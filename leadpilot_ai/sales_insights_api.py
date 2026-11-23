"""Read-only sales analytics and due follow-up alerts for the local LeadPilot operator.

One sales opportunity per CRM conversation. Browser alerts are delivered by the
frontend only while it is open; this module NEVER sends emails or customer messages.
Keep behind localhost until proper authentication/authorization are implemented.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import select

from .appointment_booking import Appointment
from .crm_store import LeadProfile, SessionLocal
from .sales_pipeline_api import SalesOutcome
from . import dashboard_api

router = APIRouter(prefix='/api/sales', tags=['Local Sales Follow-up & Analytics'])
ConversationLabel = getattr(dashboard_api, 'ConversationLabel', None)


def _as_utc(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _pct(top, bottom):
    return round(100 * top / bottom, 1) if bottom else 0.0


def build_sales_overview(db, now=None):
    """Purely read existing bookings and outcomes; no DB or calendar mutations."""
    now = now or datetime.now(timezone.utc)
    bookings = db.scalars(select(Appointment)).all()
    outcomes = {r.request_id: r for r in db.scalars(select(SalesOutcome)).all()}
    conversation_ids = {b.conversation_id for b in bookings}
    labels = {}
    if conversation_ids and ConversationLabel is not None:
        labels = {r.conversation_id: r.display_name for r in db.scalars(
            select(ConversationLabel).where(ConversationLabel.conversation_id.in_(conversation_ids))
        ).all()}
    leads = {}
    if conversation_ids:
        leads = {r.conversation_id: r for r in db.scalars(
            select(LeadProfile).where(LeadProfile.conversation_id.in_(conversation_ids))
        ).all()}
    meetings_by_lead = defaultdict(list)
    actual_outcomes = defaultdict(list)
    completed_leads = set()
    for appointment in bookings:
        cid = appointment.conversation_id
        meetings_by_lead[cid].append(appointment)
        record = outcomes.get(appointment.request_id)
        if record is not None:
            completed_leads.add(cid)
            if record.outcome is not None:
                actual_outcomes[cid].append(record)
    owners = {cid: max(records, key=lambda r: (r.updated_at, r.request_id))
              for cid, records in actual_outcomes.items()}
    won = [row for row in owners.values() if row.outcome == 'Won']
    lost = [row for row in owners.values() if row.outcome == 'Lost']
    followups = [row for row in owners.values() if row.outcome == 'Follow-up Required']
    revenue = sum((Decimal(str(row.deal_value)) for row in won if row.deal_value is not None), Decimal('0.00'))
    due, upcoming = [], []
    for conversation_id, row in owners.items():
        if row.outcome != 'Follow-up Required' or not row.follow_up_at:
            continue
        due_time = _as_utc(row.follow_up_at)
        if due_time is None:
            continue
        lead = leads.get(conversation_id)
        item = {
            'conversation_id': conversation_id,
            'request_id': row.request_id,
            'display_name': labels.get(conversation_id) or f'Lead {conversation_id[:8]}',
            'follow_up_at': due_time.isoformat(),
            'lead_category': lead.category if lead else None,
            'lead_score': lead.score if lead else None,
            'appointment_count': len(meetings_by_lead[conversation_id]),
        }
        if due_time <= now:
            due.append(item)
        elif due_time <= now + timedelta(days=7):
            upcoming.append(item)
    due.sort(key=lambda item: item['follow_up_at'])
    upcoming.sort(key=lambda item: item['follow_up_at'])
    opportunity_count = len(meetings_by_lead)
    decided = len(won) + len(lost)
    analytics = {
        'booked_appointments': len(bookings),
        'distinct_opportunities': opportunity_count,
        'completed_meetings': len(outcomes),
        'opportunities_with_completed_meetings': len(completed_leads),
        'pending_decision': len(completed_leads - owners.keys()),
        'follow_up_required': len(followups),
        'won': len(won),
        'lost': len(lost),
        'win_rate_decided_percent': _pct(len(won), decided),
        'opportunity_to_won_percent': _pct(len(won), opportunity_count),
        'meeting_completion_percent': _pct(len(outcomes), len(bookings)),
        'won_deal_value_inr': str(revenue.quantize(Decimal('0.01'))),
        'average_won_deal_inr': str((revenue / len(won) if won else Decimal('0.00')).quantize(Decimal('0.01'))),
        'historical_conflicts': sum(len(items) > 1 for items in actual_outcomes.values()),
    }
    return {
        'generated_at': now.isoformat(),
        'analytics': analytics,
        'reminders': {'due': due, 'upcoming': upcoming, 'due_count': len(due), 'upcoming_count': len(upcoming)},
        'currency': 'INR',
        'notification_delivery': 'in-app/browser-when-open',
    }


@router.get('/overview')
def get_sales_overview():
    with SessionLocal() as db:
        return build_sales_overview(db)
