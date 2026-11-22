import unittest
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from leadpilot_twilio_gateway import create_gateway

TOKEN = "local-test-secret"
ACCOUNT = "AC" + "1" * 32
CALL = "CA" + "2" * 32
ORIGIN = "https://leadpilot.example"


class FakeBackend:
    def __init__(self):
        self.starts = 0
        self.messages = []

    async def start(self):
        self.starts += 1
        return "fake-conversation-id"

    async def chat(self, cid, message):
        self.messages.append((cid, message))
        return "Do you have an allocated budget?"


class GatherTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self._step = 0
        self.app = create_gateway(
            auth_token=TOKEN,
            account_sid=ACCOUNT,
            public_base_url=ORIGIN,
            gather_backend=self.backend
        )
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(
            self.client.__exit__, None, None, None
        )
        self.validator = RequestValidator(TOKEN)

    def post(self, route, extra=None, sign=True):
        auto_step = route == "/twilio/gather-turn"

        if auto_step:
            route += f"?step={self._step}"
        params = {
            "AccountSid": ACCOUNT,
            "CallSid": CALL
        }

        if extra:
            params.update(extra)

        headers = {}

        if sign:
            headers["X-Twilio-Signature"] = (
                self.validator.compute_signature(
                    ORIGIN + route, params
                )
            )

        result = self.client.post(
            route,
            data=params,
            headers=headers
        )

        if auto_step and result.status_code == 200:
            self._step += 1

        return result

    def test_unsigned_start_rejected(self):
        result = self.post(
            "/twilio/gather-start", sign=False
        )
        self.assertEqual(result.status_code, 403)
        self.assertEqual(self.backend.starts, 0)

    def test_signed_start_returns_gather(self):
        result = self.post("/twilio/gather-start")
        self.assertEqual(result.status_code, 200)

        root = ET.fromstring(result.text)
        gather = root.find("Gather")

        self.assertIsNotNone(gather)
        self.assertEqual(
            gather.attrib["input"], "speech"
        )
        self.assertEqual(self.backend.starts, 1)

    def test_speech_reaches_crm(self):
        self.post("/twilio/gather-start")

        result = self.post(
            "/twilio/gather-turn",
            {"SpeechResult": "I need a CRM"}
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(
            self.backend.messages,
            [("fake-conversation-id", "I need a CRM")]
        )

        self.assertIn(
            "allocated budget", result.text
        )

    def test_empty_speech_asks_to_repeat(self):
        self.post("/twilio/gather-start")

        result = self.post("/twilio/gather-turn")

        self.assertEqual(result.status_code, 200)
        self.assertIn(
            "say it again", result.text
        )
        self.assertEqual(self.backend.messages, [])

    def test_turn_requires_started_call(self):
        result = self.post(
            "/twilio/gather-turn",
            {"SpeechResult": "Hello"}
        )
        self.assertEqual(result.status_code, 409)

    def test_email_claim_blocked(self):
        from leadpilot_ai.twilio_gather_fallback import (
            safe_spoken_reply
        )

        text = safe_spoken_reply(
            "I've sent you a calendar link."
        )

        self.assertIn(
            "cannot send emails", text
        )

    def test_fourth_turn_keeps_listening(self):
        from xml.etree import ElementTree as ET

        self.post("/twilio/gather-start")

        for index in range(4):
            result = self.post(
                "/twilio/gather-turn",
                {"SpeechResult": f"Answer {index}"}
            )

        root = ET.fromstring(result.text)

        self.assertIsNotNone(root.find("Gather"))
        self.assertEqual(len(self.backend.messages), 4)

    def test_six_turn_limit(self):
        from xml.etree import ElementTree as ET

        self.post("/twilio/gather-start")

        for index in range(6):
            result = self.post(
                "/twilio/gather-turn",
                {"SpeechResult": f"Answer {index}"}
            )

        root = ET.fromstring(result.text)

        self.assertIsNone(root.find("Gather"))
        self.assertIsNotNone(root.find("Hangup"))
        self.assertEqual(len(self.backend.messages), 6)




    def test_duplicate_callback_cached(self):
        self.post("/twilio/gather-start")

        url = "/twilio/gather-turn?step=0"
        speech = {"SpeechResult": "I need a CRM"}

        first = self.post(url, speech)
        retry = self.post(url, speech)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(first.text, retry.text)
        self.assertEqual(len(self.backend.messages), 1)
        self.assertIn("step=1", first.text)

    def test_same_words_next_step_allowed(self):
        self.post("/twilio/gather-start")

        speech = {"SpeechResult": "Yes"}

        self.post(
            "/twilio/gather-turn?step=0", speech
        )
        second = self.post(
            "/twilio/gather-turn?step=1", speech
        )

        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(self.backend.messages), 2)

    def test_changed_retry_rejected(self):
        self.post("/twilio/gather-start")

        self.post(
            "/twilio/gather-turn?step=0",
            {"SpeechResult": "First answer"}
        )

        changed = self.post(
            "/twilio/gather-turn?step=0",
            {"SpeechResult": "Different answer"}
        )

        self.assertEqual(changed.status_code, 409)
        self.assertEqual(len(self.backend.messages), 1)

    def test_future_step_rejected(self):
        self.post("/twilio/gather-start")

        result = self.post(
            "/twilio/gather-turn?step=3",
            {"SpeechResult": "Hello"}
        )

        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.backend.messages, [])

    def test_missing_step_rejected(self):
        self.post("/twilio/gather-start")

        params = {
            "AccountSid": ACCOUNT,
            "CallSid": CALL,
            "SpeechResult": "Hello"
        }

        signature = self.validator.compute_signature(
            ORIGIN + "/twilio/gather-turn",
            params
        )

        result = self.client.post(
            "/twilio/gather-turn",
            data=params,
            headers={
                "X-Twilio-Signature": signature
            }
        )

        self.assertEqual(result.status_code, 403)

    def test_empty_callback_retry_cached(self):
        self.post("/twilio/gather-start")

        url = "/twilio/gather-turn?step=0"

        first = self.post(url)
        retry = self.post(url)

        self.assertEqual(first.text, retry.text)
        self.assertIn("step=1", first.text)

        next_turn = self.post(
            "/twilio/gather-turn?step=1",
            {"SpeechResult": "Hello"}
        )

        self.assertEqual(next_turn.status_code, 200)
        self.assertEqual(len(self.backend.messages), 1)


class SpokenReplyQualityTests(unittest.TestCase):

    def test_unfinished_question_removed(self):
        from leadpilot_ai.twilio_gather_fallback import (
            safe_spoken_reply
        )

        reply = safe_spoken_reply(
            "Our CRM requirements are confirmed. Would you"
        )

        self.assertEqual(
            reply,
            "Our CRM requirements are confirmed."
        )

    def test_markdown_removed(self):
        from leadpilot_ai.twilio_gather_fallback import (
            safe_spoken_reply
        )

        reply = safe_spoken_reply(
            "Summary: - **Budget:** 50000 INR. "
            "- **Timeline:** Within 30 days."
        )

        self.assertNotIn("**", reply)
        self.assertIn("Budget:", reply)
        self.assertIn("Timeline:", reply)
        self.assertTrue(reply.endswith("."))

    def test_final_goodbye_clean(self):
        from unittest.mock import AsyncMock
        from xml.etree import ElementTree as ET

        backend = FakeBackend()
        backend.chat = AsyncMock(
            return_value=(
                "Your CRM requirements are recorded. "
                "Would you"
            )
        )

        app = create_gateway(
            auth_token=TOKEN,
            account_sid=ACCOUNT,
            public_base_url=ORIGIN,
            gather_backend=backend
        )

        validator = RequestValidator(TOKEN)

        with TestClient(app) as client:
            for index in range(7):
                route = (
                    "/twilio/gather-start"
                    if index == 0
                    else f"/twilio/gather-turn?step={index - 1}"
                )

                params = {
                    "AccountSid": ACCOUNT,
                    "CallSid": CALL
                }

                if index:
                    params["SpeechResult"] = "Test response"

                sig = validator.compute_signature(
                    ORIGIN + route, params
                )

                result = client.post(
                    route,
                    data=params,
                    headers={"X-Twilio-Signature": sig}
                )

                self.assertEqual(result.status_code, 200)

            final = ET.fromstring(result.text)
            spoken = final.findtext("Say")

            self.assertIsNotNone(spoken)
            self.assertNotIn("Would you", spoken)
            self.assertTrue(
                spoken.endswith(
                    "Thank you for calling. Goodbye."
                )
            )
            self.assertLessEqual(len(spoken), 300)


# LeadPilot spoken reply quality v1

if __name__ == "__main__":
    unittest.main()

# LeadPilot numbered callback replay protection v1
