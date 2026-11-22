import base64
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from leadpilot_api import app


CID = "26802eda-2815-48e0-ab48-0363d3f43078"
SID = "MZLiveLocal"


def start_packet():
    return {
        "event": "start",
        "streamSid": SID,
        "start": {
            "streamSid": SID,
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


def media_packet(value):
    return {
        "event": "media",
        "streamSid": SID,
        "media": {
            "track": "inbound",
            "payload": base64.b64encode(
                bytes([value] * 160)
            ).decode("ascii")
        }
    }


def send_utterance(ws):
    for _ in range(15):
        ws.send_json(media_packet(0))

    for _ in range(35):
        ws.send_json(media_packet(255))


def stop(ws):
    ws.send_json({
        "event": "stop",
        "streamSid": SID
    })


class LiveCallTests(unittest.TestCase):

    @patch(
        "leadpilot_ai.twilio_live_local.process_turn",
        new_callable=AsyncMock
    )
    def test_realistic_audio_playback(self, process):
        process.return_value = b"\xff" * (160 * 8)

        with TestClient(app) as client:
            with client.websocket_connect(
                "/twilio/local-live-test"
            ) as ws:
                ws.send_json(start_packet())
                send_utterance(ws)

                events = []

                while True:
                    message = ws.receive()

                    self.assertEqual(
                        message["type"],
                        "websocket.send"
                    )

                    packet = json.loads(message["text"])
                    events.append(packet["event"])

                    if packet["event"] == "mark":
                        break

                self.assertEqual(
                    events,
                    ["media"] * 8 + ["mark"]
                )

                ws.send_json({
                    "event": "mark",
                    "streamSid": SID,
                    "mark": {
                        "name": "leadpilot-local-playback"
                    }
                })

                stop(ws)

                closed = ws.receive()

                self.assertEqual(
                    closed["type"], "websocket.close"
                )
                self.assertEqual(closed["code"], 1000)

        process.assert_awaited_once()

    @patch(
        "leadpilot_ai.twilio_live_local.process_turn",
        new_callable=AsyncMock
    )
    def test_interruption_during_ai_reply(self, process):
        process.return_value = b"\xff" * (160 * 80)

        with TestClient(app) as client:
            with client.websocket_connect(
                "/twilio/local-live-test"
            ) as ws:
                ws.send_json(start_packet())
                send_utterance(ws)

                first = ws.receive()

                self.assertEqual(
                    json.loads(first["text"])["event"],
                    "media"
                )

                # Caller starts speaking during AI playback.
                for _ in range(3):
                    ws.send_json(media_packet(0))

                clear_seen = False

                for _ in range(40):
                    message = ws.receive()

                    self.assertEqual(
                        message["type"],
                        "websocket.send"
                    )

                    packet = json.loads(message["text"])

                    if packet["event"] == "clear":
                        clear_seen = True
                        break

                self.assertTrue(clear_seen)

                stop(ws)

                while True:
                    message = ws.receive()

                    if message["type"] == "websocket.close":
                        self.assertEqual(
                            message["code"], 1000
                        )
                        break

                    packet = json.loads(message["text"])

                    self.assertNotEqual(
                        packet["event"], "media"
                    )

    @patch(
        "leadpilot_ai.twilio_live_local.process_turn",
        new_callable=AsyncMock
    )
    def test_silence_does_not_call_ai(self, process):
        with TestClient(app) as client:
            with client.websocket_connect(
                "/twilio/local-live-test"
            ) as ws:
                ws.send_json(start_packet())

                for _ in range(40):
                    ws.send_json(media_packet(255))

                stop(ws)

                closed = ws.receive()

                self.assertEqual(
                    closed["type"], "websocket.close"
                )
                self.assertEqual(closed["code"], 1000)

        process.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
