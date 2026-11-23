"""Local operator-managed outcomes for *confirmed* LeadPilot appointments.

No inference from the LLM: meeting completion and sales outcomes require deliberate
operator actions. Do not expose these endpoints outside localhost without auth/RBAC.
Additive SQLite tables only: existing calendar events and CRM rows are untouched.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from .crm_store import Base, engine, SessionLocal, LeadProfile
from .appointment_booking import Appointment
from . import dashboard_api

ConversationLabel = getattr(dashboard_api, "ConversationLabel", None)

router = APIRouter(prefix="/api/sales", tags=["Local Sales Pipeline"])


class SalesOutcome(Base):
    __tablename__ = "lp_sales_outcomes"
    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lp_appointments.request_id"), primary_key=True
    )
    completed_at: Mapped[str] = mapped_column(String(40), nullable=False)
    meeting_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    follow_up_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    deal_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class SalesActivity(Base):
    __tablename__ = "lp_sales_activities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lp_appointments.request_id"), nullable=False
    )
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(String(250), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


# Add only our new tables. checkfirst preserves existing data on restart.
SalesOutcome.__table__.create(bind=engine, checkfirst=True)
SalesActivity.__table__.create(bind=engine, checkfirst=True)


def utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


def to_utc(value: datetime) -> datetime:
    """Calendar entries must carry a timezone; no guessed offsets."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Appointment time is missing a timezone offset")
    return value.astimezone(timezone.utc)


def _booking(db, request_id):
    appointment = db.get(Appointment, request_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Booked appointment not found")
    return appointment


def _appointment_dict(booking, result, label, lead):
    return {
        "request_id": booking.request_id,
        "conversation_id": booking.conversation_id,
        "calendar_event_id": booking.calendar_event_id,
        "start": booking.start_at,
        "end": booking.end_at,
        "display_name": label,
        "lead_category": lead.category if lead else None,
        "lead_score": lead.score if lead else None,
        "meeting_status": "Meeting Completed" if result else "Booked",
        "completed_at": result.completed_at if result else None,
        "meeting_notes": result.meeting_notes if result else "",
        "outcome": result.outcome if result else None,
        "follow_up_at": result.follow_up_at if result else None,
        "deal_value": str(result.deal_value) if result and result.deal_value is not None else None,
        "lost_reason": result.lost_reason if result else None,
        "updated_at": result.updated_at if result else None,
    }


@router.get("/pipeline")
def get_pipeline():
    with SessionLocal() as db:
        bookings = db.scalars(select(Appointment).order_by(Appointment.start_at.desc())).all()
        results = {r.request_id: r for r in db.scalars(select(SalesOutcome)).all()}
        ids = {r.conversation_id for r in bookings}
        labels = {r.conversation_id: r.display_name for r in db.scalars(
            select(ConversationLabel).where(ConversationLabel.conversation_id.in_(ids))
        ).all()} if ids and ConversationLabel is not None else {}
        leads = {r.conversation_id: r for r in db.scalars(
            select(LeadProfile).where(LeadProfile.conversation_id.in_(ids))
        ).all()} if ids else {}
        rows = [_appointment_dict(b, results.get(b.request_id), labels.get(b.conversation_id),
                                  leads.get(b.conversation_id)) for b in bookings]
        # Appointments are not sales opportunities: one conversation is one
        # opportunity, regardless of the number of booked consultations.
        # Legacy duplicate outcomes remain in the audit data; select the last
        # update for display and flag any historical conflicts for review.
        outcome_groups = {}
        booking_counts = {}
        completed_conversations = set()
        for booking in bookings:
            cid = booking.conversation_id
            booking_counts[cid] = booking_counts.get(cid, 0) + 1
            result = results.get(booking.request_id)
            if result:
                completed_conversations.add(cid)
                if result.outcome is not None:
                    outcome_groups.setdefault(cid, []).append(result)
        owners = {
            cid: max(records, key=lambda r: (r.updated_at, r.request_id))
            for cid, records in outcome_groups.items()
        }
        for row in rows:
            owner = owners.get(row["conversation_id"])
            row["opportunity_outcome"] = owner.outcome if owner else None
            row["opportunity_owner_request_id"] = owner.request_id if owner else None
            row["opportunity_deal_value"] = (
                str(owner.deal_value) if owner and owner.deal_value is not None else None
            )
            row["opportunity_follow_up_at"] = owner.follow_up_at if owner else None
            row["opportunity_appointment_count"] = booking_counts[row["conversation_id"]]
        now = datetime.now(timezone.utc)
        followups_due = sum(
            1 for owner in owners.values()
            if owner.outcome == "Follow-up Required" and owner.follow_up_at
            and to_utc(datetime.fromisoformat(owner.follow_up_at)) <= now
        )
        revenue = sum(
            (owner.deal_value for owner in owners.values()
             if owner.outcome == "Won" and owner.deal_value is not None),
            Decimal("0.00"),
        )
        return {
            "appointments": rows,
            "summary": {
                "booked": len(bookings),
                "completed": len(results),
                "opportunities": len(booking_counts),
                "pending_outcome": len(completed_conversations - owners.keys()),
                "follow_up_required": sum(r.outcome == "Follow-up Required" for r in owners.values()),
                "won": sum(r.outcome == "Won" for r in owners.values()),
                "lost": sum(r.outcome == "Lost" for r in owners.values()),
                "followups_due": followups_due,
                "won_revenue_inr": str(revenue),
                "opportunity_conflicts": sum(len(records) > 1 for records in outcome_groups.values()),
            },
            "currency": "INR",
        }


class CompleteRequest(BaseModel):
    meeting_notes: str = Field(default="", max_length=4000)


@router.post("/appointments/{request_id}/complete")
def complete_meeting(request_id: UUID, request: CompleteRequest):
    key = str(request_id)
    with SessionLocal() as db:
        appointment = _booking(db, key)
        try:
            ended = to_utc(datetime.fromisoformat(appointment.end_at))
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=409, detail="Booking end time is invalid") from error
        if ended > datetime.now(timezone.utc):
            raise HTTPException(status_code=409, detail="Cannot complete a meeting before its scheduled end")
        result = db.get(SalesOutcome, key)
        now = utcnow_iso()
        if result is None:
            result = SalesOutcome(request_id=key, completed_at=now, meeting_notes=request.meeting_notes.strip(),
                                  outcome=None, updated_at=now)
            db.add(result)
            db.add(SalesActivity(request_id=key, event="meeting_completed", description="Meeting marked completed", created_at=now))
        else:
            notes = request.meeting_notes.strip()
            if notes != result.meeting_notes:
                result.meeting_notes = notes
                result.updated_at = now
                db.add(SalesActivity(request_id=key, event="notes_updated", description="Meeting notes updated", created_at=now))
        db.commit()
        return {"success": True, "request_id": key, "meeting_status": "Meeting Completed",
                "completed_at": result.completed_at, "meeting_notes": result.meeting_notes,
                "outcome": result.outcome}


OutcomeLiteral = Literal["Follow-up Required", "Won", "Lost"]


class OutcomeRequest(BaseModel):
    outcome: OutcomeLiteral
    follow_up_at: datetime | None = None
    deal_value: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    lost_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_outcome(self):
        if self.outcome == "Follow-up Required":
            if self.follow_up_at is None:
                raise ValueError("Follow-up date and time are required")
            if self.follow_up_at.tzinfo is None or self.follow_up_at.utcoffset() is None:
                raise ValueError("Follow-up date and time must include a timezone offset")
            if self.follow_up_at.astimezone(timezone.utc) <= datetime.now(timezone.utc):
                raise ValueError("Follow-up must be in the future")
            if self.deal_value is not None or self.lost_reason:
                raise ValueError("Follow-up cannot include a won amount or lost reason")
        elif self.outcome == "Won":
            if self.deal_value is None:
                raise ValueError("Won deals require a positive deal value in INR")
            if self.follow_up_at is not None or self.lost_reason:
                raise ValueError("Won deals cannot include follow-up dates or loss reasons")
        else:
            if not self.lost_reason or not self.lost_reason.strip():
                raise ValueError("Lost deals require a reason")
            if self.follow_up_at is not None or self.deal_value is not None:
                raise ValueError("Lost deals cannot include follow-up dates or won amounts")
        return self


@router.patch("/appointments/{request_id}/outcome")
def set_outcome(request_id: UUID, request: OutcomeRequest):
    key = str(request_id)
    with SessionLocal() as db:
        # Serialize opportunity decisions on local SQLite, including concurrent
        # requests for two different appointments belonging to the same lead.
        # Keep this *before* any ORM read to avoid an already-open transaction.
        if db.bind.dialect.name == "sqlite":
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        appointment = _booking(db, key)
        result = db.get(SalesOutcome, key)
        if result is None:
            raise HTTPException(status_code=409, detail="Mark the meeting completed first")
        existing = db.scalars(
            select(SalesOutcome)
            .join(Appointment, Appointment.request_id == SalesOutcome.request_id)
            .where(
                Appointment.conversation_id == appointment.conversation_id,
                SalesOutcome.request_id != key,
                SalesOutcome.outcome.is_not(None),
            )
            .order_by(SalesOutcome.updated_at.desc())
        ).first()
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This lead already has a sales outcome on appointment "
                    f"{existing.request_id} ({existing.outcome}). "
                    "Open that appointment to update its outcome. "
                    "Multiple meetings for the same lead share one sales opportunity."
                ),
            )
        now = utcnow_iso()
        old = result.outcome
        when = request.follow_up_at.astimezone(timezone.utc).isoformat() if request.follow_up_at else None
        value = request.deal_value
        loss = request.lost_reason.strip() if request.lost_reason else None
        changed = old != request.outcome or (result.follow_up_at or None) != when \
            or result.deal_value != value or (result.lost_reason or None) != loss
        if changed:
            result.outcome = request.outcome
            result.follow_up_at = when
            result.deal_value = value
            result.lost_reason = loss
            result.updated_at = now
            db.add(SalesActivity(request_id=key, event="outcome_changed",
                                 description=f"Outcome: {old or 'Pending'} → {request.outcome}", created_at=now))
            db.commit()
        return {"success": True, "request_id": key, "meeting_status": "Meeting Completed",
                "outcome": result.outcome, "follow_up_at": result.follow_up_at,
                "deal_value": str(result.deal_value) if result.deal_value is not None else None,
                "lost_reason": result.lost_reason}


@router.get("/appointments/{request_id}/history")
def get_outcome_history(request_id: UUID):
    key = str(request_id)
    with SessionLocal() as db:
        _booking(db, key)
        records = db.scalars(select(SalesActivity).where(SalesActivity.request_id == key)
                             .order_by(SalesActivity.id.desc()).limit(100)).all()
        return {"request_id": key, "activities": [{"event": r.event, "description": r.description,
                                                      "created_at": r.created_at} for r in records]}
