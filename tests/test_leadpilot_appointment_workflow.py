import unittest
from datetime import date
from unittest.mock import MagicMock, patch
from uuid import UUID
from types import SimpleNamespace

from fastapi import HTTPException

from leadpilot_ai.appointment_workflow import (
    appointment_options, select_slot_options
)


ID = UUID("d94cb505-afe7-45e6-b1f8-a9ec5ffbb66d")


class AppointmentWorkflowTests(unittest.TestCase):

    def test_slot_limit(self):
        slots = [1, 2, 3, 4, 5]
        self.assertEqual(
            select_slot_options(slots, 3),
            [1, 2, 3]
        )

    @patch("leadpilot_ai.appointment_workflow.check_availability")
    @patch("leadpilot_ai.appointment_workflow.SessionLocal")
    def test_hot_lead_gets_slots(self, session_factory, availability):
        db = MagicMock()
        session_factory.return_value.__enter__.return_value = db

        db.get.side_effect = [
            object(),
            SimpleNamespace(category="Hot", score=100)
        ]

        availability.return_value = {
            "available_count": 2,
            "available_slots": [
                {"start": "10:30", "end": "11:00"},
                {"start": "11:00", "end": "11:30"}
            ]
        }

        result = appointment_options(
            ID, date(2026, 11, 23), limit=1
        )

        self.assertEqual(result["lead_score"], 100)
        self.assertEqual(len(result["suggested_slots"]), 1)
        self.assertFalse(result["booking_created"])

    @patch("leadpilot_ai.appointment_workflow.check_availability")
    @patch("leadpilot_ai.appointment_workflow.SessionLocal")
    def test_incomplete_lead_rejected(
        self, session_factory, availability
    ):
        db = MagicMock()
        session_factory.return_value.__enter__.return_value = db

        db.get.side_effect = [
            object(),
            SimpleNamespace(category="Incomplete", score=25)
        ]

        with self.assertRaises(HTTPException) as caught:
            appointment_options(
                ID, date(2026, 11, 23), limit=5
            )

        self.assertEqual(caught.exception.status_code, 409)
        availability.assert_not_called()


if __name__ == "__main__":
    unittest.main()
