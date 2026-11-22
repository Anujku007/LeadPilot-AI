import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("NVIDIA_API_KEY")

TTS_URL = (
    "https://877104f7-e885-42b9-8de8-f6e4c6303969"
    ".invocation.api.nvcf.nvidia.com/v1/audio/synthesize"
)

OUTPUT = ROOT / "leadpilot_audio"
OUTPUT.mkdir(exist_ok=True)

AUDIO_FILE = OUTPUT / "nvidia_voice_test.wav"


def test_tts():
    if not API_KEY:
        raise RuntimeError("NVIDIA_API_KEY missing in .env")

    print("Connecting to NVIDIA Magpie TTS...")

    data = {
        "text": (
            "Hello! I am LeadPilot AI, your virtual "
            "sales assistant. How can I help you today?"
        ),
        "language": "en-US",
        "voice": "Magpie-Multilingual.EN-US.Aria",
        "encoding": "LINEAR_PCM",
        "sample_rate_hz": "44100"
    }

    # NVIDIA's HTTP example uses multipart form data.
    files = {
        key: (None, str(value))
        for key, value in data.items()
    }

    with httpx.Client(timeout=120) as client:
        response = client.post(
            TTS_URL,
            headers={
                "Authorization": f"Bearer {API_KEY}"
            },
            files=files
        )

    if response.status_code != 200:
        print("API status:", response.status_code)
        print("Details:", response.text[:400])
        raise RuntimeError("NVIDIA TTS request failed")

    audio = response.content

    if not (
        audio[:4] == b"RIFF"
        and audio[8:12] == b"WAVE"
    ):
        print(
            "Unexpected audio format:",
            response.headers.get("content-type")
        )
        raise RuntimeError(
            "Audio was returned, but WAV format was not verified."
        )

    AUDIO_FILE.write_bytes(audio)

    print("SUCCESS: NVIDIA TTS generated speech!")
    print("Audio file:", AUDIO_FILE)
    print("Size:", len(audio), "bytes")


if __name__ == "__main__":
    test_tts()
