"""Regression checks: multiple appointments are one business opportunity per conversation.

Runs against an isolated in-memory SQLite database. No live API calls.
"""
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from leadpilot_ai import sales_pipeline_api as sales
from leadpilot_ai.crm_store import Base, Conversation, LeadProfile
from leadpilot_ai.appointment_booking import Appointment


class OpportunityDedupTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool,
                                    connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.patcher = patch.object(sales, 'SessionLocal', self.Session)
        self.patcher.start()
        app = FastAPI()
        app.include_router(sales.router)
        self.client = TestClient(app)
        self.cid = str(uuid4())
        self.a = str(uuid4())
        self.b = str(uuid4())
        past = datetime.now(timezone.utc) - timedelta(days=3)
        with self.Session() as db:
            db.add(Conversation(id=self.cid))
            db.add(LeadProfile(conversation_id=self.cid, score=100, category='Hot'))
            for i, bid in enumerate((self.a, self.b)):
                db.add(Appointment(request_id=bid, conversation_id=self.cid,
                                   calendar_event_id=f'dedup{i}',
                                   start_at=(past + timedelta(minutes=60*i)).isoformat(),
                                   end_at=(past + timedelta(minutes=60*i+30)).isoformat()))
            db.commit()

    def tearDown(self):
        self.patcher.stop()
        self.engine.dispose()

    def complete(self, bid):
        return self.client.post(f'/api/sales/appointments/{bid}/complete',
                                json={'meeting_notes': 'Completed product demo'})

    def outcome(self, bid, result, **kw):
        return self.client.patch(f'/api/sales/appointments/{bid}/outcome',
                                 json={'outcome': result, **kw})

    def pipeline(self):
        response = self.client.get('/api/sales/pipeline')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_two_meetings_one_opportunity(self):
        data = self.pipeline()
        self.assertEqual(data['summary']['booked'], 2)
        self.assertEqual(data['summary']['opportunities'], 1)
        self.assertEqual(data['summary']['won'], 0)
        self.assertEqual([row['opportunity_appointment_count'] for row in data['appointments']], [2, 2])

    def test_sibling_won_cannot_be_recorded_twice(self):
        self.assertEqual(self.complete(self.a).status_code, 200)
        self.assertEqual(self.complete(self.b).status_code, 200)
        self.assertEqual(self.outcome(self.a, 'Won', deal_value='45000.00').status_code, 200)
        denied = self.outcome(self.b, 'Won', deal_value='90000.00')
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertIn(self.a, denied.json()['detail'])
        data = self.pipeline()
        self.assertEqual(data['summary']['completed'], 2)
        self.assertEqual(data['summary']['won'], 1)
        self.assertEqual(data['summary']['won_revenue_inr'], '45000.00')
        self.assertEqual(data['summary']['pending_outcome'], 0)
        self.assertEqual(data['summary']['opportunity_conflicts'], 0)
        for row in data['appointments']:
            self.assertEqual(row['opportunity_owner_request_id'], self.a)
            self.assertEqual(row['opportunity_outcome'], 'Won')

    def test_sibling_conflicting_lost_rejected(self):
        self.complete(self.a)
        self.complete(self.b)
        self.outcome(self.a, 'Won', deal_value='45000')
        response = self.outcome(self.b, 'Lost', lost_reason='Chose another provider')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.pipeline()['summary']['lost'], 0)

    def test_owner_can_change_followup_to_won(self):
        self.complete(self.a)
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.assertEqual(self.outcome(self.a, 'Follow-up Required', follow_up_at=tomorrow).status_code, 200)
        self.assertEqual(self.outcome(self.a, 'Won', deal_value='12000.00').status_code, 200)
        data = self.pipeline()['summary']
        self.assertEqual(data['won'], 1)
        self.assertEqual(data['follow_up_required'], 0)
        self.assertEqual(data['won_revenue_inr'], '12000.00')

    def test_different_conversations_count_as_separate_deals(self):
        second = str(uuid4())
        bid = str(uuid4())
        past = datetime.now(timezone.utc) - timedelta(days=1)
        with self.Session() as db:
            db.add(Conversation(id=second))
            db.add(Appointment(request_id=bid, conversation_id=second,
                               calendar_event_id='unrelated', start_at=past.isoformat(),
                               end_at=(past + timedelta(minutes=30)).isoformat()))
            db.commit()
        self.complete(self.a)
        self.complete(bid)
        self.assertEqual(self.outcome(self.a, 'Won', deal_value='45000').status_code, 200)
        self.assertEqual(self.outcome(bid, 'Won', deal_value='5000').status_code, 200)
        data = self.pipeline()['summary']
        self.assertEqual(data['opportunities'], 2)
        self.assertEqual(data['won'], 2)
        self.assertEqual(data['won_revenue_inr'], '50000.00')

    def test_old_duplicate_rows_are_reported_not_double_counted(self):
        self.complete(self.a)
        self.complete(self.b)
        # Emulate legacy data created before the duplicate-outcome restriction.
        with self.Session() as db:
            left = db.get(sales.SalesOutcome, self.a)
            right = db.get(sales.SalesOutcome, self.b)
            left.outcome = right.outcome = 'Won'
            left.deal_value = right.deal_value = 1000
            left.updated_at = '2026-01-01T00:00:00+00:00'
            right.updated_at = '2026-02-01T00:00:00+00:00'
            db.commit()
        data = self.pipeline()
        self.assertEqual(data['summary']['won'], 1)
        self.assertEqual(data['summary']['won_revenue_inr'], '1000.00')
        self.assertEqual(data['summary']['opportunity_conflicts'], 1)
        self.assertEqual(data['appointments'][0]['opportunity_owner_request_id'], self.b)


if __name__ == '__main__':
    unittest.main()
