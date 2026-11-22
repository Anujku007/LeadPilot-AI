import base64
import json
import time

from fastapi.testclient import TestClient

from leadpilot_api import app


SID = "MZLocalPacedSimulation"


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
            }
        }
    }


def caller_audio():
    return {
        "event": "media",
        "streamSid": SID,
        "media": {
            "track": "inbound",
            "payload": base64.b64encode(
                bytes([0] * 160)
            ).decode("ascii")
        }
    }


def normal_playback():
    print("\nTEST 1: PACED AI PLAYBACK")

    with TestClient(app) as client:
        with client.websocket_connect(
            "/twilio/local-paced-test"
        ) as ws:
            ws.send_json(start_packet())

            count = 0
            started = time.perf_counter()

            while True:
                message = ws.receive()

                if message["type"] != "websocket.send":
                    raise RuntimeError(
                        "Playback ended unexpectedly"
                    )

                packet = json.loads(message["text"])

                if packet["event"] == "media":
                    count += 1

                elif packet["event"] == "mark":
                    break

            duration = time.perf_counter() - started

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
                    "Playback did not close cleanly"
                )

    print("Audio frames:", count)
    print("Elapsed time:", round(duration, 2), "seconds")
    print("Playback acknowledgement: SENT")

    expected = max(0, (count - 1) * 0.020)

    if duration < expected - 0.10:
        raise RuntimeError(
            "Playback frames were sent too quickly"
        )

    print("SUCCESS: Audio playback was paced")


def interruption_test():
    print("\nTEST 2: CUSTOMER INTERRUPTION")

    with TestClient(app) as client:
        with client.websocket_connect(
            "/twilio/local-paced-test"
        ) as ws:
            ws.send_json(start_packet())

            first = ws.receive()

            if (
                first["type"] != "websocket.send"
                or json.loads(first["text"])["event"]
                != "media"
            ):
                raise RuntimeError(
                    "AI playback did not start"
                )

            # Simulated speech during AI playback.
            for _ in range(3):
                ws.send_json(caller_audio())

            clear_received = False

            while True:
                message = ws.receive()

                if message["type"] != "websocket.send":
                    raise RuntimeError(
                        "WebSocket closed before clear"
                    )

                packet = json.loads(message["text"])

                if packet["event"] == "clear":
                    clear_received = True
                    break

                if packet["event"] == "mark":
                    raise RuntimeError(
                        "Playback completed before interruption"
                    )

            ws.send_json({
                "event": "stop",
                "streamSid": SID
            })

            while True:
                message = ws.receive()

                if message["type"] == "websocket.close":
                    if message["code"] != 1000:
                        raise RuntimeError(
                            "Unexpected close code"
                        )
                    break

                packet = json.loads(message["text"])

                if packet["event"] == "media":
                    raise RuntimeError(
                        "Additional audio after clear"
                    )

    if not clear_received:
        raise RuntimeError("Interruption not detected")

    print("SUCCESS: Customer speech detected")
    print("SUCCESS: Twilio clear message sent")
    print("SUCCESS: Further AI frames stopped")


if __name__ == "__main__":
    print("=" * 48)
    print("LEADPILOT - TWILIO TIMING AND INTERRUPTION")
    print("=" * 48)
    print("Local simulation only. No real phone call.")

    normal_playback()
    interruption_test()

    print("\nALL LOCAL TESTS COMPLETED")
    print("No calls or appointments created.")
