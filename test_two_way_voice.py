import asyncio
import wave
import winsound
from pathlib import Path

import sounddevice as sd

from leadpilot_ai.nvidia_asr_service import (
    NvidiaASRService
)
from leadpilot_ai.nvidia_llm_service import (
    NvidiaLLMService
)
from leadpilot_ai.nvidia_tts_service import (
    NvidiaTTSService
)

ROOT = Path(__file__).resolve().parent
AUDIO_DIR = ROOT / "leadpilot_audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

INPUT_FILE = AUDIO_DIR / "voice_input.wav"
OUTPUT_FILE = AUDIO_DIR / "voice_response.wav"

SAMPLE_RATE = 16000
RECORD_SECONDS = 8


def record_audio():
    print("\nRecording for 8 seconds. Speak now!")

    audio = sd.rec(
        int(RECORD_SECONDS * SAMPLE_RATE),
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
        raise RuntimeError(
            "No microphone signal detected."
        )

    print("Recording completed.")
    return INPUT_FILE


def build_prompt(history):
    context = ""

    for customer, assistant in history[-6:]:
        context += (
            f"\nCustomer: {customer}"
            f"\nAssistant: {assistant}\n"
        )

    return (
        "You are LeadPilot AI, a friendly and "
        "professional AI sales assistant. "
        "Your goal is to qualify potential customers "
        "using budget, authority, need, and timeline. "
        "Ask one relevant question at a time. "
        "Keep every reply conversational and "
        "under 45 words so it sounds natural aloud. "
        "Use information previously provided by "
        "the customer. Never claim that an "
        "appointment was booked. "
        "This standalone voice test does not "
        "have access to booking tools.\n"
        "Previous conversation for context:\n"
        + context
    )


async def main():
    asr = NvidiaASRService()
    llm = NvidiaLLMService()
    tts = NvidiaTTSService()

    history = []

    print("=" * 50)
    print("        LEADPILOT AI VOICE ASSISTANT")
    print("=" * 50)

    device = sd.query_devices(kind="input")
    print("Microphone:", device["name"])
    print("Voice mode: Turn-by-turn")
    print("Type q to exit.")

    while True:
        command = input(
            "\nPress ENTER to speak, or q to quit: "
        ).strip().lower()

        if command in ("q", "quit", "exit"):
            print("\nLeadPilot AI voice session ended.")
            break

        try:
            # 1. Record customer speech
            audio_file = record_audio()

            # 2. Convert speech to text
            print("\n[NVIDIA ASR] Recognizing speech...")

            transcript = await asr.transcribe(
                audio_file
            )

            print("\nYOU SAID:")
            print(transcript)

            # 3. Generate the AI response
            print("\n[NVIDIA LLM] Thinking...")

            response = await llm.generate_response(
                message=transcript,
                system_prompt=build_prompt(history)
            )

            if (
                not isinstance(response, str)
                or not response.strip()
            ):
                raise RuntimeError(
                    "NVIDIA LLM returned an empty response."
                )

            response = response.strip()

            print("\nLEADPILOT AI:")
            print(response)

            # Keep short-term conversation memory
            history.append((transcript, response))

            # 4. Convert AI response to speech
            print("\n[NVIDIA TTS] Generating voice...")

            speech_file = await tts.synthesize(
                text=response,
                output_path=OUTPUT_FILE
            )

            # 5. Play the AI response
            print("\n[PLAYING AI VOICE]")

            try:
                winsound.PlaySound(
                    str(speech_file),
                    winsound.SND_FILENAME
                )
            except RuntimeError:
                print(
                    "Automatic playback failed. "
                    "Open this WAV file manually:"
                )
                print(speech_file)

            print("\nTurn completed.")

        except Exception as error:
            print("\nVOICE TURN FAILED")
            print(
                f"{type(error).__name__}: {error}"
            )
            print("You can retry the next turn.")

    print("Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nVoice session stopped.")
