import argparse
import asyncio
import wave
import winsound
from pathlib import Path
from uuid import UUID

import httpx
import sounddevice as sd

from leadpilot_ai.nvidia_asr_service import NvidiaASRService
from leadpilot_ai.nvidia_tts_service import NvidiaTTSService

ROOT = Path(__file__).resolve().parent
AUDIO_DIR = ROOT / "leadpilot_audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

INPUT_FILE = AUDIO_DIR / "voice_crm_input.wav"
OUTPUT_FILE = AUDIO_DIR / "voice_crm_reply.wav"

API_URL = "http://127.0.0.1:8001"
SAMPLE_RATE = 16000
RECORD_SECONDS = 8


def record_audio():
    print("\nRecording for 8 seconds. Speak now!")

    audio = sd.rec(
        int(SAMPLE_RATE * RECORD_SECONDS),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16"
    )
    sd.wait()

    with wave.open(str(INPUT_FILE), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(audio.tobytes())

    if not audio.any():
        raise RuntimeError("No microphone signal detected")

    return INPUT_FILE


def read_reply(data):
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected chat API response")

    # Support commonly used response field names.
    for key in (
        "assistant_response",
        "ai_response",
        "assistant_reply",
        "reply",
        "response",
        "answer",
        "assistant_message",
        "assistant"
    ):
        value = data.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

        if isinstance(value, dict):
            for field in ("content", "text", "message", "reply"):
                text = value.get(field)
                if isinstance(text, str) and text.strip():
                    return text.strip()

    messages = data.get("messages")

    if isinstance(messages, list):
        for item in reversed(messages):
            if (
                isinstance(item, dict)
                and item.get("role") == "assistant"
            ):
                content = item.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()

    raise RuntimeError(
        "Could not identify assistant reply. "
        f"Response fields: {list(data.keys())}"
    )


def display_lead(data):
    for key in (
        "lead",
        "lead_profile",
        "qualification",
        "lead_qualification"
    ):
        lead = data.get(key)

        if isinstance(lead, dict):
            score = lead.get("score")
            category = lead.get("category")

            if score is not None:
                print("\nLEAD QUALIFICATION")
                print("Score:", score)
                print("Category:", category)
                return


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--conversation-id",
        help="Resume an existing CRM conversation"
    )
    args = parser.parse_args()

    asr = NvidiaASRService()
    tts = NvidiaTTSService()

    print("=" * 52)
    print("       LEADPILOT AI - VOICE + CRM")
    print("=" * 52)

    print("Microphone:", sd.query_devices(kind="input")["name"])

    async with httpx.AsyncClient(
        base_url=API_URL,
        timeout=180
    ) as client:

        try:
            health = await client.get("/health")
            health.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(
                "FastAPI is unavailable on port 8001. "
                "Start Uvicorn in another terminal."
            ) from error

        print("FastAPI connection: OK")

        if args.conversation_id:
            conversation_id = str(
                UUID(args.conversation_id)
            )

            check = await client.get(
                f"/api/conversations/{conversation_id}"
            )
            check.raise_for_status()
            print("Resuming saved conversation")

        else:
            started = await client.post(
                "/api/conversations/start"
            )
            started.raise_for_status()

            data = started.json()

            conversation_id = data.get(
                "conversation_id"
            )

            if not conversation_id:
                raise RuntimeError(
                    "Conversation start response "
                    f"missing conversation_id: {list(data)}"
                )

            print("New CRM conversation created")

        print("Conversation ID:", conversation_id)
        print("Press ENTER to speak, q to exit.")

        while True:
            command = input(
                "\nENTER to speak / q to quit: "
            ).strip().lower()

            if command in ("q", "quit", "exit"):
                break

            try:
                audio_file = record_audio()

                print("\n[1/4] NVIDIA ASR...")
                transcript = await asr.transcribe(
                    audio_file
                )

                print("\nCUSTOMER:")
                print(transcript)

                print("\n[2/4] CRM + NVIDIA Nemotron...")

                response = await client.post(
                    f"/api/conversations/{conversation_id}/chat",
                    json={"message": transcript}
                )
                response.raise_for_status()

                result = response.json()
                reply = read_reply(result)

                print("\nLEADPILOT AI:")
                print(reply)

                display_lead(result)

                print("\n[3/4] NVIDIA Magpie TTS...")

                audio_response = await tts.synthesize(
                    text=reply,
                    output_path=OUTPUT_FILE
                )

                print("\n[4/4] Playing response...")

                winsound.PlaySound(
                    str(audio_response),
                    winsound.SND_FILENAME
                )

                print("\nVoice turn completed and sent to CRM.")

            except httpx.HTTPStatusError as error:
                print("\nAPI ERROR:", error.response.status_code)
                print(error.response.text[:500])

            except Exception as error:
                print(
                    "\nVOICE ERROR:",
                    type(error).__name__,
                    str(error)
                )

        print("\nRetrieving saved conversation...")

        saved = await client.get(
            f"/api/conversations/{conversation_id}"
        )

        if saved.is_success:
            data = saved.json()
            messages = data.get("messages")

            if isinstance(messages, list):
                print("CRM messages saved:", len(messages))

            display_lead(data)
        else:
            print("Could not retrieve CRM conversation.")

        print("\nSESSION ENDED")
        print("Conversation ID:", conversation_id)
        print("Save this ID to resume later.")
        print("No appointment booking was requested.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user")
