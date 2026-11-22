
import asyncio
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("NVIDIA_API_KEY")
MODEL = os.getenv("NVIDIA_MODEL")
BASE_URL = os.getenv(
    "NVIDIA_BASE_URL",
    "https://integrate.api.nvidia.com/v1"
)


async def test_nvidia():
    if not API_KEY or not MODEL:
        print("Missing NVIDIA_API_KEY or NVIDIA_MODEL")
        return

    print("Connecting to NVIDIA NIM...")

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are LeadPilot AI, a helpful "
                    "AI sales assistant. Ask customers "
                    "about their business requirements "
                    "one question at a time."
                )
            },
            {
                "role": "user",
                "content": (
                    "Hello! I need an AI CRM "
                    "for my sales business."
                )
            }
        ],
        "temperature": 0.3,
        "max_tokens": 512,
        "stream": False,
        "chat_template_kwargs": {
            "enable_thinking": False
        }
    }

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{BASE_URL.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}"
                },
                json=payload
            )

            response.raise_for_status()
            result = response.json()

            choice = result["choices"][0]
            message = choice["message"]

            print("\nNVIDIA API request successful!")
            print("Finish reason:", choice.get("finish_reason"))

            answer = message.get("content")

            if answer:
                print("\nLeadPilot AI Response:")
                print(answer)
            else:
                print("\nNo visible response generated.")
                print("Response fields:", list(message.keys()))
                print("Token usage:", result.get("usage"))

    except httpx.HTTPStatusError as error:
        print("API error:", error.response.status_code)

    except httpx.RequestError as error:
        print("Connection error:", error)


if __name__ == "__main__":
    asyncio.run(test_nvidia())
