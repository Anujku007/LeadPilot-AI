"""Offline regression cases for LeadPilot chat intent and qualification.

No NVIDIA, Google Calendar, or real CRM calls are made by this test module.
"""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from leadpilot_ai.smart_conversation import (
    AUTHORITY_QUESTION, classify_booking_turn, missing_question,
    recover_explicit_authority,
)
from leadpilot_ai.qualification_flow import merge_qualification


class ConversationIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.blank = merge_qualification({}, {})
        self.complete = merge_qualification({}, {
            'budget': 'confirmed', 'authority': 'decision_maker',
            'need': 'clear', 'timeline': 'within_30_days',
        })

    def test_authority_not_inferred_from_software_users(self):
        result = recover_explicit_authority(self.blank, [
            'Our sales and customer relationship management teams use the CRM.',
            'We have 12 employees and 5 daily users.',
        ])
        self.assertEqual(result['extracted']['authority'], 'unknown')

    def test_authority_recognized_from_explicit_owner_statement(self):
        result = recover_explicit_authority(self.blank, [
            "I'm the company owner and final decision maker."
        ])
        self.assertEqual(result['extracted']['authority'], 'decision_maker')
        self.assertIn('authority', result['breakdown'])

    def test_explicit_purchase_approval_recognized(self):
        result = recover_explicit_authority(self.blank, [
            'I can approve the purchase myself.'
        ])
        self.assertEqual(result['extracted']['authority'], 'decision_maker')

    def test_owner_of_someone_elses_company_not_accepted(self):
        result = recover_explicit_authority(self.blank, [
            'I will ask the owner of the company to approve it.'
        ])
        self.assertEqual(result['extracted']['authority'], 'unknown')

    def test_authority_question_explicitly_about_purchase(self):
        values = merge_qualification({}, {
            'budget':'confirmed', 'need':'clear', 'timeline':'within_30_days'
        })
        self.assertEqual(missing_question(values), AUTHORITY_QUESTION)
        self.assertIn('approve', missing_question(values))
        self.assertNotIn('department', missing_question(values))

    def test_full_bant_needs_no_more_questions(self):
        self.assertIsNone(missing_question(self.complete))

    def test_unqualified_cannot_request_slot(self):
        self.assertEqual(classify_booking_turn(
            'Wednesday November 25, 2026 at 11:00 AM', [], False
        ), 'none')

    def test_explicit_date_and_clock_triggers_slot_check(self):
        self.assertEqual(classify_booking_turn(
            'Can we do Wednesday, 25 November 2026 at 11:00 a.m.?', [], True
        ), 'check')

    def test_verbal_date_and_clock_triggers_slot_check(self):
        self.assertEqual(classify_booking_turn(
            'Wednesday November 25 at eleven in the morning', [], True
        ), 'check')

    def test_numeric_spoken_clock_triggers_slot_check(self):
        self.assertEqual(classify_booking_turn(
            'Wednesday November 25 at 11 in the morning', [], True
        ), 'check')

    def test_timeline_not_confused_with_appointment(self):
        self.assertEqual(classify_booking_turn(
            'We want to implement the software within three weeks', [], True
        ), 'none')

    def test_acceptance_of_consultation_asks_for_preferred_time(self):
        self.assertEqual(classify_booking_turn(
            'Yes, that would be helpful.',
            [{'role':'assistant','content':'Would you like to schedule a 30-minute consultation?'}],
            True
        ), 'ask_time')

    def test_meeting_without_time_prompts_for_time(self):
        self.assertEqual(classify_booking_turn(
            'I would like to book a consultation.', [], True
        ), 'ask_time')

    def test_spoken_confirmation_does_not_book(self):
        self.assertEqual(classify_booking_turn(
            'Yes, confirm the appointment at that time.', [], True
        ), 'confirm_ui')

    def test_non_scheduling_reply_no_action(self):
        self.assertEqual(classify_booking_turn('I manage 12 employees', [], True), 'none')


class PendingBookingReadOnlyTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from leadpilot_ai.crm_store import Base, Conversation
        from leadpilot_ai.appointment_confirmation import AppointmentProposal
        from leadpilot_ai.appointment_booking import Appointment
        from leadpilot_ai import smart_conversation
        from uuid import uuid4
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.mock_session = patch.object(smart_conversation, 'SessionLocal', self.Session)
        self.mock_session.start()
        self.cid = str(uuid4())
        self.pid = str(uuid4())
        with self.Session() as db:
            db.add(Conversation(id=self.cid))
            db.commit()
        self.Proposal = AppointmentProposal
        self.Appointment = Appointment
        self.smart = smart_conversation

    def tearDown(self):
        self.mock_session.stop()
        self.engine.dispose()

    def _create_proposal(self, expires):
        with self.Session() as db:
            db.add(self.Proposal(
                id=self.pid, conversation_id=self.cid,
                start_at='2030-11-25T11:00:00+05:30', expires_at=expires
            ))
            db.commit()

    def test_missing_conversation_404(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.smart.current_booking_state('00000000-0000-0000-0000-000000000000')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_pending_proposal_survives_reload_without_booking(self):
        self._create_proposal((datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
        current = self.smart.current_booking_state(self.cid)
        self.assertEqual(current['proposal']['proposal_id'], self.pid)
        self.assertFalse(current['booking_created'])
        # The endpoint is read-only; it never writes a Google Calendar event.
        with self.Session() as db:
            self.assertIsNone(db.get(self.Appointment, self.pid))

    def test_expired_proposal_not_returned(self):
        self._create_proposal((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
        current = self.smart.current_booking_state(self.cid)
        self.assertIsNone(current['proposal'])

    def test_existing_booking_does_not_leak_as_pending(self):
        self._create_proposal((datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
        with self.Session() as db:
            db.add(self.Appointment(
                request_id=self.pid, conversation_id=self.cid,
                calendar_event_id='lp-test-event', start_at='2030-11-25T11:00:00+05:30',
                end_at='2030-11-25T11:30:00+05:30'
            ))
            db.commit()
        current = self.smart.current_booking_state(self.cid)
        self.assertIsNone(current['proposal'])
        self.assertTrue(current['booking_created'])
        self.assertTrue(self.smart.has_saved_booking(self.cid))


if __name__ == '__main__':
    unittest.main()
