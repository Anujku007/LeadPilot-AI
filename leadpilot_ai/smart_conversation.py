"""Safe, deterministic routing for qualification and conversational booking.

This module never books an appointment. Only a separate explicit confirmation
request can create a Google Calendar event.
"""
from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from .crm_store import SessionLocal, Conversation
from .appointment_booking import Appointment
from .appointment_confirmation import AppointmentProposal, is_expired
from .calendar_availability import IST
from .qualification_flow import merge_qualification

router = APIRouter(prefix="/api/conversations", tags=["Conversational Scheduling"])

AUTHORITY_QUESTION = (
    "Are you personally authorized to approve the CRM purchase, "
    "or does someone else make the final buying decision?"
)

# Match explicit self-identification only; do not infer buying authority
# from department names, team size, or an employer's job title.
AUTHORITY_SELF = re.compile(
    r"\b(?:i\s+am|i'm|i’m)\s+(?:(?:the|a|an|company|business|final)\s+){0,3}"
    r"(?:owner|founder|decision[\s-]?maker|purchase[\s-]?approver)\b"
    r"|\bi\s+(?:own|founded)\s+(?:the|this|my)\s+(?:business|company|agency)\b"
    r"|\bi\s+(?:can|will|personally)\s+(?:approve|authorize|sign\s+off\s+on)\s+"
    r"(?:the|this|our|a)?\s*(?:purchase|budget|deal|investment|software|crm)\b",
    re.IGNORECASE,
)

MONTH_OR_DAY = re.compile(
    r"\b(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b"
    r"|\b\d{4}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)
CLOCK = re.compile(
    r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b"
    r"|\b(?:1[0-2]|0?[1-9])\s*(?:a\.?m\.?|p\.?m\.?)\b"
    r"|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"\s+(?:in\s+the\s+)?(?:morning|afternoon|evening)\b"
    r"|\b(?:1[0-2]|0?[1-9])\s+(?:in\s+the\s+)?(?:morning|afternoon|evening)\b",
    re.IGNORECASE,
)
MEETING = re.compile(
    r"\b(?:appointment|consultation|demo|demonstration|meeting|booking|book|schedule|slot)\b",
    re.IGNORECASE,
)
POSITIVE = re.compile(
    r"^\s*(?:yes|sure|okay|ok|definitely|absolutely|please|that\s+would\s+be\s+helpful)"
    r"(?:[,.!\s]|$)", re.IGNORECASE
)
CONFIRM_WORDS = re.compile(
    r"\b(?:confirm\s+(?:the\s+)?(?:appointment|booking|slot)|book\s+(?:it|that\s+slot))\b",
    re.IGNORECASE,
)


def recover_explicit_authority(qualification: dict, user_messages: list[str]) -> dict:
    """Restore *only* unambiguous first-person buying authority, as fallback to AI."""
    authority = qualification["extracted"].get("authority", "unknown")
    if authority == "decision_maker":
        return qualification
    if any(AUTHORITY_SELF.search(text or "") for text in user_messages):
        return merge_qualification(qualification["extracted"], {"authority": "decision_maker"})
    return qualification


def missing_question(qualification: dict) -> str | None:
    missing = qualification.get("missing_fields") or []
    if not missing:
        return None
    if missing[0] == "authority":
        return AUTHORITY_QUESTION
    return qualification.get("next_question")


def classify_booking_turn(message: str, history: list[dict], hot: bool) -> str:
    """'check', 'ask_time', 'confirm_ui' or 'none'; no calendar side effects."""
    if not hot:
        return "none"
    text = (message or "").strip()
    if CONFIRM_WORDS.search(text) and not (CLOCK.search(text) and MONTH_OR_DAY.search(text)):
        return "confirm_ui"
    previous = next((str(m.get("content", "")) for m in reversed(history)
                     if m.get("role") == "assistant"), "")
    offered = bool(re.search(r"\b(?:schedule|consultation|appointment|book|date and time)\b", previous, re.I))
    if CLOCK.search(text) and (MONTH_OR_DAY.search(text) or MEETING.search(text) or offered):
        return "check"
    if MEETING.search(text) and re.search(r"\b(?:want|would like|can we|please|let's|let us|schedule|book)\b", text, re.I):
        return "ask_time"
    if offered and POSITIVE.search(text):
        return "ask_time"
    return "none"


def has_saved_booking(conversation_id: str) -> bool:
    """Block an accidental second *upcoming* consultation in this chat."""
    with SessionLocal() as db:
        rows = db.scalars(select(Appointment).where(
            Appointment.conversation_id == conversation_id
        )).all()
        now = datetime.now(IST)
        for appointment in rows:
            try:
                if datetime.fromisoformat(appointment.end_at).astimezone(IST) > now:
                    return True
            except (TypeError, ValueError):
                continue
        return False


def current_booking_state(conversation_id: str) -> dict:
    """Read-only view for reloading a pending confirmation in the chat UI."""
    with SessionLocal() as db:
        if db.get(Conversation, conversation_id) is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        proposals = db.scalars(
            select(AppointmentProposal).where(
                AppointmentProposal.conversation_id == conversation_id
            ).order_by(AppointmentProposal.expires_at.desc()).limit(20)
        ).all()
        for proposal in proposals:
            if is_expired(proposal.expires_at):
                continue
            if db.get(Appointment, proposal.id):
                continue
            return {
                "success": True, "booking_created": False,
                "proposal": {
                    "proposal_id": proposal.id,
                    "conversation_id": proposal.conversation_id,
                    "start": proposal.start_at,
                    "expires_at": proposal.expires_at,
                    "booking_created": False,
                },
            }

        booked = db.scalars(
            select(Appointment).where(
                Appointment.conversation_id == conversation_id
            ).order_by(Appointment.start_at.desc()).limit(20)
        ).all()
        now = datetime.now(IST)
        for appointment in booked:
            try:
                if datetime.fromisoformat(appointment.end_at).astimezone(IST) > now:
                    return {
                        "success": True, "booking_created": True,
                        "proposal": None,
                        "appointment": {
                            "start": appointment.start_at,
                            "end": appointment.end_at,
                            "event_id": appointment.calendar_event_id,
                        },
                    }
            except (TypeError, ValueError):
                continue
        return {"success": True, "booking_created": False, "proposal": None}


@router.get("/{conversation_id}/pending-appointment")
def pending_appointment(conversation_id: UUID):
    return current_booking_state(str(conversation_id))
