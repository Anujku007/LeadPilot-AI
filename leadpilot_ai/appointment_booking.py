import base64
import logging
import threading
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from googleapiclient.errors import HttpError
from pydantic import BaseModel
from sqlalchemy import String, ForeignKey, select
from sqlalchemy.orm import Mapped, mapped_column

from .crm_store import (
    Base, engine, SessionLocal,
    Conversation, LeadProfile
)
from .calendar_availability import (
    IST, DURATION, get_calendar_service,
    get_busy_intervals, build_available_slots
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/appointments",
    tags=["Appointment Booking"]
)

_booking_lock = threading.Lock()


class Appointment(Base):
    __tablename__ = "lp_appointments"

    request_id: Mapped[str] = mapped_column(
        String(36), primary_key=True
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("lp_conversations.id"),
        nullable=False
    )
    calendar_event_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    start_at: Mapped[str] = mapped_column(
        String(40), nullable=False
    )
    end_at: Mapped[str] = mapped_column(
        String(40), nullable=False
    )


Appointment.__table__.create(
    bind=engine, checkfirst=True
)


class PreviewRequest(BaseModel):
    conversation_id: UUID
    start: datetime


class BookingRequest(PreviewRequest):
    request_id: UUID
    customer_confirmed: Literal[True]


def validate_slot(start, now=None):
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError(
            "Start time must include a timezone offset"
        )

    start = start.astimezone(IST)
    end = start + DURATION
    now = now or datetime.now(IST)

    if start <= now:
        raise ValueError("Appointment must be in the future")

    if start.weekday() >= 5:
        raise ValueError("Weekend booking is unavailable")

    if (
        start.hour < 10
        or start.hour >= 18
        or start.minute not in (0, 30)
        or start.second != 0
        or start.microsecond != 0
        or end.hour > 18
    ):
        raise ValueError(
            "Choose a 30-minute slot between 10:00 and 18:00 IST"
        )

    return start, end


def make_event_id(request_id):
    encoded = base64.b32hexencode(
        request_id.bytes
    ).decode("ascii").lower().rstrip("=")

    return "lp" + encoded


def check_google_slot(service, start):
    busy = get_busy_intervals(
        service, start.date()
    )

    slots = build_available_slots(
        start.date(),
        busy,
        now=datetime.now(IST)
    )

    return any(
        datetime.fromisoformat(item["start"]) == start
        for item in slots
    )


def ensure_conversation(db, conversation_id):
    conversation = db.get(
        Conversation, conversation_id
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )


@router.post("/preview")
def preview_appointment(request: PreviewRequest):
    conversation_id = str(request.conversation_id)

    with SessionLocal() as db:
        ensure_conversation(db, conversation_id)

    try:
        start, end = validate_slot(request.start)
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

    try:
        service = get_calendar_service()
        available = check_google_slot(
            service, start
        )
    except HTTPException:
        raise
    except (HttpError, ValueError, KeyError) as error:
        logger.warning(
            "Calendar preview failed: %s",
            type(error).__name__
        )
        raise HTTPException(
            status_code=502,
            detail="Calendar availability check failed"
        ) from error

    return {
        "success": True,
        "conversation_id": conversation_id,
        "available": available,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timezone": "Asia/Kolkata",
        "booking_created": False
    }


@router.post("/book")
def book_appointment(request: BookingRequest):
    conversation_id = str(request.conversation_id)
    request_id = str(request.request_id)

    try:
        start, end = validate_slot(request.start)
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

    event_id = make_event_id(request.request_id)

    # Serializes local requests within this server process.
    with _booking_lock:
        with SessionLocal() as db:
            ensure_conversation(db, conversation_id)

            existing = db.get(Appointment, request_id)

            if existing:
                if (
                    existing.conversation_id != conversation_id
                    or existing.start_at != start.isoformat()
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Request ID used for another booking"
                    )

                return {
                    "success": True,
                    "booking_created": True,
                    "already_processed": True,
                    "event_id": existing.calendar_event_id,
                    "start": existing.start_at,
                    "end": existing.end_at
                }

            lead = db.get(
                LeadProfile, conversation_id
            )

            if lead is None or lead.category == "Incomplete":
                raise HTTPException(
                    status_code=409,
                    detail="Complete lead qualification first"
                )

            try:
                service = get_calendar_service()

                if not check_google_slot(
                    service, start
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Selected appointment is unavailable"
                    )

                event_body = {
                    "id": event_id,
                    "summary": "LeadPilot AI - Sales Consultation",
                    "description": (
                        "Appointment confirmed through "
                        "LeadPilot AI."
                    ),
                    "start": {
                        "dateTime": start.isoformat(),
                        "timeZone": "Asia/Kolkata"
                    },
                    "end": {
                        "dateTime": end.isoformat(),
                        "timeZone": "Asia/Kolkata"
                    },
                    "extendedProperties": {
                        "private": {
                            "conversation_id": conversation_id,
                            "request_id": request_id
                        }
                    }
                }

                try:
                    event = service.events().insert(
                        calendarId="primary",
                        body=event_body,
                        sendUpdates="none"
                    ).execute()

                except HttpError as error:
                    if error.resp.status != 409:
                        raise

                    # Recover an earlier successful insert.
                    event = service.events().get(
                        calendarId="primary",
                        eventId=event_id
                    ).execute()

                    private = event.get(
                        "extendedProperties", {}
                    ).get("private", {})

                    event_start = datetime.fromisoformat(
                        event["start"]["dateTime"]
                    ).astimezone(IST)

                    if (
                        private.get("conversation_id")
                        != conversation_id
                        or private.get("request_id")
                        != request_id
                        or event_start != start
                    ):
                        raise HTTPException(
                            status_code=409,
                            detail="Booking request ID conflict"
                        )

            except HTTPException:
                raise
            except (HttpError, ValueError, KeyError) as error:
                logger.warning(
                    "Calendar booking failed: %s",
                    type(error).__name__
                )
                raise HTTPException(
                    status_code=502,
                    detail="Google Calendar booking failed"
                ) from error

            db.add(Appointment(
                request_id=request_id,
                conversation_id=conversation_id,
                calendar_event_id=event["id"],
                start_at=start.isoformat(),
                end_at=end.isoformat()
            ))

            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(
                    "Calendar event created but CRM save failed"
                )
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Calendar event may exist. "
                        "Retry with the same request_id."
                    )
                )

    return {
        "success": True,
        "booking_created": True,
        "already_processed": False,
        "event_id": event["id"],
        "start": start.isoformat(),
        "end": end.isoformat(),
        "calendar_link": event.get("htmlLink")
    }
