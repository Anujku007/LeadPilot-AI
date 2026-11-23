import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from .crm_store import (
    SessionLocal, Conversation,
    ChatMessage, LeadProfile, utcnow
)
from .lead_extraction import (
    extract_lead, ExtractionRequest,
    ConversationTurn
)
from .nvidia_llm_service import NvidiaLLMService
from .qualification_flow import merge_qualification, prompt_for_lead
from .smart_conversation import (
    classify_booking_turn, missing_question, recover_explicit_authority, has_saved_booking
)

router = APIRouter(
    prefix="/api/conversations",
    tags=["CRM Conversations"]
)

logger = logging.getLogger(__name__)
nvidia = NvidiaLLMService()


class ChatInput(BaseModel):
    message: str = Field(
        min_length=1, max_length=2000
    )


@router.post("/start")
def start_conversation():
    conversation_id = str(uuid4())

    with SessionLocal() as db:
        db.add(Conversation(id=conversation_id))
        db.commit()

    return {
        "success": True,
        "conversation_id": conversation_id,
        "message": "Conversation started"
    }


@router.post("/{conversation_id}/chat")
async def conversation_chat(
    conversation_id: str,
    request: ChatInput
):
    # Read saved conversation state
    with SessionLocal() as db:
        conversation = db.get(
            Conversation, conversation_id
        )

        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found"
            )

        previous = db.scalars(
            select(ChatMessage)
            .where(
                ChatMessage.conversation_id
                == conversation_id
            )
            .order_by(ChatMessage.id.desc())
            .limit(18)
        ).all()

        history = [
            {
                "role": row.role,
                "content": row.content
            }
            for row in reversed(previous)
        ]

        prior_lead = db.get(
            LeadProfile, conversation_id
        )

        stored = (
            {
                field: getattr(prior_lead, field)
                for field in (
                    "budget",
                    "authority",
                    "need",
                    "timeline"
                )
            }
            if prior_lead else {}
        )

    # Extract qualification data before responding
    transcript = history + [
        {
            "role": "user",
            "content": request.message
        }
    ]

    try:
        extraction = await extract_lead(
            ExtractionRequest(
                messages=[
                    ConversationTurn(
                        role=item["role"],
                        content=item["content"][:2000]
                    )
                    for item in transcript
                ]
            )
        )

        qualification = merge_qualification(stored, extraction["extracted"])
        # Only customer statements are evidence for buying authority;
        # software department/user-count claims do not establish authority.
        user_texts = [t["content"] for t in transcript if t["role"] == "user"]
        qualification = recover_explicit_authority(qualification, user_texts)
        stage = classify_booking_turn(
            request.message, history, qualification["category"] == "Hot"
        )

        if stage == "ask_time":
            reply = (
                "Certainly. What date and time in IST would you prefer for "
                "your 30-minute consultation? I will check live availability."
            )
        elif stage == "confirm_ui":
            reply = (
                "To book safely, review the available slot and click "
                "CONFIRM BOOKING in the appointment card shown in chat. "
                "I cannot confirm a calendar event from speech or text alone."
            )
        elif stage == "check":
            reply = "I'll check that time against Google Calendar now."
        else:
            reply = await nvidia.generate_response(
                message=request.message, history=history,
                system_prompt=prompt_for_lead(qualification)
            )
            question = missing_question(qualification)
            if question and question.casefold() not in reply.casefold():
                if qualification["missing_fields"][0] == "authority":
                    reply = (
                        "Thanks for explaining. To complete qualification, " + question
                    )
                else:
                    reply = "Thank you for sharing those details. " + question
            elif not question and any(s in reply.lower() for s in (
                "cannot confirm bookings", "can't confirm bookings",
                "cannot send calendar", "cannot book appointments"
            )):
                reply = (
                    "I can help you check live Google Calendar availability "
                    "and prepare a 30-minute consultation. "
                    "What date and time in IST would you prefer?"
                )

    except HTTPException:
        raise

    except Exception as error:
        logger.warning(
            "Conversation AI failed: %s",
            type(error).__name__
        )
        raise HTTPException(
            status_code=502,
            detail="AI processing failed"
        ) from error

    # Save conversation and qualification to database
    with SessionLocal() as db:
        conversation = db.get(
            Conversation, conversation_id
        )

        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found"
            )

        db.add(ChatMessage(
            conversation_id=conversation_id,
            role="user",
            content=request.message
        ))

        assistant_entry = ChatMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=reply
        )
        db.add(assistant_entry)

        lead = db.get(
            LeadProfile, conversation_id
        )

        if lead is None:
            lead = LeadProfile(
                conversation_id=conversation_id
            )
            db.add(lead)

        for field, value in qualification[
            "extracted"
        ].items():
            setattr(lead, field, value)

        lead.score = qualification["score"]
        lead.category = qualification["category"]

        conversation.updated_at = utcnow()

        db.commit()
        assistant_message_id = assistant_entry.id

    # Scheduling is an independent, verified tool action. It cannot book;
    # it only proposes a live-available slot. Persist the *actual* result
    # instead of an LLM guess about calendar availability.
    scheduling = None
    if stage == "check":
        if has_saved_booking(conversation_id):
            reply = (
                "This lead already has a saved consultation. "
                "Please review it under Appointments before arranging another."
            )
        else:
            try:
                from uuid import UUID
                from .natural_language_scheduling import (
                    ScheduleRequest, schedule_request
                )
                result = await schedule_request(
                    UUID(conversation_id), ScheduleRequest(message=request.message)
                )
                scheduling = result
                if result.get("proposal"):
                    reply = (
                        "Google Calendar shows your requested 30-minute slot "
                        "as available. Please review the appointment card in "
                        "this chat and click CONFIRM BOOKING to create the event."
                    )
                else:
                    reply = result.get("reply", "Please choose another time.")
            except HTTPException as error:
                logger.warning("Scheduling check unavailable (%s)", error.status_code)
                reply = (
                    "I couldn't verify Google Calendar availability right now. "
                    "Please retry or check the Appointments page; "
                    "no booking was created."
                )
            except Exception as error:
                logger.warning("Scheduling error: %s", type(error).__name__)
                reply = (
                    "I couldn't verify that time right now. "
                    "Please try again using Appointments. No booking was created."
                )
        with SessionLocal() as db:
            saved = db.get(ChatMessage, assistant_message_id)
            if saved is not None and saved.conversation_id == conversation_id:
                saved.content = reply
                db.commit()

    return {
        "success": True,
        "conversation_id": conversation_id,
        "reply": reply,
        "lead": qualification,
        "scheduling": scheduling
    }


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str):
    with SessionLocal() as db:
        conversation = db.get(
            Conversation, conversation_id
        )

        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found"
            )

        messages = db.scalars(
            select(ChatMessage)
            .where(
                ChatMessage.conversation_id
                == conversation_id
            )
            .order_by(ChatMessage.id)
        ).all()

        lead = db.get(
            LeadProfile, conversation_id
        )

        return {
            "conversation_id": conversation_id,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content
                }
                for msg in messages
            ],
            "lead": None if lead is None else {
                "budget": lead.budget,
                "authority": lead.authority,
                "need": lead.need,
                "timeline": lead.timeline,
                "score": lead.score,
                "category": lead.category
            }
        }
