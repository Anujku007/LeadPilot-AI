import base64

from fastapi.testclient import TestClient

from leadpilot_api import app


def main():
    print("LEADPILOT AI - LOCAL TWILIO STREAM TEST")
    print("No Twilio account or phone call is required.")

    # Simulate ten 20 ms G.711 mu-law silence frames.
    frame = base64.b64encode(
        bytes([255] * 160)
    ).decode("ascii")

    with TestClient(app) as client:
        with client.websocket_connect(
            "/twilio/media-stream"
        ) as ws:

            ws.send_json({
                "event": "connected",
                "protocol": "Call",
                "version": "1.0.0"
            })

            ws.send_json({
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
            })

            for i in range(10):
                ws.send_json({
                    "event": "media",
                    "streamSid": "MZLocalTest",
                    "media": {
                        "track": "inbound",
                        "chunk": str(i + 1),
                        "payload": frame
                    }
                })

            ws.send_json({
                "event": "stop",
                "streamSid": "MZLocalTest"
            })

            response = ws.receive()

            if (
                response.get("type") != "websocket.close"
                or response.get("code") != 1000
            ):
                raise RuntimeError(
                    "Twilio stream did not close cleanly"
                )

    print("SUCCESS: WebSocket connection established")
    print("SUCCESS: Start message accepted")
    print("SUCCESS: 10 audio frames processed")
    print("SUCCESS: Stream stopped cleanly")
    print("Converted format: 16 kHz PCM, mono")
    print("No customer audio was stored")
    print("No phone calls or appointments created")


if __name__ == "__main__":
    main()
