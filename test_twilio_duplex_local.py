import base64
import json
import wave
import winsound
from pathlib import Path

from fastapi.testclient import TestClient

from leadpilot_api import app
from leadpilot_ai.twilio_audio_out import wav_to_mulaw8k
from leadpilot_ai.twilio_stream import (
    decode_mulaw_to_pcm16k
)
from leadpilot_ai.twilio_duplex_local import SpeechSegmenter
from test_voice_vad_crm import record_until_silence


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "leadpilot_audio" / "twilio_duplex_reply.wav"

SID = "MZLeadPilotLocalDuplex"


def media_packet(chunk):
    return {
        "event": "media",
        "streamSid": SID,
        "media": {
            "track": "inbound",
            "payload": base64.b64encode(
                chunk
            ).decode("ascii")
        }
    }


def main():
    print("=" * 50)
    print("LEADPILOT - SIMULATED BIDIRECTIONAL CALL")
    print("=" * 50)
    print("No real Twilio phone call will be made.")

    recording = record_until_silence()

    if recording is None:
        raise SystemExit(
            "No speech detected. Run the test again."
        )

    # Encode laptop speech into telephone format.
    incoming = wav_to_mulaw8k(recording)

    incoming = (
        b"\xff" * 1600
        + incoming
        + b"\xff" * 8000
    )

    frames = [
        incoming[i:i + 160]
        for i in range(0, len(incoming), 160)
    ]

    # Ensure the simulated speech can be detected
    # before opening the WebSocket.
    vad = SpeechSegmenter()
    detected = False

    for frame in frames:
        result = vad.feed(
            decode_mulaw_to_pcm16k(
                base64.b64encode(frame).decode("ascii")
            )
        )
        if result is not None:
            detected = True
            break

    if not detected:
        raise RuntimeError(
            "Speech energy too low for telephone VAD. "
            "Try speaking louder or closer to the microphone."
        )

    print("Input telephone audio frames:", len(frames))

    with TestClient(app) as client:
        started = client.post(
            "/api/conversations/start"
        )
        started.raise_for_status()

        cid = started.json()["conversation_id"]

        print("New CRM conversation:", cid)

        with client.websocket_connect(
            "/twilio/local-duplex-test"
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

            for frame in frames:
                ws.send_json(media_packet(frame))

            print("Waiting for NVIDIA ASR, CRM, and TTS...")

            output_audio = bytearray()
            mark_seen = False

            while not mark_seen:
                message = ws.receive()

                if message["type"] == "websocket.close":
                    raise RuntimeError(
                        "Duplex server closed before playback. "
                        "Check the server traceback."
                    )

                packet = json.loads(message["text"])

                if packet["event"] == "media":
                    output_audio.extend(
                        decode_mulaw_to_pcm16k(
                            packet["media"]["payload"]
                        )
                    )

                elif packet["event"] == "mark":
                    mark_seen = True

            # Simulate Twilio playback acknowledgement.
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
                    "Duplex stream did not stop cleanly"
                )

        saved = client.get(
            f"/api/conversations/{cid}"
        )
        saved.raise_for_status()
        crm = saved.json()

    if not output_audio:
        raise RuntimeError("No AI voice was returned")

    OUTPUT.parent.mkdir(
        parents=True, exist_ok=True
    )

    with wave.open(str(OUTPUT), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(bytes(output_audio))

    print("\nSUCCESS: Telephone audio received")
    print("SUCCESS: NVIDIA processed the voice turn")
    print("SUCCESS: Outbound telephone audio received")
    print("SUCCESS: Twilio playback mark acknowledged")
    print("CRM messages saved:", len(crm.get("messages", [])))

    for message in crm.get("messages", [])[-2:]:
        if isinstance(message, dict):
            print(
                message.get("role", "unknown").upper() + ":",
                message.get("content", "")
            )

    print("Voice response:", OUTPUT)
    print("\nPlaying simulated telephone audio...")

    winsound.PlaySound(
        str(OUTPUT), winsound.SND_FILENAME
    )

    print("\nLocal simulated call completed.")
    print("No real phone call or appointment created.")


if __name__ == "__main__":
    main()
