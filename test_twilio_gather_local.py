from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from leadpilot_twilio_gateway import create_gateway

TOKEN = "local-simulator-token"
ACCOUNT = "AC" + "1" * 32
CALL = "CA" + "2" * 32
ORIGIN = "https://leadpilot.example"


class DemoCRM:
    def __init__(self):
        self.messages = []

    async def start(self):
        print("CRM conversation created (simulated)")
        return "local-demo-conversation"

    async def chat(self, cid, speech):
        print("CUSTOMER:", speech)
        self.messages.append(speech)

        if len(self.messages) == 1:
            return "Do you have an allocated budget?"

        if len(self.messages) == 2:
            return "Who makes the purchasing decision?"

        return "When do you want to implement the CRM?"


def main():
    demo = DemoCRM()

    app = create_gateway(
        auth_token=TOKEN,
        account_sid=ACCOUNT,
        public_base_url=ORIGIN,
        gather_backend=demo
    )

    validator = RequestValidator(TOKEN)

    def signed_post(client, route, extra=None):
        params = {
            "AccountSid": ACCOUNT,
            "CallSid": CALL
        }

        if extra:
            params.update(extra)

        if route == "/twilio/gather-turn":
            route += f"?step={len(demo.messages)}"

        signature = validator.compute_signature(
            ORIGIN + route, params
        )

        response = client.post(
            route,
            data=params,
            headers={
                "X-Twilio-Signature": signature
            }
        )
        response.raise_for_status()
        return response

    print("=" * 48)
    print("LEADPILOT - TWILIO GATHER FALLBACK TEST")
    print("=" * 48)
    print("No real phone call or NVIDIA request.")

    with TestClient(app) as client:
        start = signed_post(
            client, "/twilio/gather-start"
        )

        root = ET.fromstring(start.text)
        self_gather = root.find("Gather")

        if self_gather is None:
            raise RuntimeError("Gather missing")

        print("SUCCESS: Signed call started")
        print("SUCCESS: Speech Gather instructions returned")

        for spoken in (
            "I need a CRM for my business.",
            "My budget is fifty thousand rupees.",
            "I make the purchasing decision."
        ):
            reply = signed_post(
                client,
                "/twilio/gather-turn",
                {"SpeechResult": spoken}
            )

            document = ET.fromstring(reply.text)
            spoken_reply = (
                document.findtext("Gather/Say")
                or document.findtext("Say")
            )

            print("LEADPILOT:", spoken_reply)

    print()
    print("SUCCESS: Three signed speech turns accepted")
    print("SUCCESS: CRM interaction simulated")
    print("SUCCESS: Twilio speech replies generated")
    print("No calls or appointments created")


if __name__ == "__main__":
    main()

# LeadPilot numbered callback replay protection v1
