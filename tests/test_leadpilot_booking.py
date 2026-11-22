import unittest
from uuid import UUID
from datetime import datetime

from leadpilot_ai.appointment_booking import (
    IST, validate_slot, make_event_id
)


class BookingTests(unittest.TestCase):

    def setUp(self):
        self.now = datetime(
            2026, 11, 22, 12, 0, tzinfo=IST
        )

    def test_valid_slot(self):
        start = datetime(
            2026, 11, 23, 10, 0, tzinfo=IST
        )
        actual, end = validate_slot(
            start, now=self.now
        )
        self.assertEqual(end.hour, 10)
        self.assertEqual(end.minute, 30)

    def test_weekend_rejected(self):
        start = datetime(
            2026, 11, 28, 10, 0, tzinfo=IST
        )
        with self.assertRaises(ValueError):
            validate_slot(start, now=self.now)

    def test_invalid_time_rejected(self):
        start = datetime(
            2026, 11, 23, 18, 0, tzinfo=IST
        )
        with self.assertRaises(ValueError):
            validate_slot(start, now=self.now)

    def test_naive_time_rejected(self):
        start = datetime(2026, 11, 23, 10, 0)
        with self.assertRaises(ValueError):
            validate_slot(start, now=self.now)

    def test_idempotency_id(self):
        request_id = UUID(
            "12345678-1234-1234-1234-123456789abc"
        )
        event_id = make_event_id(request_id)
        self.assertEqual(
            event_id,
            make_event_id(request_id)
        )
        self.assertTrue(
            set(event_id) <= set(
                "0123456789abcdefghijklmnopqrstuv"
            )
        )


if __name__ == "__main__":
    unittest.main()
