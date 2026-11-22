import unittest
from datetime import date, datetime, timedelta

from leadpilot_ai.calendar_availability import (
    IST, build_available_slots, parse_event_time
)


class CalendarAvailabilityTests(unittest.TestCase):

    def setUp(self):
        self.day = date(2026, 11, 23)
        self.now = datetime(
            2026, 11, 22, 12, 0, tzinfo=IST
        )

    def test_empty_calendar(self):
        slots = build_available_slots(
            self.day, [], self.now
        )
        self.assertEqual(len(slots), 16)

    def test_busy_calendar(self):
        start = datetime(
            2026, 11, 23, 10, 15, tzinfo=IST
        )
        end = start + timedelta(minutes=30)

        slots = build_available_slots(
            self.day, [(start, end)], self.now
        )
        self.assertEqual(len(slots), 14)

    def test_weekend(self):
        slots = build_available_slots(
            date(2026, 11, 22), [], self.now
        )
        self.assertEqual(slots, [])

    def test_all_day_event(self):
        start = parse_event_time({
            "date": "2026-11-23"
        })
        end = parse_event_time({
            "date": "2026-11-24"
        })

        slots = build_available_slots(
            self.day, [(start, end)], self.now
        )
        self.assertEqual(slots, [])

    def test_past_slots(self):
        now = datetime(
            2026, 11, 23, 12, 0, tzinfo=IST
        )
        slots = build_available_slots(
            self.day, [], now
        )

        self.assertTrue(all(
            datetime.fromisoformat(s["start"]) > now
            for s in slots
        ))


if __name__ == "__main__":
    unittest.main()
