import unittest

from leadpilot_ai.qualification_flow import (
    merge_qualification,
    prompt_for_lead
)


class QualificationFlowTests(unittest.TestCase):

    def test_incomplete_lead(self):
        result = merge_qualification(
            {}, {"need": "clear"}
        )
        self.assertEqual(result["score"], 25)
        self.assertEqual(result["category"], "Incomplete")
        self.assertEqual(
            result["missing_fields"][0], "budget"
        )

    def test_previous_information_preserved(self):
        result = merge_qualification(
            {"need": "clear"},
            {
                "budget": "confirmed",
                "authority": "decision_maker",
                "timeline": "within_30_days"
            }
        )
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["category"], "Hot")

    def test_unknown_does_not_erase_known_data(self):
        result = merge_qualification(
            {"budget": "confirmed"},
            {"budget": "unknown"}
        )
        self.assertEqual(
            result["extracted"]["budget"],
            "confirmed"
        )

    def test_appointment_offer(self):
        result = merge_qualification(
            {},
            {
                "budget": "confirmed",
                "authority": "decision_maker",
                "need": "clear",
                "timeline": "within_30_days"
            }
        )
        self.assertIsNone(result["next_question"])
        self.assertIn(
            "30-minute sales consultation",
            prompt_for_lead(result)
        )


if __name__ == "__main__":
    unittest.main()
