import unittest

from leadpilot_ai.voice_booking_commands import (
    is_confirmation, is_cancel,
    is_schedule_request, spoken_slot
)


class VoiceBookingCommandTests(unittest.TestCase):

    def test_explicit_confirmation(self):
        self.assertTrue(
            is_confirmation("Yes, confirm the booking.")
        )

    def test_yes_please_is_not_confirmation(self):
        self.assertFalse(
            is_confirmation("Yes, please.")
        )

    def test_cancel_command(self):
        self.assertTrue(is_cancel("Cancel booking."))

    def test_schedule_intent(self):
        self.assertTrue(
            is_schedule_request(
                "Can we schedule a consultation tomorrow?"
            )
        )

    def test_slot_timezone(self):
        result = spoken_slot(
            "2026-11-23T11:00:00+05:30"
        )
        self.assertIn("11:00 AM IST", result)




class VoiceBookingRegressionTests(unittest.TestCase):

    def test_asr_consultant_variant(self):
        from leadpilot_ai.voice_booking_commands import (
            is_schedule_request
        )

        self.assertTrue(is_schedule_request(
            "Can we schedule consultant at 11:00 a.m.? Tomorrow"
        ))

    def test_schedule_without_meeting_noun(self):
        from leadpilot_ai.voice_booking_commands import (
            is_schedule_request
        )

        self.assertTrue(is_schedule_request(
            "Can we schedule tomorrow at 11 AM?"
        ))

    def test_unrelated_statement(self):
        from leadpilot_ai.voice_booking_commands import (
            is_schedule_request
        )

        self.assertFalse(is_schedule_request(
            "I need a CRM for my business"
        ))

    def test_email_delivery_guard(self):
        from leadpilot_ai.voice_booking_commands import (
            guard_email_delivery_reply
        )

        response, guarded = guard_email_delivery_reply(
            "I've sent a calendar link. Check your inbox."
        )

        self.assertTrue(guarded)
        self.assertIn("No email", response)

    def test_email_input(self):
        from leadpilot_ai.voice_booking_commands import (
            is_email_input
        )

        self.assertTrue(is_email_input(
            "My email address is test@example.com"
        ))


# LeadPilot voice scheduling safety patch v1

if __name__ == "__main__":
    unittest.main()
