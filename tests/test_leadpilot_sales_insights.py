"""Read-only follow-up and revenue analytics; isolated SQLite, no real CRM writes."""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from leadpilot_ai import sales_insights_api as insights
from leadpilot_ai.sales_pipeline_api import SalesOutcome
from leadpilot_ai.crm_store import Base, Conversation
from leadpilot_ai.appointment_booking import Appointment


class SalesInsightsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.patcher = patch.object(insights, 'SessionLocal', self.Session)
        self.patcher.start()
        app = FastAPI()
        app.include_router(insights.router)
        self.client = TestClient(app)
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.cid = str(uuid4())
        self.a, self.b = str(uuid4()), str(uuid4())
        with self.Session() as db:
            db.add(Conversation(id=self.cid))
            for i, rid in enumerate((self.a, self.b)):
                db.add(Appointment(request_id=rid, conversation_id=self.cid, calendar_event_id=f'meeting{i}',
                                   start_at=(self.now-timedelta(days=2)).isoformat(),
                                   end_at=(self.now-timedelta(days=2)+timedelta(minutes=30)).isoformat()))
            db.commit()

    def tearDown(self):
        self.patcher.stop()
        self.engine.dispose()

    def record(self, request_id, outcome, follow_up=None, value=None, updated=None):
        with self.Session() as db:
            db.add(SalesOutcome(request_id=request_id, completed_at=self.now.isoformat(),
                                meeting_notes='Demo', outcome=outcome, follow_up_at=follow_up,
                                deal_value=value, updated_at=updated or self.now.isoformat()))
            db.commit()

    def overview(self):
        with self.Session() as db:
            return insights.build_sales_overview(db, now=self.now)

    def test_endpoint_returns_no_side_effects(self):
        before = self.overview()
        response = self.client.get('/api/sales/overview')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['analytics']['distinct_opportunities'], 1)
        self.assertEqual(self.overview()['analytics'], before['analytics'])

    def test_two_appointments_one_opportunity(self):
        a = self.overview()['analytics']
        self.assertEqual((a['booked_appointments'], a['distinct_opportunities']), (2, 1))
        self.assertEqual(a['meeting_completion_percent'], 0)

    def test_due_followup_deduplicated_by_lead(self):
        self.record(self.a, 'Follow-up Required', (self.now-timedelta(minutes=1)).isoformat())
        d = self.overview()
        self.assertEqual(d['reminders']['due_count'], 1)
        self.assertEqual(d['reminders']['due'][0]['appointment_count'], 2)
        self.assertEqual(d['analytics']['follow_up_required'], 1)

    def test_upcoming_within_seven_days_only(self):
        self.record(self.a, 'Follow-up Required', (self.now+timedelta(days=2)).isoformat())
        self.assertEqual(self.overview()['reminders']['upcoming_count'], 1)
        self.assertEqual(self.overview()['reminders']['due_count'], 0)

    def test_future_followup_beyond_week_not_displayed(self):
        self.record(self.a, 'Follow-up Required', (self.now+timedelta(days=8)).isoformat())
        self.assertEqual(self.overview()['reminders']['upcoming_count'], 0)
        self.assertEqual(self.overview()['analytics']['follow_up_required'], 1)

    def test_won_not_reminded_and_counted_once(self):
        self.record(self.a, 'Won', value=Decimal('45000.00'))
        metrics = self.overview()
        self.assertEqual(metrics['analytics']['won'], 1)
        self.assertEqual(metrics['analytics']['won_deal_value_inr'], '45000.00')
        self.assertEqual(metrics['analytics']['average_won_deal_inr'], '45000.00')
        self.assertEqual(metrics['reminders']['due_count'], 0)
        self.assertEqual(metrics['analytics']['meeting_completion_percent'], 50.0)
        self.assertEqual(metrics['analytics']['win_rate_decided_percent'], 100.0)

    def test_changed_followup_to_won_clears_alert(self):
        self.record(self.a, 'Follow-up Required', (self.now-timedelta(hours=1)).isoformat())
        self.assertEqual(self.overview()['reminders']['due_count'], 1)
        with self.Session() as db:
            row = db.get(SalesOutcome, self.a)
            row.outcome = 'Won'; row.follow_up_at = None; row.deal_value = Decimal('1250')
            db.commit()
        self.assertEqual(self.overview()['reminders']['due_count'], 0)
        self.assertEqual(self.overview()['analytics']['won_deal_value_inr'], '1250.00')

    def test_old_duplicate_outcomes_not_double_counted(self):
        self.record(self.a, 'Won', value=Decimal('1000'), updated='2026-01-01T00:00:00+00:00')
        self.record(self.b, 'Won', value=Decimal('5000'), updated='2026-02-01T00:00:00+00:00')
        a = self.overview()['analytics']
        self.assertEqual(a['historical_conflicts'], 1)
        self.assertEqual(a['won'], 1)
        self.assertEqual(a['won_deal_value_inr'], '5000.00')

    def test_invalid_legacy_followup_does_not_crash(self):
        self.record(self.a, 'Follow-up Required', 'broken-time')
        d = self.overview()
        self.assertEqual(d['analytics']['follow_up_required'], 1)
        self.assertEqual(d['reminders']['due_count'], 0)

    def test_decision_win_rate_uses_won_and_lost(self):
        cid2, rid2 = str(uuid4()), str(uuid4())
        with self.Session() as db:
            db.add(Conversation(id=cid2))
            db.add(Appointment(request_id=rid2, conversation_id=cid2, calendar_event_id='another',
                               start_at=self.now.isoformat(), end_at=self.now.isoformat()))
            db.commit()
        self.record(self.a, 'Won', value=Decimal('45000'))
        self.record(rid2, 'Lost')
        a = self.overview()['analytics']
        self.assertEqual(a['distinct_opportunities'], 2)
        self.assertEqual(a['win_rate_decided_percent'], 50.0)
        self.assertEqual(a['opportunity_to_won_percent'], 50.0)


if __name__ == '__main__':
    unittest.main()
