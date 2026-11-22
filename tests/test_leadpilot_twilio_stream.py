import base64
import unittest

from fastapi.testclient import TestClient

from leadpilot_ai.twilio_stream import (
    StreamState, decode_mulaw_to_pcm16k
)
from leadpilot_api import app


def start_packet():
    return {
        "event": "start",
        "streamSid": "MZLocalTest",
        "start": {
            "streamSid": "MZLocalTest",
            "mediaFormat": {
                "encoding": "audio/x-mulaw",
                "sampleRate": 8000,
                "channels": 1
            }
        }
    }


def media_packet():
    return {
        "event": "media",
        "streamSid": "MZLocalTest",
        "media": {
            "track": "inbound",
            "payload": base64.b64encode(
                bytes([255] * 160)
            ).decode("ascii")
        }
    }


class TwilioMediaTests(unittest.TestCase):

    def test_silence_decodes(self):
        payload = media_packet()["media"]["payload"]
        pcm = decode_mulaw_to_pcm16k(payload)

        # 20 ms at 16 kHz, signed 16-bit mono
        self.assertEqual(len(pcm), 640)
        self.assertEqual(pcm, bytes(640))

    def test_invalid_base64_rejected(self):
        with self.assertRaises(ValueError):
            decode_mulaw_to_pcm16k("not-base64!")

    def test_start_validates_format(self):
        state = StreamState()
        packet = start_packet()
        packet["start"]["mediaFormat"]["sampleRate"] = 44100

        with self.assertRaises(ValueError):
            state.start(packet)

    def test_media_accounting(self):
        state = StreamState()
        state.start(start_packet())
        pcm = state.feed(media_packet())

        self.assertEqual(len(pcm), 640)
        self.assertEqual(state.media_count, 1)
        self.assertEqual(state.input_bytes, 160)

    def test_media_requires_start(self):
        state = StreamState()

        with self.assertRaises(ValueError):
            state.feed(media_packet())

    def test_websocket_lifecycle(self):
        with TestClient(app) as client:
            with client.websocket_connect(
                "/twilio/media-stream"
            ) as ws:
                ws.send_json({
                    "event": "connected",
                    "protocol": "Call",
                    "version": "1.0.0"
                })
                ws.send_json(start_packet())
                ws.send_json(media_packet())
                ws.send_json({
                    "event": "stop",
                    "streamSid": "MZLocalTest"
                })

                message = ws.receive()
                self.assertEqual(
                    message["type"], "websocket.close"
                )
                self.assertEqual(
                    message["code"], 1000
                )


if __name__ == "__main__":
    unittest.main()
