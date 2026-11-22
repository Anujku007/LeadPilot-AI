import asyncio
import wave
from pathlib import Path

import sounddevice as sd

from leadpilot_ai.nvidia_asr_service import (
    NvidiaASRService
)

ROOT = Path(__file__).resolve().parent

AUDIO_DIR = ROOT / "leadpilot_audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_FILE = AUDIO_DIR / "microphone_test.wav"

SAMPLE_RATE = 16000
DURATION_SECONDS = 7


def record_microphone():
    print("\nChecking microphone...")

    device = sd.query_devices(kind="input")

    print("Input device:", device["name"])
    print()
    input("Press ENTER when you are ready to speak...")

    print("\nRecording started!")
    print("Speak clearly for 7 seconds.")
    print()

    audio = sd.rec(
        int(DURATION_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16"
    )

    sd.wait()

    with wave.open(str(AUDIO_FILE), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(audio.tobytes())

    print("Recording completed.")
    print("Audio saved:", AUDIO_FILE)

    if not audio.any():
        raise RuntimeError(
            "Microphone recording contains silence. "
            "Check Windows microphone permissions."
        )

    return AUDIO_FILE


async def main():
    audio_path = record_microphone()

    print("\nSending speech to NVIDIA Parakeet ASR...")

    asr = NvidiaASRService()

    transcript = await asr.transcribe(audio_path)

    print("\n===================================")
    print("SUCCESS: SPEECH RECOGNIZED")
    print("===================================")

    print("\nYou said:")
    print(transcript)

    print("\nNVIDIA Speech-to-Text is working!")


if __name__ == "__main__":
    asyncio.run(main())
