import argparse
import asyncio
import time
import winsound
from datetime import datetime, timezone
from uuid import UUID

import httpx
import sounddevice as sd

from leadpilot_ai.nvidia_asr_service import NvidiaASRService
from leadpilot_ai.nvidia_tts_service import NvidiaTTSService
from leadpilot_ai.voice_booking_commands import (
    is_confirmation, is_cancel, is_change,
    is_agreement, is_schedule_request, spoken_slot,
    is_email_input, guard_email_delivery_reply
)
from test_voice_vad_crm import (
    record_until_silence, OUTPUT_FILE
)
from test_voice_with_crm import read_reply, display_lead

BASE_URL = "http://127.0.0.1:8001"


def profile_from(data):
    if not isinstance(data, dict):
        return {}

    for key in (
        "lead", "lead_profile",
        "qualification", "lead_qualification"
    ):
        if isinstance(data.get(key), dict):
            return data[key]

    return {}


async def say(tts, message):
    print("\nLEADPILOT AI:", message)

    path = await tts.synthesize(
        message, OUTPUT_FILE
    )

    winsound.PlaySound(
        str(path), winsound.SND_FILENAME
    )


async def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--conversation-id", required=True
    )

    parser.add_argument(
        "--allow-real-booking",
        action="store_true",
        help="Enable real booking with extra confirmation"
    )

    args = parser.parse_args()
    cid = str(UUID(args.conversation_id))

    asr = NvidiaASRService()
    tts = NvidiaTTSService()

    print("=" * 52)
    print("     LEADPILOT AI - VOICE + CRM + CALENDAR")
    print("=" * 52)
    print("Microphone:", sd.query_devices(kind="input")["name"])

    booking_mode = (
        "ARMED" if args.allow_real_booking
        else "DISABLED - SAFE TEST"
    )
    print("Real calendar booking:", booking_mode)

    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=180
    ) as client:

        health = await client.get("/health")
        health.raise_for_status()

        saved = await client.get(
            f"/api/conversations/{cid}"
        )
        saved.raise_for_status()

        lead = profile_from(saved.json())
        hot = lead.get("category") == "Hot"

        print("Lead category:", lead.get("category"))
        print("Lead score:", lead.get("score"))
        print("Conversation ID:", cid)

        print(
            "Say 'schedule appointment for tomorrow "
            "at 11 AM IST' to request a time."
        )

        state = "chat"
        pending = None
        offer_pending = hot

        while True:
            command = input(
                "\nENTER to speak / q to quit: "
            ).strip().lower()

            if command in ("q", "quit", "exit"):
                break

            try:
                audio = record_until_silence()

                if audio is None:
                    continue

                start_time = time.perf_counter()

                transcript = await asr.transcribe(
                    audio
                )

                print("\nCUSTOMER:", transcript)
                print(
                    "ASR latency:",
                    round(time.perf_counter() - start_time, 2),
                    "seconds"
                )

                # Never let the LLM directly confirm booking.
                if state == "confirm":

                    if is_cancel(transcript):
                        pending = None
                        state = "chat"
                        reply = (
                            "Cancelled. No new appointment "
                            "was booked."
                        )

                    elif (
                        is_change(transcript)
                        or is_schedule_request(transcript)
                    ):
                        pending = None
                        state = "date"
                        reply = (
                            "Please tell me your preferred "
                            "new date and time in IST."
                        )

                    elif is_confirmation(transcript):
                        expires_at = datetime.fromisoformat(
                            pending["expires_at"]
                        )

                        if (
                            datetime.now(timezone.utc)
                            >= expires_at
                        ):
                            pending = None
                            state = "date"
                            reply = (
                                "That proposal expired. "
                                "Please choose a new time."
                            )

                        elif not args.allow_real_booking:
                            reply = (
                                "Your confirmation was recognized. "
                                "This is safe test mode. "
                                "No appointment was booked."
                            )

                        else:
                            print(
                                "\nREAL BOOKING REQUEST:",
                                spoken_slot(pending["start"])
                            )

                            typed = input(
                                "Type BOOK TEST to create "
                                "the calendar event: "
                            )

                            if typed != "BOOK TEST":
                                reply = (
                                    "Booking cancelled at the "
                                    "final safety check."
                                )

                            else:
                                response = await client.post(
                                    f"/api/conversations/"
                                    f"{cid}/confirm-appointment",
                                    json={
                                        "proposal_id":
                                            pending["proposal_id"],
                                        "confirmation_text":
                                            "CONFIRM BOOKING"
                                    }
                                )

                                response.raise_for_status()
                                booking = response.json()

                                if not booking.get("booking_created"):
                                    raise RuntimeError(
                                        "Booking was not confirmed"
                                    )

                                print(
                                    "GOOGLE EVENT ID:",
                                    booking.get("event_id")
                                )

                                reply = (
                                    "Your appointment is confirmed "
                                    "for "
                                    + spoken_slot(booking["start"])
                                    + "."
                                )

                                pending = None
                                state = "chat"

                    else:
                        reply = (
                            "Nothing has been booked. "
                            "Say confirm booking, change time, "
                            "or cancel."
                        )

                elif state == "date" and is_cancel(transcript):
                    state = "chat"
                    reply = "Scheduling cancelled."


                elif hot and is_email_input(transcript):
                    state = "date"
                    offer_pending = False
                    reply = (
                        "I cannot send emails or calendar "
                        "links from this prototype. "
                        "No email has been sent. "
                        "Please tell me your preferred "
                        "date and time in IST."
                    )

                elif (
                    state == "date"
                    or (
                        hot
                        and is_schedule_request(transcript)
                    )
                    or (
                        hot
                        and offer_pending
                        and is_agreement(transcript)
                    )
                ):
                    state = "date"
                    offer_pending = False

                    if is_agreement(transcript):
                        reply = (
                            "What date and time would you "
                            "prefer in IST?"
                        )

                    else:
                        response = await client.post(
                            f"/api/conversations/"
                            f"{cid}/schedule-request",
                            json={"message": transcript}
                        )

                        response.raise_for_status()
                        result = response.json()
                        proposal = result.get("proposal")

                        if (
                            result.get("available")
                            and isinstance(proposal, dict)
                        ):
                            if (
                                proposal.get("booking_created")
                                or not proposal.get(
                                    "confirmation_required"
                                )
                            ):
                                raise RuntimeError(
                                    "Unexpected proposal state"
                                )

                            for field in (
                                "proposal_id", "expires_at",
                                "start", "end"
                            ):
                                if not proposal.get(field):
                                    raise RuntimeError(
                                        "Missing field: " + field
                                    )

                            pending = proposal
                            state = "confirm"

                            reply = (
                                "Your 30-minute consultation on "
                                + spoken_slot(proposal["start"])
                                + " is available. "
                                "Say confirm booking to accept, "
                                "change time, or cancel."
                            )

                        elif result.get("understood") is False:
                            reply = (
                                "Please specify a date and "
                                "time in IST. "
                                "No booking was made."
                            )

                        else:
                            reply = (
                                "That time is unavailable. "
                                "Please choose another time."
                            )

                elif (
                    is_schedule_request(transcript)
                    and not hot
                ):
                    reply = (
                        "Let's complete your lead "
                        "qualification first."
                    )

                else:
                    response = await client.post(
                        f"/api/conversations/{cid}/chat",
                        json={"message": transcript}
                    )

                    response.raise_for_status()
                    result = response.json()

                    reply = read_reply(result)
                    display_lead(result)

                    lead = profile_from(result)
                    hot = (
                        lead.get("category") == "Hot"
                        or hot
                    )

                    offer_pending = hot and (
                        "would you like to schedule"
                        in reply.lower()
                        or "would you like to book"
                        in reply.lower()
                    )

                    if hot:
                        print(
                            "TIP: Say 'schedule appointment' "
                            "to request a time."
                        )


                # Never speak an unsupported delivery claim.
                reply, guarded = guard_email_delivery_reply(reply)

                if guarded and hot:
                    state = "date"
                    offer_pending = False

                await say(tts, reply)
                print("Scheduling state:", state)

            except httpx.HTTPStatusError as error:
                print(
                    "API ERROR:",
                    error.response.status_code
                )
                print(error.response.text[:500])
                print(
                    "If a booking failed or timed out, "
                    "check Google Calendar before retrying."
                )

            except Exception as error:
                print(
                    "VOICE ERROR:",
                    type(error).__name__,
                    str(error)
                )
                print("No automatic retry attempted.")

        print("\nSESSION ENDED")
        print("Conversation ID:", cid)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user")

# LeadPilot voice scheduling safety patch v1
