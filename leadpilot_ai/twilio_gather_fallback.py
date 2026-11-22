import asyncio
import re
import time
from urllib.parse import parse_qsl

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse

MAX_TURNS = 6
SESSION_SECONDS = 900
MAX_SESSIONS = 100

UNAVAILABLE = (
    "The AI service is temporarily unavailable. "
    "Please try again later."
)


class LocalCRMBackend:
    """Calls only the private LeadPilot API on localhost."""

    def __init__(self):
        self.base_url = "http://127.0.0.1:8001"

    async def start(self):
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=3.8
        ) as client:
            result = await client.post(
                "/api/conversations/start"
            )
            result.raise_for_status()
            data = result.json()

        cid = data.get("conversation_id")

        if not isinstance(cid, str) or not cid:
            raise RuntimeError("CRM conversation ID missing")

        return cid

    async def chat(self, conversation_id, message):
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=3.8
        ) as client:
            result = await client.post(
                f"/api/conversations/{conversation_id}/chat",
                json={"message": message}
            )
            result.raise_for_status()
            data = result.json()

        for key in (
            "assistant_response",
            "ai_response",
            "assistant_reply",
            "reply",
            "response",
            "answer"
        ):
            value = data.get(key)

            if isinstance(value, str) and value.strip():
                return value.strip()

            if isinstance(value, dict):
                content = value.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()

        raise RuntimeError("No assistant reply in CRM response")


def safe_spoken_reply(text, max_chars=300):
    if not isinstance(text, str) or not text.strip():
        return "Could you please repeat that?"

    # Preserve the existing no-false-actions rule.
    unsupported = re.search(
        r"(?:i(?:'ve| have)? (?:sent|emailed|booked|"
        r"scheduled)|i(?:'ll| will) send|"
        r"calendar link|calendar invite|"
        r"check your inbox|"
        r"share your email|provide your email|"
        r"appointment (?:is|has been) confirmed)",
        text,
        re.IGNORECASE
    )

    if unsupported:
        return (
            "I can discuss your requirements, but this "
            "test call cannot send emails or book "
            "appointments. What else can I help with?"
        )

    # Convert Markdown and lists to speech-friendly text.
    text = re.sub(
        r"\s+-\s+(?=(?:\*\*)?[A-Za-z][A-Za-z ]{0,25}:)",
        ". ",
        text
    )

    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        r"\1", text
    )
    text = re.sub(r"(?m)^\s*[-?]\s*", "", text)
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)
    text = re.sub(r"[`*_#]", "", text)

    text = text.replace("\r", " ").replace("\n", ". ")
    clean = " ".join(text.split()).strip()

    clean = re.sub(r":\s*\.", ":", clean)
    clean = re.sub(r"([.!?])\s*[.!?]+", r"\1", clean)

    if (
        len(clean) <= max_chars
        and clean.endswith((".", "?", "!"))
    ):
        return clean

    # Prefer complete sentences, avoiding endings such
    # as "Would you" from previously truncated replies.
    prefix = clean[:max_chars]

    boundaries = [
        match.end()
        for match in re.finditer(
            r"[.!?](?=\s|$)",
            prefix
        )
    ]

    if boundaries:
        return prefix[:boundaries[-1]].strip()

    if len(clean) <= max_chars:
        return clean.rstrip(" ,;:") + "."

    # Fallback for responses lacking sentence punctuation.
    clipped = prefix[:max_chars - 4].rsplit(" ", 1)[0]
    return clipped.rstrip(" ,;:") + "..."



def twiml_response(message, action=None):
    response = VoiceResponse()

    if action is not None:
        gather = response.gather(
            input="speech",
            action=action,
            method="POST",
            language="en-IN",
            timeout=5,
            speech_timeout=2,
            action_on_empty_result=True
        )

        gather.say(message)

        # If Gather cannot continue, finish safely.
        response.hangup()
    else:
        response.say(message)
        response.hangup()

    return Response(
        content=str(response),
        media_type="application/xml",
        headers={"Cache-Control": "no-store"}
    )


def attach_gather_routes(
    app, validator, account, origin,
    configured, backend=None, store=None
):
    backend = backend or LocalCRMBackend()
    sessions = {}
    start_lock = asyncio.Lock()

    persistent_flow = None

    if store is not None:
        from leadpilot_ai.twilio_gather_persistent import (
            PersistentGatherFlow
        )
        persistent_flow = PersistentGatherFlow(
            store, backend, origin
        )

    def expire_old_sessions():
        now = time.monotonic()

        for sid, state in list(sessions.items()):
            if now - state["updated"] > SESSION_SECONDS:
                del sessions[sid]

    async def validated_params(request, route):
        if not configured:
            raise HTTPException(
                status_code=503,
                detail="Gateway not configured"
            )

        query = request.url.query

        if route == "/twilio/gather-start":
            if query:
                raise HTTPException(status_code=403)
        elif not re.fullmatch(
            r"step=(0|[1-9][0-9]{0,2})", query
        ):
            raise HTTPException(status_code=403)

        content_type = request.headers.get(
            "content-type", ""
        ).lower()

        if not content_type.startswith(
            "application/x-www-form-urlencoded"
        ):
            raise HTTPException(status_code=415)

        raw = await request.body()

        if len(raw) > 8192:
            raise HTTPException(status_code=413)

        try:
            pairs = parse_qsl(
                raw.decode("utf-8"),
                keep_blank_values=True,
                max_num_fields=32
            )
        except (UnicodeDecodeError, ValueError):
            raise HTTPException(status_code=400)

        params = dict(pairs)

        if len(params) != len(pairs):
            raise HTTPException(status_code=400)

        signature = request.headers.get(
            "x-twilio-signature", ""
        )

        url = origin + route + ("?" + query if query else "")

        if not signature or not validator.validate(
            url, params, signature
        ):
            raise HTTPException(status_code=403)

        if params.get("AccountSid") != account:
            raise HTTPException(status_code=403)

        sid = params.get("CallSid", "")

        if not re.fullmatch(
            r"CA[a-fA-F0-9]{32}", sid
        ):
            raise HTTPException(status_code=403)

        return params, sid


    @app.post(
        "/twilio/gather-start",
        include_in_schema=False
    )
    async def gather_start(request: Request):
        _, call_sid = await validated_params(
            request, "/twilio/gather-start"
        )

        if persistent_flow is not None:
            return await persistent_flow.start(call_sid)

        async with start_lock:
            expire_old_sessions()
            state = sessions.get(call_sid)

            if state is None:
                if len(sessions) >= MAX_SESSIONS:
                    return twiml_response(UNAVAILABLE)

                try:
                    cid = await backend.start()
                except (httpx.HTTPError, RuntimeError, ValueError):
                    return twiml_response(UNAVAILABLE)

                state = {
                    "conversation_id": cid,
                    "turns": 0,
                    "empty": 0,
                    "step": 0,
                    "responses": {},
                    "closed": False,
                    "lock": asyncio.Lock(),
                    "updated": time.monotonic()
                }
                sessions[call_sid] = state

            state["updated"] = time.monotonic()

        return twiml_response(
            "Hello! Welcome to LeadPilot AI. "
            "How can I help your business today?",
            action=origin + "/twilio/gather-turn?step=0"
        )

    @app.post(
        "/twilio/gather-turn",
        include_in_schema=False
    )
    async def gather_turn(request: Request):
        params, call_sid = await validated_params(
            request, "/twilio/gather-turn"
        )

        step = int(request.url.query.split("=", 1)[1])

        if persistent_flow is not None:
            return await persistent_flow.turn(
                call_sid,
                step,
                params.get("SpeechResult", "").strip()
            )

        state = sessions.get(call_sid)

        if state is None:
            raise HTTPException(status_code=409)

        async with state["lock"]:
            if (
                time.monotonic() - state["updated"]
                > SESSION_SECONDS
            ):
                sessions.pop(call_sid, None)
                raise HTTPException(status_code=409)

            state["updated"] = time.monotonic()
            speech = params.get(
                "SpeechResult", ""
            ).strip()

            # Retry of a previously completed callback.
            if step in state["responses"]:
                old_speech, old_response = (
                    state["responses"][step]
                )

                if speech != old_speech:
                    raise HTTPException(status_code=409)

                return old_response

            # Never process callbacks out of order or
            # after a conversation has ended.
            if state["closed"] or step != state["step"]:
                raise HTTPException(status_code=409)

            next_action = (
                origin + "/twilio/gather-turn"
                + f"?step={step + 1}"
            )

            def remember(response, finished=False):
                state["responses"][step] = (
                    speech, response
                )
                state["step"] = step + 1

                if finished:
                    state["closed"] = True

                return response

            if not speech:
                state["empty"] += 1

                if state["empty"] >= 2:
                    return remember(
                        twiml_response(
                            "I could not hear you clearly. "
                            "Goodbye."
                        ),
                        finished=True
                    )

                return remember(
                    twiml_response(
                        "Sorry, I did not catch that. "
                        "Could you say it again?",
                        action=next_action
                    )
                )

            if len(speech) > 1000:
                return remember(
                    twiml_response(
                        "That response was too long. "
                        "Goodbye."
                    ),
                    finished=True
                )

            state["empty"] = 0

            try:
                answer = await backend.chat(
                    state["conversation_id"], speech
                )
            except (httpx.HTTPError, RuntimeError, ValueError):
                return remember(
                    twiml_response(UNAVAILABLE),
                    finished=True
                )

            state["turns"] += 1
            answer = safe_spoken_reply(answer)

            if state["turns"] >= MAX_TURNS:
                final_reply = safe_spoken_reply(
                    answer, max_chars=225
                )
                return remember(
                    twiml_response(
                        final_reply
                        + " Thank you for calling. Goodbye."
                    ),
                    finished=True
                )

            return remember(
                twiml_response(
                    answer,
                    action=next_action
                )
            )

# LeadPilot spoken reply quality v1

# LeadPilot numbered callback replay protection v1

# LeadPilot persistent Gather integration v1
