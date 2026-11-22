import base64
import unittest

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from twilio.request_validator import RequestValidator

from leadpilot_twilio_gateway import create_gateway

TOKEN = "local-test-secret"
ACCOUNT = "AC" + "1" * 32
CALL = "CA" + "2" * 32
ORIGIN = "https://leadpilot.example"

APP = create_gateway(
    auth_token=TOKEN,
    account_sid=ACCOUNT,
    public_base_url=ORIGIN
)

VALIDATOR = RequestValidator(TOKEN)


def signed_form():
    params = {
        "AccountSid": ACCOUNT,
        "CallSid": CALL
    }
    signature = VALIDATOR.compute_signature(
        ORIGIN + "/twilio/voice",
        params
    )
    return params, signature


def stream_start(account=ACCOUNT):
    return {
        "event": "start",
        "streamSid": "MZLocalSecure",
        "start": {
            "streamSid": "MZLocalSecure",
            "accountSid": account,
            "mediaFormat": {
                "encoding": "audio/x-mulaw",
                "sampleRate": 8000,
                "channels": 1
            }
        }
    }


class TwilioGatewayTests(unittest.TestCase):

    def test_missing_voice_signature_rejected(self):
        params, _ = signed_form()

        with TestClient(APP) as client:
            result = client.post(
                "/twilio/voice",
                data=params
            )

        self.assertEqual(result.status_code, 403)

    def test_signed_webhook_returns_safe_twiml(self):
        params, signature = signed_form()

        with TestClient(APP) as client:
            result = client.post(
                "/twilio/voice",
                data=params,
                headers={
                    "X-Twilio-Signature": signature
                }
            )

        self.assertEqual(result.status_code, 200)
        self.assertIn("<Hangup/>", result.text)
        self.assertNotIn("<Stream", result.text)

    def test_unsigned_websocket_rejected(self):
        with TestClient(APP) as client:
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/twilio/stream"
                ):
                    pass

    def test_signed_websocket_lifecycle(self):
        signature = VALIDATOR.compute_signature(
            "wss://leadpilot.example/twilio/stream",
            {}
        )

        with TestClient(APP) as client:
            with client.websocket_connect(
                "/twilio/stream",
                headers={
                    "X-Twilio-Signature": signature
                }
            ) as ws:
                ws.send_json(stream_start())

                ws.send_json({
                    "event": "media",
                    "streamSid": "MZLocalSecure",
                    "media": {
                        "track": "inbound",
                        "payload": base64.b64encode(
                            bytes([255] * 160)
                        ).decode("ascii")
                    }
                })

                ws.send_json({
                    "event": "stop",
                    "streamSid": "MZLocalSecure"
                })

                closed = ws.receive()
                self.assertEqual(
                    closed["type"], "websocket.close"
                )
                self.assertEqual(closed["code"], 1000)

    def test_wrong_account_rejected(self):
        signature = VALIDATOR.compute_signature(
            "wss://leadpilot.example/twilio/stream",
            {}
        )

        with TestClient(APP) as client:
            with client.websocket_connect(
                "/twilio/stream",
                headers={
                    "X-Twilio-Signature": signature
                }
            ) as ws:
                ws.send_json(
                    stream_start("AC" + "9" * 32)
                )

                closed = ws.receive()

                self.assertEqual(
                    closed["type"], "websocket.close"
                )
                self.assertEqual(closed["code"], 1008)


if __name__ == "__main__":
    unittest.main()
