"""Post-appointment CRM stages with an isolated SQLite database.

No Google Calendar calls, real customer data, or NVIDIA tokens required.
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


class SalesPipelineTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool,
                                    connect_args={'check_same_thread': False})
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.patch = patch.object(sales, 'SessionLocal', self.Session)
        self.patch.start()
        app = FastAPI()
        app.include_router(sales.router)
        self.client = TestClient(app)
        self.cid = str(uuid4())
        self.bid = str(uuid4())
        self.future_bid = str(uuid4())
        past = datetime.now(timezone.utc) - timedelta(days=2)
        future = datetime.now(timezone.utc) + timedelta(days=2)
        with self.Session() as db:
            db.add(Conversation(id=self.cid))
            db.add(LeadProfile(conversation_id=self.cid, budget='confirmed', authority='confirmed',
                               need='confirmed', timeline='confirmed', score=100, category='Hot'))
            db.add_all([
                Appointment(request_id=self.bid, conversation_id=self.cid,
                            calendar_event_id='event1', start_at=past.isoformat(),
                            end_at=(past + timedelta(minutes=30)).isoformat()),
                Appointment(request_id=self.future_bid, conversation_id=self.cid,
                            calendar_event_id='event2', start_at=future.isoformat(),
                            end_at=(future + timedelta(minutes=30)).isoformat()),
            ])
            db.commit()

    def tearDown(self):
        self.patch.stop()
        self.engine.dispose()

    def url(self, request_id=None, action='complete'):
        return f'/api/sales/appointments/{request_id or self.bid}/{action}'

    def complete(self, notes='Demonstrated the software'):
        return self.client.post(self.url(), json={'meeting_notes': notes})

    def test_bookings_visible_without_creating_outcome_records(self):
        result = self.client.get('/api/sales/pipeline')
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()
        self.assertEqual(data['summary']['booked'], 2)
        self.assertEqual(data['summary']['completed'], 0)
        self.assertEqual(data['summary']['won_revenue_inr'], '0.00')
        self.assertTrue(all(x['meeting_status'] == 'Booked' for x in data['appointments']))
        with self.Session() as db:
            self.assertEqual(db.query(sales.SalesOutcome).count(), 0)

    def test_missing_booking_and_invalid_uuid_rejected(self):
        self.assertEqual(self.client.post(self.url(str(uuid4())), json={}).status_code, 404)
        self.assertEqual(self.client.post(self.url('bad-id'), json={}).status_code, 422)
        self.assertEqual(self.client.patch(self.url(str(uuid4()), 'outcome'), json={
            'outcome': 'Won', 'deal_value': '5000.00'}).status_code, 404)

    def test_future_meeting_cannot_be_completed(self):
        response = self.client.post(self.url(self.future_bid), json={'meeting_notes': 'No meeting yet'})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.client.get('/api/sales/pipeline').json()['summary']['completed'], 0)

    def test_completion_idempotent_notes_and_history(self):
        self.assertEqual(self.complete('Initial demo').status_code, 200)
        again = self.complete('Initial demo')
        self.assertEqual(again.status_code, 200)
        updated = self.complete('Discussed integrations')
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()['meeting_notes'], 'Discussed integrations')
        pipeline = self.client.get('/api/sales/pipeline').json()
        self.assertEqual(pipeline['summary']['completed'], 1)
        self.assertEqual(pipeline['summary']['pending_outcome'], 1)
        activities = self.client.get(self.url(action='history')).json()['activities']
        self.assertEqual([a['event'] for a in activities], ['notes_updated','meeting_completed'])

    def test_outcome_requires_completion(self):
        response = self.client.patch(self.url(action='outcome'), json={'outcome': 'Won', 'deal_value': '1000.00'})
        self.assertEqual(response.status_code, 409, response.text)

    def test_valid_won_records_revenue(self):
        self.complete()
        response = self.client.patch(self.url(action='outcome'), json={'outcome': 'Won', 'deal_value': '45000.50'})
        self.assertEqual(response.status_code, 200, response.text)
        data = self.client.get('/api/sales/pipeline').json()
        self.assertEqual(data['summary']['won'], 1)
        self.assertEqual(data['summary']['won_revenue_inr'], '45000.50')
        self.assertEqual(next(x for x in data['appointments'] if x['request_id'] == self.bid)['deal_value'], '45000.50')

    def test_won_requires_positive_amount_and_rejects_excess_decimals(self):
        self.complete()
        for amount in ['0', '-20', '1.234', '99999999999999']:
            response = self.client.patch(self.url(action='outcome'), json={'outcome': 'Won', 'deal_value': amount})
            self.assertEqual(response.status_code, 422, (amount, response.text))
        self.assertEqual(self.client.get('/api/sales/pipeline').json()['summary']['won'], 0)

    def test_follow_up_date_required_and_must_be_future_timezone_aware(self):
        self.complete()
        for payload in [
            {'outcome': 'Follow-up Required'},
            {'outcome': 'Follow-up Required', 'follow_up_at': '2040-05-05T10:00:00'},
            {'outcome': 'Follow-up Required', 'follow_up_at': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
        ]:
            response = self.client.patch(self.url(action='outcome'), json=payload)
            self.assertEqual(response.status_code, 422, response.text)
        future = datetime.now(timezone.utc) + timedelta(days=4)
        response = self.client.patch(self.url(action='outcome'), json={
            'outcome': 'Follow-up Required', 'follow_up_at': future.isoformat()})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get('/api/sales/pipeline').json()['summary']['follow_up_required'], 1)

    def test_lost_requires_reason(self):
        self.complete()
        self.assertEqual(self.client.patch(self.url(action='outcome'),json={'outcome':'Lost'}).status_code, 422)
        self.assertEqual(self.client.patch(self.url(action='outcome'),json={
            'outcome':'Lost', 'lost_reason':'Customer chose another vendor'}).status_code, 200)
        self.assertEqual(self.client.get('/api/sales/pipeline').json()['summary']['lost'], 1)

    def test_follow_up_can_transition_to_won_and_clear_old_fields(self):
        self.complete()
        date = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        self.assertEqual(self.client.patch(self.url(action='outcome'),json={
            'outcome':'Follow-up Required','follow_up_at':date}).status_code,200)
        self.assertEqual(self.client.patch(self.url(action='outcome'),json={
            'outcome':'Won','deal_value':'35000'}).status_code,200)
        details = self.client.get('/api/sales/pipeline').json()
        self.assertEqual(details['summary']['follow_up_required'], 0)
        self.assertEqual(details['summary']['won'], 1)
        row = next(x for x in details['appointments'] if x['request_id']==self.bid)
        self.assertIsNone(row['follow_up_at'])
        events = self.client.get(self.url(action='history')).json()['activities']
        self.assertEqual(events[0]['description'], 'Outcome: Follow-up Required → Won')

    def test_bad_outcome_and_extraneous_fields_rejected(self):
        self.complete()
        for payload in [
            {'outcome':'Sold','deal_value':'100'},
            {'outcome':'Won','deal_value':'100','follow_up_at':(datetime.now(timezone.utc) + timedelta(days=3)).isoformat()},
            {'outcome':'Lost','lost_reason':'No budget','deal_value':'100'},
        ]:
            self.assertEqual(self.client.patch(self.url(action='outcome'),json=payload).status_code, 422)

    def test_notes_length_limit(self):
        self.assertEqual(self.complete('a' * 4001).status_code, 422)

if __name__ == '__main__':
    unittest.main()
