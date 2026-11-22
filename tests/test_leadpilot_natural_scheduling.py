import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from leadpilot_ai.natural_language_scheduling import (
    IST, parse_schedule, schedule_request, ScheduleRequest
)


CID = UUID("d94cb505-afe7-45e6-b1f8-a9ec5ffbb66d")


class SchedulingTests(unittest.IsolatedAsyncioTestCase):

    def test_parse_valid_datetime(self):
        result = parse_schedule(
            '{"intent":"schedule",'
            '"date":"2026-11-23","time":"11:00"}'
        )
        self.assertEqual(
            result,
            datetime(2026, 11, 23, 11, 0, tzinfo=IST)
        )

    def test_ambiguous_request(self):
        result = parse_schedule(
            '{"intent":"unclear","date":null,"time":null}'
        )
        self.assertIsNone(result)

    def test_missing_time(self):
        result = parse_schedule(
            '{"intent":"schedule",'
            '"date":"2026-11-23","time":null}'
        )
        self.assertIsNone(result)

    async def test_creates_proposal_not_booking(self):
        with (
            patch(
                "leadpilot_ai.natural_language_scheduling.SessionLocal"
            ) as session,
            patch(
                "leadpilot_ai.natural_language_scheduling.nvidia.generate_response",
                new_callable=AsyncMock
            ) as llm,
            patch(
                "leadpilot_ai.natural_language_scheduling.propose_appointment"
            ) as propose
        ):
            db = MagicMock()
            session.return_value.__enter__.return_value = db

            db.get.side_effect = [
                object(),
                SimpleNamespace(category="Hot", score=100)
            ]

            llm.return_value = (
                '{"intent":"schedule",'
                '"date":"2026-11-23","time":"11:00"}'
            )

            propose.return_value = {
                "proposal_id": "test-proposal",
                "booking_created": False
            }

            response = await schedule_request(
                CID,
                ScheduleRequest(
                    message="Book November 23 at 11 AM IST"
                )
            )

            self.assertTrue(response["understood"])
            self.assertFalse(response["booking_created"])
            propose.assert_called_once()


if __name__ == "__main__":
    unittest.main()
