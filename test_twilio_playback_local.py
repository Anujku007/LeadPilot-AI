import base64
import json
from pathlib import Path

from fastapi.testclient import TestClient

from leadpilot_api import app
from leadpilot_ai.twilio_playback_local import AUDIO_FILE


def main():
    if not AUDIO_FILE.is_file():
        raise SystemExit(
            "Missing NVIDIA voice file: "
            + str(AUDIO_FILE)
            + "\nRun test_llm_to_voice.py first."
        )

    print("LEADPILOT AI - LOCAL TWILIO PLAYBACK TEST")
    print("Source WAV:", AUDIO_FILE)

    frame_count = 0
    total_audio = 0
    found_mark = False

    with TestClient(app) as client:
        with client.websocket_connect(
            "/twilio/local-playback-test"
        ) as ws:

            ws.send_json({
                "event": "connected",
                "protocol": "Call",
                "version": "1.0.0"
            })

            ws.send_json({
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
            })

            while True:
                message = ws.receive()

                if message["type"] == "websocket.close":
                    if message["code"] != 1000:
                        raise RuntimeError(
                            "Playback WebSocket closed with error"
                        )
                    break

                packet = json.loads(message["text"])

                if packet["event"] == "media":
                    if found_mark:
                        raise RuntimeError(
                            "Media arrived after mark"
                        )

                    decoded = base64.b64decode(
                        packet["media"]["payload"],
                        validate=True
                    )

                    if not 1 <= len(decoded) <= 160:
                        raise RuntimeError(
                            "Invalid media frame length"
                        )

                    frame_count += 1
                    total_audio += len(decoded)

                elif packet["event"] == "mark":
                    found_mark = True

                else:
                    raise RuntimeError(
                        "Unexpected outbound message"
                    )

    if not frame_count or not found_mark:
        raise RuntimeError(
            "Missing outbound audio or playback mark"
        )

    print("SUCCESS: Playback WebSocket established")
    print("SUCCESS: Outbound media frames:", frame_count)
    print("SUCCESS: Raw mu-law bytes:", total_audio)
    print("SUCCESS: Playback mark sent")
    print("SUCCESS: Stream closed cleanly")
    print("Duration:", round(total_audio / 8000, 2), "seconds")
    print("No phone calls or appointments created")


if __name__ == "__main__":
    main()
