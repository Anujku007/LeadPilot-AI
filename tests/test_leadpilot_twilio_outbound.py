import base64
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from leadpilot_api import app
from leadpilot_ai.twilio_audio_out import (
    wav_to_mulaw8k, outbound_packets,
    mark_packet, clear_packet
)


def create_wav(path, rate=44100, silence=False):
    t = np.arange(rate) / rate
    data = (
        np.zeros(rate)
        if silence
        else np.sin(2 * np.pi * 440 * t) * 12000
    ).astype("<i2")

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(data.tobytes())


def start_packet():
    return {
        "event": "start",
        "streamSid": "MZLocalPlayback",
        "start": {
            "streamSid": "MZLocalPlayback",
            "mediaFormat": {
                "encoding": "audio/x-mulaw",
                "sampleRate": 8000,
                "channels": 1
            }
        }
    }


class TwilioOutboundTests(unittest.TestCase):

    def test_wav_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voice.wav"
            create_wav(path)

            result = wav_to_mulaw8k(path)

            self.assertEqual(len(result), 8000)
            self.assertNotEqual(result[:4], b"RIFF")

    def test_silence_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "silence.wav"
            create_wav(path, rate=8000, silence=True)

            result = wav_to_mulaw8k(path)

            self.assertEqual(result, b"\xff" * 8000)

    def test_media_frames(self):
        packets = list(outbound_packets(
            b"\xff" * 400, "MZTest"
        ))

        self.assertEqual(len(packets), 3)
        self.assertEqual(packets[0]["event"], "media")
        self.assertEqual(
            len(base64.b64decode(
                packets[0]["media"]["payload"]
            )),
            160
        )

    def test_mark_and_clear(self):
        self.assertEqual(
            mark_packet("MZTest")["event"], "mark"
        )
        self.assertEqual(
            clear_packet("MZTest")["event"], "clear"
        )

    def test_empty_audio_rejected(self):
        with self.assertRaises(ValueError):
            list(outbound_packets(b"", "MZTest"))

    @patch(
        "leadpilot_ai.twilio_playback_local.wav_to_mulaw8k",
        return_value=b"\xff" * 320
    )
    def test_local_websocket_playback(self, mocked_audio):
        with TestClient(app) as client:
            with client.websocket_connect(
                "/twilio/local-playback-test"
            ) as ws:
                ws.send_json(start_packet())

                received = []

                while True:
                    message = ws.receive()

                    if message["type"] == "websocket.close":
                        self.assertEqual(
                            message["code"], 1000
                        )
                        break

                    received.append(
                        json.loads(message["text"])
                    )

                self.assertEqual(
                    [item["event"] for item in received],
                    ["media", "media", "mark"]
                )

        mocked_audio.assert_called_once()


if __name__ == "__main__":
    unittest.main()
