import httpx
from fastapi import HTTPException
from fastapi.responses import Response

from leadpilot_ai.twilio_gather_fallback import (
    MAX_TURNS,
    UNAVAILABLE,
    safe_spoken_reply,
    twiml_response
)


class PersistentGatherFlow:
    def __init__(self, store, backend, origin):
        self.store = store
        self.backend = backend
        self.origin = origin

    @staticmethod
    def replay(xml):
        return Response(
            content=xml,
            media_type="application/xml",
            headers={"Cache-Control": "no-store"}
        )

    @staticmethod
    def xml_body(response):
        return response.body.decode("utf-8")

    async def start(self, call_sid):
        claim = self.store.claim_start(call_sid)

        if claim["status"] == "cached":
            return self.replay(claim["twiml"])

        if claim["status"] == "pending":
            return twiml_response(UNAVAILABLE)

        if claim["status"] != "new":
            raise HTTPException(status_code=409)

        try:
            conversation_id = await self.backend.start()
        except (
            httpx.HTTPError,
            RuntimeError,
            ValueError
        ):
            # Keep the start claim pending: we cannot
            # assume the CRM operation did not succeed.
            return twiml_response(UNAVAILABLE)

        response = twiml_response(
            "Hello! Welcome to LeadPilot AI. "
            "How can I help your business today?",
            action=(
                self.origin
                + "/twilio/gather-turn?step=0"
            )
        )

        self.store.complete_start(
            call_sid,
            conversation_id,
            self.xml_body(response)
        )

        return response

    def complete(
        self, call_sid, step, speech,
        response, turns, empty, closed=False
    ):
        self.store.complete_turn(
            call_sid=call_sid,
            step=step,
            speech=speech,
            twiml=self.xml_body(response),
            turns=turns,
            empty=empty,
            closed=closed
        )

        return response

    async def turn(self, call_sid, step, speech):
        claim = self.store.claim_turn(
            call_sid, step, speech
        )

        status = claim["status"]

        if status == "cached":
            return self.replay(claim["twiml"])

        if status == "pending":
            # Do not re-run a possibly completed CRM
            # request after a crash or concurrent retry.
            return twiml_response(UNAVAILABLE)

        if status != "new":
            raise HTTPException(status_code=409)

        turns = claim["turns"]
        empty = claim["empty"]

        next_action = (
            self.origin
            + f"/twilio/gather-turn?step={step + 1}"
        )

        if not speech:
            empty += 1

            if empty >= 2:
                response = twiml_response(
                    "I could not hear you clearly. Goodbye."
                )

                return self.complete(
                    call_sid, step, speech,
                    response, turns, empty,
                    closed=True
                )

            response = twiml_response(
                "Sorry, I did not catch that. "
                "Could you say it again?",
                action=next_action
            )

            return self.complete(
                call_sid, step, speech,
                response, turns, empty
            )

        if len(speech) > 1000:
            response = twiml_response(
                "That response was too long. Goodbye."
            )

            return self.complete(
                call_sid, step, speech,
                response, turns, empty,
                closed=True
            )

        try:
            answer = await self.backend.chat(
                claim["conversation_id"],
                speech
            )
        except (
            httpx.HTTPError,
            RuntimeError,
            ValueError
        ):
            # Preserve the processing claim instead
            # of potentially duplicating a CRM turn.
            return twiml_response(UNAVAILABLE)

        turns += 1
        empty = 0

        if turns >= MAX_TURNS:
            final_answer = safe_spoken_reply(
                answer,
                max_chars=225
            )

            response = twiml_response(
                final_answer
                + " Thank you for calling. Goodbye."
            )

            return self.complete(
                call_sid, step, speech,
                response, turns, empty,
                closed=True
            )

        response = twiml_response(
            safe_spoken_reply(answer),
            action=next_action
        )

        return self.complete(
            call_sid, step, speech,
            response, turns, empty
        )
