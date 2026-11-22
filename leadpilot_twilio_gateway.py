import os
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, Response
from twilio.request_validator import RequestValidator

from leadpilot_ai.twilio_stream import StreamState

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

SAFE_TWIML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Response>'
    '<Say>LeadPilot AI secure gateway is ready. '
    'Live telephone conversations are not enabled yet.'
    '</Say>'
    '<Hangup/>'
    '</Response>'
)


def create_gateway(
    auth_token=None,
    account_sid=None,
    public_base_url=None,
    gather_backend=None,
    gather_store=None
):
    token = (
        auth_token if auth_token is not None
        else os.getenv("TWILIO_AUTH_TOKEN", "")
    )
    account = (
        account_sid if account_sid is not None
        else os.getenv("TWILIO_ACCOUNT_SID", "")
    )
    origin = (
        public_base_url if public_base_url is not None
        else os.getenv("TWILIO_PUBLIC_BASE_URL", "")
    )

    origin = origin.rstrip("/")

    if origin:
        parsed = urlparse(origin)

        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError(
                "TWILIO_PUBLIC_BASE_URL must be "
                "an HTTPS origin without a path or query"
            )

    configured = bool(token and account and origin)

    validator = (
        RequestValidator(token) if configured else None
    )

    voice_url = origin + "/twilio/voice"
    stream_url = (
        "wss://" + urlparse(origin).netloc
        + "/twilio/stream"
        if origin else ""
    )

    app = FastAPI(
        title="LeadPilot Secure Twilio Gateway",
        docs_url=None,
        redoc_url=None,
        openapi_url=None
    )

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "service": "LeadPilot Twilio Gateway",
            "configured": configured,
            "live_calls_enabled": False
        }

    @app.post("/twilio/voice")
    async def voice_webhook(request: Request):
        if not configured:
            return PlainTextResponse(
                "Twilio gateway is not configured",
                status_code=503
            )

        if not request.headers.get(
            "content-type", ""
        ).lower().startswith(
            "application/x-www-form-urlencoded"
        ):
            return PlainTextResponse(
                "Unsupported content type",
                status_code=415
            )

        raw = await request.body()

        if len(raw) > 8192:
            return PlainTextResponse(
                "Request too large",
                status_code=413
            )

        try:
            pairs = parse_qsl(
                raw.decode("utf-8"),
                keep_blank_values=True
            )
            params = dict(pairs)
        except (UnicodeDecodeError, ValueError):
            return PlainTextResponse(
                "Invalid form data",
                status_code=400
            )

        if len(params) != len(pairs):
            return PlainTextResponse(
                "Duplicate parameters",
                status_code=400
            )

        signature = request.headers.get(
            "x-twilio-signature", ""
        )

        if not signature or not validator.validate(
            voice_url, params, signature
        ):
            return PlainTextResponse(
                "Invalid Twilio signature",
                status_code=403
            )

        if (
            params.get("AccountSid") != account
            or not re.fullmatch(
                r"CA[a-fA-F0-9]{32}",
                params.get("CallSid", "")
            )
        ):
            return PlainTextResponse(
                "Invalid call identity",
                status_code=403
            )

        return Response(
            SAFE_TWIML,
            media_type="application/xml"
        )

    @app.websocket("/twilio/stream")
    async def authenticated_stream(websocket: WebSocket):
        signature = websocket.headers.get(
            "x-twilio-signature", ""
        )

        # Twilio documents a trailing-slash variation
        # for some WSS handshake signatures.
        valid = bool(
            configured
            and signature
            and (
                validator.validate(
                    stream_url, {}, signature
                )
                or validator.validate(
                    stream_url + "/", {}, signature
                )
            )
        )

        if not valid:
            await websocket.close(code=1008)
            return

        await websocket.accept()

        state = StreamState()

        try:
            while True:
                packet = await websocket.receive_json()

                if not isinstance(packet, dict):
                    raise ValueError("Invalid message")

                event = packet.get("event")

                if event == "connected":
                    continue

                if event == "start":
                    if state.stream_sid is not None:
                        raise ValueError(
                            "Duplicate stream start"
                        )

                    details = packet.get("start") or {}

                    if details.get("accountSid") != account:
                        raise ValueError(
                            "Account does not match"
                        )

                    state.start(packet)

                elif event == "media":
                    if (
                        packet.get("streamSid")
                        != state.stream_sid
                    ):
                        raise ValueError(
                            "Stream SID mismatch"
                        )

                    state.feed(packet)

                    if state.media_count > 2500:
                        raise ValueError(
                            "Test stream limit exceeded"
                        )

                elif event == "stop":
                    break

                elif event in ("mark", "dtmf"):
                    continue

                else:
                    raise ValueError(
                        "Unsupported stream event"
                    )

        except WebSocketDisconnect:
            return

        except (ValueError, TypeError, KeyError):
            await websocket.close(code=1008)
            return

        await websocket.close(code=1000)


    from leadpilot_ai.twilio_gather_fallback import (
        attach_gather_routes
    )

    # Optional SQLite-backed Gather call sessions.
    # Without the environment variable, the existing
    # in-memory implementation remains unchanged.
    if gather_store is None and gather_backend is None:

        database_path = os.environ.get(
            "LEADPILOT_GATHER_DB", ""
        ).strip()

        if database_path:
            from pathlib import Path
            from leadpilot_ai.twilio_gather_store import (
                GatherSessionStore
            )

            if not Path(database_path).is_absolute():
                raise RuntimeError(
                    "LEADPILOT_GATHER_DB must be absolute"
                )

            gather_store = GatherSessionStore(database_path)

    attach_gather_routes(
        app=app,
        validator=validator,
        account=account,
        origin=origin,
        configured=configured,
        backend=gather_backend,
        store=gather_store
    )

    return app


app = create_gateway()

# LeadPilot persistent Gather integration v1
