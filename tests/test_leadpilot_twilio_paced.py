import base64
import json
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from leadpilot_api import app
from leadpilot_ai.twilio_stream import (
    decode_mulaw_to_pcm16k
)
from leadpilot_ai.twilio_paced_local import (
    speech_detected
)


def start_packet():
    return {
        "event": "start",
        "streamSid": "MZPacedTest",
        "start": {
            "streamSid": "MZPacedTest",
            "mediaFormat": {
                "encoding": "audio/x-mulaw",
                "sampleRate": 8000,
                "channels": 1
            }
        }
    }


def inbound(value):
    return {
        "event": "media",
        "streamSid": "MZPacedTest",
        "media": {
            "track": "inbound",
            "payload": base64.b64encode(
                bytes([value] * 160)
            ).decode("ascii")
        }
    }


class PacedTwilioTests(unittest.TestCase):

    def test_silence_is_not_speech(self):
        pcm = decode_mulaw_to_pcm16k(
            inbound(255)["media"]["payload"]
        )
        self.assertFalse(speech_detected(pcm))

    def test_loud_frame_is_speech(self):
        pcm = decode_mulaw_to_pcm16k(
            inbound(0)["media"]["payload"]
        )
        self.assertTrue(speech_detected(pcm))

    @patch(
        "leadpilot_ai.twilio_paced_local.wav_to_mulaw8k",
        return_value=b"\xff" * (160 * 5)
    )
    def test_paced_playback_and_mark(self, mocked_audio):
        with TestClient(app) as client:
            with client.websocket_connect(
                "/twilio/local-paced-test"
            ) as ws:
                ws.send_json(start_packet())

                events = []
                timestamps = []

                while True:
                    message = ws.receive()
                    self.assertEqual(
                        message["type"], "websocket.send"
                    )

                    packet = json.loads(message["text"])
                    events.append(packet["event"])
                    timestamps.append(time.monotonic())

                    if packet["event"] == "mark":
                        break

                self.assertEqual(
                    events,
                    ["media"] * 5 + ["mark"]
                )

                self.assertGreaterEqual(
                    timestamps[4] - timestamps[0],
                    0.045
                )

                ws.send_json({
                    "event": "mark",
                    "streamSid": "MZPacedTest",
                    "mark": {
                        "name": "leadpilot-local-playback"
                    }
                })

                ws.send_json({
                    "event": "stop",
                    "streamSid": "MZPacedTest"
                })

                closed = ws.receive()
                self.assertEqual(
                    closed["type"], "websocket.close"
                )
                self.assertEqual(closed["code"], 1000)

        mocked_audio.assert_called_once()

    @patch(
        "leadpilot_ai.twilio_paced_local.wav_to_mulaw8k",
        return_value=b"\xff" * (160 * 50)
    )
    def test_speech_interrupts_playback(self, mocked_audio):
        with TestClient(app) as client:
            with client.websocket_connect(
                "/twilio/local-paced-test"
            ) as ws:
                ws.send_json(start_packet())

                first = json.loads(ws.receive()["text"])
                self.assertEqual(first["event"], "media")

                # Simulate caller speech while AI audio plays.
                for _ in range(3):
                    ws.send_json(inbound(0))

                saw_clear = False

                for _ in range(30):
                    message = ws.receive()
                    self.assertEqual(
                        message["type"], "websocket.send"
                    )

                    packet = json.loads(message["text"])

                    if packet["event"] == "clear":
                        saw_clear = True
                        break

                self.assertTrue(saw_clear)

                ws.send_json({
                    "event": "stop",
                    "streamSid": "MZPacedTest"
                })

                while True:
                    message = ws.receive()

                    if message["type"] == "websocket.close":
                        self.assertEqual(
                            message["code"], 1000
                        )
                        break

                    packet = json.loads(message["text"])

                    self.assertNotEqual(
                        packet["event"], "media",
                        "Audio was sent after clear"
                    )


if __name__ == "__main__":
    unittest.main()
