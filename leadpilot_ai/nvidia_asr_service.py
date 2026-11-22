import os
import wave
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEFAULT_ASR_URL = (
    "https://1598d209-5e27-4d3c-8079-4751568b1081"
    ".invocation.api.nvcf.nvidia.com/v1/audio/transcriptions"
)


class NvidiaASRService:

    def __init__(self):
        self.api_key = os.getenv("NVIDIA_API_KEY")
        self.url = os.getenv(
            "NVIDIA_ASR_URL",
            DEFAULT_ASR_URL
        )

    async def transcribe(self, audio_path):
        if not self.api_key:
            raise RuntimeError(
                "NVIDIA_API_KEY missing in .env"
            )

        audio_path = Path(audio_path)

        if not audio_path.is_file():
            raise FileNotFoundError(audio_path)

        # Validate microphone audio before uploading.
        with wave.open(str(audio_path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.getnframes()

        if channels != 1:
            raise ValueError("Audio must be mono")

        if sample_width != 2:
            raise ValueError("Audio must be 16-bit PCM")

        if sample_rate != 16000:
            raise ValueError("Audio must be 16000 Hz")

        if frames == 0:
            raise ValueError("Audio recording is empty")

        async with httpx.AsyncClient(
            timeout=120
        ) as client:

            with audio_path.open("rb") as audio_file:
                response = await client.post(
                    self.url,
                    headers={
                        "Authorization":
                        f"Bearer {self.api_key}"
                    },
                    data={
                        "language": "en-US",
                        "response_format": "json"
                    },
                    files={
                        "file": (
                            audio_path.name,
                            audio_file,
                            "audio/wav"
                        )
                    }
                )

        if response.status_code != 200:
            print("NVIDIA ASR HTTP status:",
                  response.status_code)
            print("API details:", response.text[:500])
            response.raise_for_status()

        result = response.json()

        if not isinstance(result, dict):
            raise RuntimeError(
                "Unexpected NVIDIA ASR response"
            )

        transcript = result.get("text", "")

        if not isinstance(transcript, str):
            raise RuntimeError(
                "Invalid transcript format"
            )

        transcript = transcript.strip()

        if not transcript:
            raise RuntimeError(
                "NVIDIA returned an empty transcript"
            )

        return transcript
