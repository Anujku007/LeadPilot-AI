from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from .crm_store import (
    SessionLocal, Conversation, LeadProfile
)
from .calendar_availability import check_availability

router = APIRouter(
    prefix="/api/conversations",
    tags=["Lead Appointment Workflow"]
)


def select_slot_options(slots, limit):
    return list(slots[:limit])


@router.get("/{conversation_id}/appointment-options")
def appointment_options(
    conversation_id: UUID,
    date: date,
    limit: int = Query(default=5, ge=1, le=10)
):
    conversation_id = str(conversation_id)

    # Verify the conversation belongs to a qualified lead.
    with SessionLocal() as db:
        conversation = db.get(
            Conversation, conversation_id
        )

        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found"
            )

        lead = db.get(
            LeadProfile, conversation_id
        )

        if lead is None or lead.category != "Hot":
            raise HTTPException(
                status_code=409,
                detail="A Hot lead is required to offer slots"
            )

        score = lead.score

    # Existing read-only Google Calendar service
    availability = check_availability(date)

    slots = select_slot_options(
        availability["available_slots"],
        limit
    )

    return {
        "success": True,
        "conversation_id": conversation_id,
        "lead_category": "Hot",
        "lead_score": score,
        "date": date.isoformat(),
        "timezone": "Asia/Kolkata",
        "duration_minutes": 30,
        "total_available": availability["available_count"],
        "suggested_slots": slots,
        "booking_created": False,
        "next_action": (
            "Ask the customer to select a slot. "
            "Confirm the chosen time before booking."
        )
    }
