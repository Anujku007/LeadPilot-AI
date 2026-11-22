import base64
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from leadpilot_api import app
from leadpilot_ai.twilio_duplex_local import (
    SpeechSegmenter, extract_reply
)


CID = "26802eda-2815-48e0-ab48-0363d3f43078"


def packet(value):
    return {
        "event": "media",
        "streamSid": "MZDuplexTest",
        "media": {
            "track": "inbound",
            "payload": base64.b64encode(
                bytes([value] * 160)
            ).decode("ascii")
        }
    }


def start_packet():
    return {
        "event": "start",
        "streamSid": "MZDuplexTest",
        "start": {
            "streamSid": "MZDuplexTest",
            "mediaFormat": {
                "encoding": "audio/x-mulaw",
                "sampleRate": 8000,
                "channels": 1
            },
            "customParameters": {
                "conversation_id": CID
            }
        }
    }


class DuplexTests(unittest.TestCase):

    def test_reply_extraction(self):
        self.assertEqual(
            extract_reply({"reply": "Hello!"}),
            "Hello!"
        )

    def test_invalid_reply(self):
        with self.assertRaises(ValueError):
            extract_reply({})

    def test_silence_no_utterance(self):
        from leadpilot_ai.twilio_stream import (
            decode_mulaw_to_pcm16k
        )

        vad = SpeechSegmenter()

        for _ in range(60):
            completed = vad.feed(
                decode_mulaw_to_pcm16k(
                    packet(255)["media"]["payload"]
                )
            )

        self.assertIsNone(completed)

    def test_speech_then_silence(self):
        from leadpilot_ai.twilio_stream import (
            decode_mulaw_to_pcm16k
        )

        vad = SpeechSegmenter()
        completed = None

        for value in ([0] * 15 + [255] * 35):
            result = vad.feed(
                decode_mulaw_to_pcm16k(
                    packet(value)["media"]["payload"]
                )
            )
            if result is not None:
                completed = result

        self.assertIsNotNone(completed)
        self.assertGreater(len(completed), 6400)

    @patch(
        "leadpilot_ai.twilio_duplex_local.process_turn",
        new_callable=AsyncMock
    )
    def test_bidirectional_websocket(self, process):
        process.return_value = b"\xff" * 320

        with TestClient(app) as client:
            with client.websocket_connect(
                "/twilio/local-duplex-test"
            ) as ws:
                ws.send_json(start_packet())

                for _ in range(15):
                    ws.send_json(packet(0))

                for _ in range(35):
                    ws.send_json(packet(255))

                events = []

                while True:
                    response = ws.receive()
                    self.assertEqual(
                        response["type"],
                        "websocket.send"
                    )

                    data = json.loads(response["text"])
                    events.append(data["event"])

                    if data["event"] == "mark":
                        break

                self.assertEqual(
                    events, ["media", "media", "mark"]
                )

                ws.send_json({
                    "event": "stop",
                    "streamSid": "MZDuplexTest"
                })

                closed = ws.receive()

                self.assertEqual(
                    closed["type"], "websocket.close"
                )
                self.assertEqual(closed["code"], 1000)

        process.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
