import base64
import json
import time
import wave
import winsound
from pathlib import Path

from fastapi.testclient import TestClient

from leadpilot_api import app
from leadpilot_ai.twilio_audio_out import wav_to_mulaw8k
from leadpilot_ai.twilio_stream import (
    decode_mulaw_to_pcm16k
)
from test_voice_vad_crm import record_until_silence


ROOT = Path(__file__).resolve().parent
OUTPUT = (
    ROOT / "leadpilot_audio" / "twilio_live_reply.wav"
)
SID = "MZLeadPilotLiveTest"


def media_packet(data):
    return {
        "event": "media",
        "streamSid": SID,
        "media": {
            "track": "inbound",
            "payload": base64.b64encode(
                data
            ).decode("ascii")
        }
    }


def main():
    print("=" * 52)
    print(" LEADPILOT - LOCAL LIVE TELEPHONE SIMULATION")
    print("=" * 52)
    print("No real Twilio call will be placed.")

    recording = record_until_silence()

    if recording is None:
        raise SystemExit("No speech detected.")

    input_audio = wav_to_mulaw8k(recording)

    # Telephone silence before and after speech.
    input_audio = (
        b"\xff" * 1600
        + input_audio
        + b"\xff" * 8000
    )

    frames = [
        input_audio[i:i + 160]
        for i in range(0, len(input_audio), 160)
    ]

    print("Incoming frames:", len(frames))

    with TestClient(app) as client:
        created = client.post(
            "/api/conversations/start"
        )
        created.raise_for_status()

        cid = created.json()["conversation_id"]

        print("CRM conversation:", cid)

        with client.websocket_connect(
            "/twilio/local-live-test"
        ) as ws:
            ws.send_json({
                "event": "connected",
                "protocol": "Call",
                "version": "1.0.0"
            })

            ws.send_json({
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
                        "conversation_id": cid
                    }
                }
            })

            print("Sending telephone audio at 20 ms/frame...")

            for frame in frames:
                ws.send_json(media_packet(frame))
                time.sleep(0.020)

            print("Waiting for NVIDIA response...")

            received_audio = bytearray()
            output_frames = 0
            started = time.perf_counter()

            while True:
                message = ws.receive()

                if message["type"] == "websocket.close":
                    raise RuntimeError(
                        "Call closed before AI playback"
                    )

                packet = json.loads(message["text"])

                if packet["event"] == "media":
                    output_frames += 1
                    received_audio.extend(
                        decode_mulaw_to_pcm16k(
                            packet["media"]["payload"]
                        )
                    )

                elif packet["event"] == "mark":
                    break

                elif packet["event"] == "clear":
                    raise RuntimeError(
                        "Unexpected playback interruption"
                    )

            elapsed = time.perf_counter() - started

            ws.send_json({
                "event": "mark",
                "streamSid": SID,
                "mark": {
                    "name": "leadpilot-local-playback"
                }
            })

            ws.send_json({
                "event": "stop",
                "streamSid": SID
            })

            closed = ws.receive()

            if (
                closed["type"] != "websocket.close"
                or closed["code"] != 1000
            ):
                raise RuntimeError(
                    "Call did not terminate cleanly"
                )

        saved = client.get(
            f"/api/conversations/{cid}"
        )
        saved.raise_for_status()
        crm = saved.json()

    if not received_audio:
        raise RuntimeError("No AI audio received")

    OUTPUT.parent.mkdir(
        parents=True, exist_ok=True
    )

    with wave.open(str(OUTPUT), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(bytes(received_audio))

    print("\nSUCCESS: Telephone audio received")
    print("SUCCESS: NVIDIA ASR + CRM + TTS processed")
    print("SUCCESS: Outbound audio paced")
    print("SUCCESS: Playback mark acknowledged")

    print("Outbound frames:", output_frames)
    print("Playback receive time:", round(elapsed, 2), "s")
    print("CRM messages saved:", len(crm.get("messages", [])))

    for message in crm.get("messages", [])[-2:]:
        if isinstance(message, dict):
            print(
                message.get("role", "").upper() + ":",
                message.get("content", "")
            )

    print("\nPlaying telephone-format AI response...")

    winsound.PlaySound(
        str(OUTPUT),
        winsound.SND_FILENAME
    )

    print("\nLocal live simulation completed.")
    print("No phone calls or appointments created.")


if __name__ == "__main__":
    main()
