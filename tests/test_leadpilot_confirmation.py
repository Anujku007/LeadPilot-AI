import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from leadpilot_ai.appointment_confirmation import (
    ConfirmationRequest, is_expired,
    propose_appointment, ProposalRequest
)
from leadpilot_ai.calendar_availability import IST


class ConfirmationTests(unittest.TestCase):

    def test_unconfirmed_request_rejected(self):
        with self.assertRaises(ValidationError):
            ConfirmationRequest(
                proposal_id=uuid4(),
                confirmation_text="yes"
            )

    def test_expired_proposal(self):
        expiry = (
            datetime.now(timezone.utc)
            - timedelta(minutes=1)
        ).isoformat()

        self.assertTrue(is_expired(expiry))

    def test_active_proposal(self):
        expiry = (
            datetime.now(timezone.utc)
            + timedelta(minutes=15)
        ).isoformat()

        self.assertFalse(is_expired(expiry))

    @patch(
        "leadpilot_ai.appointment_confirmation.preview_appointment"
    )
    @patch(
        "leadpilot_ai.appointment_confirmation.SessionLocal"
    )
    def test_proposal_does_not_book(
        self, session_factory, preview
    ):
        db = MagicMock()
        session_factory.return_value.__enter__.return_value = db

        db.get.side_effect = [
            object(),
            SimpleNamespace(category="Hot", score=100)
        ]

        preview.return_value = {
            "available": True
        }

        future = (
            datetime.now(IST) + timedelta(days=7)
        ).replace(
            hour=11, minute=0,
            second=0, microsecond=0
        )

        # Find a valid weekday
        while future.weekday() >= 5:
            future += timedelta(days=1)

        result = propose_appointment(
            uuid4(),
            ProposalRequest(start=future)
        )

        self.assertFalse(result["booking_created"])
        self.assertTrue(result["confirmation_required"])
        preview.assert_called_once()


if __name__ == "__main__":
    unittest.main()
