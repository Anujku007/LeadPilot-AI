"""Local-only, read-only summaries for the LeadPilot AI Copilot UI.

Do not expose the parent API publicly without user authentication and authorization.
"""
from datetime import timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from pydantic import BaseModel, Field

from .crm_store import Base, engine, SessionLocal, Conversation, ChatMessage, LeadProfile
from .appointment_booking import Appointment

router = APIRouter(prefix="/api/dashboard", tags=["Local Copilot Dashboard"])


class ConversationLabel(Base):
    """Optional operator-defined display name; the AI never invents customer identity."""
    __tablename__ = "lp_conversation_labels"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lp_conversations.id"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)


# Small additive table; no migration or changes to existing lead/message records.
ConversationLabel.__table__.create(bind=engine, checkfirst=True)


class LabelUpdate(BaseModel):
    display_name: str = Field(max_length=64)


@router.patch("/conversations/{conversation_id}/label")
def update_conversation_label(conversation_id: str, request: LabelUpdate):
    name = request.display_name.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise HTTPException(status_code=422, detail="Name contains invalid characters")
    with SessionLocal() as db:
        if db.get(Conversation, conversation_id) is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        label = db.get(ConversationLabel, conversation_id)
        if name:
            if label is None:
                db.add(ConversationLabel(conversation_id=conversation_id, display_name=name))
            else:
                label.display_name = name
        elif label is not None:
            db.delete(label)
        db.commit()
    return {"success": True, "conversation_id": conversation_id, "display_name": name or None}



def _iso_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _lead_dict(lead):
    if lead is None:
        return None
    return {
        "budget": lead.budget,
        "authority": lead.authority,
        "need": lead.need,
        "timeline": lead.timeline,
        "score": lead.score,
        "category": lead.category,
    }


@router.get("/summary")
def dashboard_summary():
    with SessionLocal() as db:
        conversations = db.scalar(select(func.count()).select_from(Conversation)) or 0
        leads = db.scalar(select(func.count()).select_from(LeadProfile)) or 0
        hot = db.scalar(select(func.count()).select_from(LeadProfile).where(LeadProfile.category == "Hot")) or 0
        qualified = db.scalar(select(func.count()).select_from(LeadProfile).where(LeadProfile.category.in_(["Hot", "Warm", "Cold"]))) or 0
        meetings = db.scalar(select(func.count()).select_from(Appointment)) or 0
    return {
        "total_conversations": conversations,
        "total_leads": leads,
        "hot_leads": hot,
        "qualified_leads": qualified,
        "appointments_booked": meetings,
        # No authoritative live-call log exists in this prototype.
        "calls_today": None,
        "calls_tracking_enabled": False,
    }


@router.get("/conversations")
def dashboard_conversations(limit: int = Query(default=100, ge=1, le=200)):
    with SessionLocal() as db:
        conversations = db.scalars(
            select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
        ).all()
        ids = [item.id for item in conversations]
        leads = {}
        labels = {}
        last_message = {}
        if ids:
            lead_rows = db.scalars(select(LeadProfile).where(LeadProfile.conversation_id.in_(ids))).all()
            leads = {lead.conversation_id: lead for lead in lead_rows}
            labels = {label.conversation_id: label.display_name for label in db.scalars(
                select(ConversationLabel).where(ConversationLabel.conversation_id.in_(ids))
            ).all()}
            # Take the latest message for each conversation, most recent ID first.
            rows = db.scalars(
                select(ChatMessage).where(ChatMessage.conversation_id.in_(ids)).order_by(ChatMessage.id.desc())
            ).all()
            for row in rows:
                if row.conversation_id not in last_message:
                    last_message[row.conversation_id] = {"role": row.role, "content": row.content}
        return {
            "conversations": [
                {
                    "id": c.id,
                    "display_name": labels.get(c.id),
                    "created_at": _iso_utc(c.created_at),
                    "updated_at": _iso_utc(c.updated_at),
                    "lead": _lead_dict(leads.get(c.id)),
                    "last_message": last_message.get(c.id),
                }
                for c in conversations
            ],
            "limit": limit,
        }


@router.get("/appointments")
def dashboard_appointments(limit: int = Query(default=50, ge=1, le=200)):
    with SessionLocal() as db:
        rows = db.scalars(
            select(Appointment).order_by(Appointment.start_at.desc()).limit(limit)
        ).all()
        return {
            "appointments": [
                {
                    "request_id": row.request_id,
                    "conversation_id": row.conversation_id,
                    "calendar_event_id": row.calendar_event_id,
                    "start": row.start_at,
                    "end": row.end_at,
                }
                for row in rows
            ]
        }
