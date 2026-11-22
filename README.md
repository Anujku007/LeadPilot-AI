# LeadPilot AI

**NVIDIA-powered AI voice sales assistant for lead qualification, CRM tracking, and appointment scheduling.**

LeadPilot AI is a Python/FastAPI portfolio project that uses NVIDIA AI services to engage prospective customers, qualify leads using the BANT framework, maintain conversation records, and support Google Calendar appointment scheduling.

## Features

- NVIDIA Nemotron for conversational AI
- NVIDIA Parakeet for speech recognition
- NVIDIA Magpie for speech synthesis
- BANT qualification: Budget, Authority, Need, Timeline
- SQLite CRM with conversation history and lead scoring
- Google Calendar availability, appointment proposals, and confirmation workflows
- Local microphone-to-AI-to-speaker voice demonstration
- Twilio-compatible audio and WebSocket simulation
- Secure Twilio webhook signature validation
- Turn-by-turn Twilio Gather fallback with SQLite session persistence and replay protection

## Architecture

```text
Customer speech
     |
     v
Speech recognition
     |
     v
NVIDIA Nemotron conversational AI
     |
     +----> BANT qualification and SQLite CRM
     |
     +----> Appointment workflows / Google Calendar
     |
     v
Spoken AI response
```

The project supports a local NVIDIA voice demonstration and separately tested Twilio-compatible call workflows.

**Deployment status:** Real Twilio outbound calling has been verified, and the NVIDIA Gather fallback has passed local signed-webhook simulations. A real public telephone call connected to NVIDIA AI has not yet been validated.

## Technology

Python, FastAPI, NVIDIA AI APIs, SQLite, SQLAlchemy, Twilio, Google Calendar API, and WebSockets.

## Local setup

Tested using Python 3.11.

1. Create a Python virtual environment.
2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and enter your own credentials.
4. Configure Google Calendar OAuth locally if appointment booking is required.
5. Run the main application:

   ```powershell
   python -m uvicorn leadpilot_api:app --host 127.0.0.1 --port 8001
   ```

6. For the isolated Twilio gateway, use another terminal:

   ```powershell
   python -m uvicorn leadpilot_twilio_gateway:app --host 127.0.0.1 --port 8002
   ```

Never expose the private CRM API publicly without appropriate authentication.

## Testing

Run the LeadPilot test suite:

```powershell
python -m unittest discover -s tests -p "test_leadpilot_*.py" -q
```

At the final local verification, 89 tests passed after removing unrelated starter components.

Local voice demonstration:

```powershell
python test_two_way_voice.py
```

A working microphone, speakers, and configured NVIDIA credentials are required.

## Security

Real credentials, OAuth tokens, SQLite customer records, and local audio recordings are excluded from Git. Twilio webhook signatures are validated before processing callbacks.

The SQLite Gather adapter supports persistent completed-response replay, while interrupted in-flight operations fail closed and may require recovery. The system is a portfolio MVP, not a production-hardened telephone service.

## Original project attribution

This project was developed using initial starter scaffolding from:

[OpenAI Realtime + Twilio Voice Agent Starter](https://github.com/aymalkhalid/Starter-Agent-InBound-OutBound-Twilio-Speech-Assistant-OpenAi-Realtime-Api-Python)

The LeadPilot NVIDIA integrations, CRM, qualification workflows, and related tests extend that foundation. See the repository license for applicable terms.

## License

See [LICENSE](LICENSE).
