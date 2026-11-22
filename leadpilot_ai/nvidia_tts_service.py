import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEFAULT_TTS_URL = (
    "https://877104f7-e885-42b9-8de8-f6e4c6303969"
    ".invocation.api.nvcf.nvidia.com/v1/audio/synthesize"
)


class NvidiaTTSService:

    def __init__(self):
        self.api_key = os.getenv("NVIDIA_API_KEY")
        self.url = os.getenv(
            "NVIDIA_TTS_URL",
            DEFAULT_TTS_URL
        )

    async def synthesize(self, text, output_path):
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY missing")

        if not text or not text.strip():
            raise ValueError("Speech text cannot be empty")

        payload = {
            "text": text,
            "language": "en-US",
            "voice": "Magpie-Multilingual.EN-US.Aria",
            "encoding": "LINEAR_PCM",
            "sample_rate_hz": "44100"
        }

        files = {
            key: (None, str(value))
            for key, value in payload.items()
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                self.url,
                headers={
                    "Authorization": f"Bearer {self.api_key}"
                },
                files=files
            )

            response.raise_for_status()

        audio = response.content

        if not (
            audio[:4] == b"RIFF"
            and audio[8:12] == b"WAVE"
        ):
            raise RuntimeError(
                "NVIDIA returned an unexpected audio format"
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(
            parents=True, exist_ok=True
        )

        output_path.write_bytes(audio)

        return str(output_path)
