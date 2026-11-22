from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .crm_store import (
    Base, engine, SessionLocal,
    Conversation, LeadProfile
)
from .appointment_booking import (
    Appointment, BookingRequest,
    PreviewRequest, preview_appointment,
    book_appointment, validate_slot
)

router = APIRouter(
    prefix="/api/conversations",
    tags=["AI Appointment Confirmation"]
)


class AppointmentProposal(Base):
    __tablename__ = "lp_appointment_proposals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("lp_conversations.id"),
        nullable=False
    )
    start_at: Mapped[str] = mapped_column(
        String(40), nullable=False
    )
    expires_at: Mapped[str] = mapped_column(
        String(40), nullable=False
    )


AppointmentProposal.__table__.create(
    bind=engine, checkfirst=True
)


class ProposalRequest(BaseModel):
    start: datetime


class ConfirmationRequest(BaseModel):
    proposal_id: UUID
    confirmation_text: Literal["CONFIRM BOOKING"]


def ensure_hot_lead(db, conversation_id):
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
            detail="A Hot lead is required"
        )

    return lead


def is_expired(expires_at, now=None):
    now = now or datetime.now(timezone.utc)
    expiry = datetime.fromisoformat(expires_at)
    return now >= expiry


@router.post("/{conversation_id}/appointment-proposal")
def propose_appointment(
    conversation_id: UUID,
    request: ProposalRequest
):
    cid = str(conversation_id)

    with SessionLocal() as db:
        lead = ensure_hot_lead(db, cid)
        score = lead.score

    try:
        start, end = validate_slot(request.start)
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

    # Read-only Google Calendar check
    preview = preview_appointment(
        PreviewRequest(
            conversation_id=conversation_id,
            start=start
        )
    )

    if not preview["available"]:
        raise HTTPException(
            status_code=409,
            detail="Selected appointment is unavailable"
        )

    proposal_id = uuid4()

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=15)
    ).isoformat()

    with SessionLocal() as db:
        db.add(AppointmentProposal(
            id=str(proposal_id),
            conversation_id=cid,
            start_at=start.isoformat(),
            expires_at=expires_at
        ))
        db.commit()

    return {
        "success": True,
        "proposal_id": str(proposal_id),
        "conversation_id": cid,
        "lead_score": score,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "expires_at": expires_at,
        "booking_created": False,
        "confirmation_required": True,
        "message": (
            "Please confirm this 30-minute appointment. "
            "No calendar booking has been created."
        )
    }


@router.post("/{conversation_id}/confirm-appointment")
def confirm_appointment(
    conversation_id: UUID,
    request: ConfirmationRequest
):
    cid = str(conversation_id)
    proposal_id = str(request.proposal_id)

    with SessionLocal() as db:
        ensure_hot_lead(db, cid)

        proposal = db.get(
            AppointmentProposal, proposal_id
        )

        if proposal is None:
            raise HTTPException(
                status_code=404,
                detail="Appointment proposal not found"
            )

        if proposal.conversation_id != cid:
            raise HTTPException(
                status_code=403,
                detail="Proposal belongs to another conversation"
            )

        # Retry-safe response for an already saved booking
        existing = db.get(Appointment, proposal_id)

        if existing is not None:
            return {
                "success": True,
                "booking_created": True,
                "already_processed": True,
                "event_id": existing.calendar_event_id,
                "start": existing.start_at,
                "end": existing.end_at
            }

        if is_expired(proposal.expires_at):
            raise HTTPException(
                status_code=410,
                detail="Proposal expired. Select a slot again."
            )

        start = datetime.fromisoformat(
            proposal.start_at
        )

    # Actual booking occurs ONLY after explicit confirmation
    result = book_appointment(
        BookingRequest(
            conversation_id=conversation_id,
            request_id=request.proposal_id,
            start=start,
            customer_confirmed=True
        )
    )

    return {
        **result,
        "proposal_id": proposal_id,
        "customer_confirmation_received": True
    }
