import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class NvidiaLLMService:
    def __init__(self):
        self.api_key = os.getenv("NVIDIA_API_KEY")
        self.model = os.getenv("NVIDIA_MODEL")
        self.base_url = os.getenv(
            "NVIDIA_BASE_URL",
            "https://integrate.api.nvidia.com/v1"
        )

    async def generate_response(self, message, history=None, system_prompt=None):
        if not self.api_key or not self.model:
            raise ValueError(
                "NVIDIA_API_KEY or NVIDIA_MODEL is missing"
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are LeadPilot AI, a professional "
                    "AI sales assistant. Understand customer "
                    "requirements, qualify leads and ask "
                    "one relevant question at a time. "
                    "Never claim an appointment is booked "
                    "unless a booking tool confirms it."
                )
            }
        ]

        if system_prompt is not None:
            messages[0]["content"] = system_prompt

        messages.extend(history or [])
        messages.append({
            "role": "user",
            "content": message
        })

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 512,
            "stream": False,
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        }

        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}"
                },
                json=payload
            )

            response.raise_for_status()
            result = response.json()

        answer = result["choices"][0]["message"].get("content")

        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError(
                "NVIDIA returned no visible answer"
            )

        return answer.strip()
