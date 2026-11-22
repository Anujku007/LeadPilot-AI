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

        qualification = merge_qualification(
            stored,
            extraction["extracted"]
        )

        reply = await nvidia.generate_response(
            message=request.message,
            history=history,
            system_prompt=prompt_for_lead(
                qualification
            )
        )

        next_question = qualification["next_question"]

        if (
            next_question
            and next_question.casefold()
            not in reply.casefold()
        ):
            reply = (
                "Thank you for sharing those details. "
                + next_question
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

        db.add(ChatMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=reply
        ))

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

    return {
        "success": True,
        "conversation_id": conversation_id,
        "reply": reply,
        "lead": qualification
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
