import asyncio
from pathlib import Path

from leadpilot_ai.nvidia_llm_service import NvidiaLLMService
from leadpilot_ai.nvidia_tts_service import NvidiaTTSService

ROOT = Path(__file__).resolve().parent

OUTPUT = (
    ROOT / "leadpilot_audio" / "leadpilot_ai_response.wav"
)


async def main():
    llm = NvidiaLLMService()
    tts = NvidiaTTSService()

    print("Connecting to NVIDIA Nemotron...")

    reply = await llm.generate_response(
        message=(
            "I manage a sales team of 20 employees. "
            "We need a CRM for automated follow-ups."
        ),
        system_prompt=(
            "You are LeadPilot AI, a professional "
            "AI sales assistant. "
            "Respond naturally in fewer than 35 words. "
            "Ask one relevant qualification question. "
            "Do not invent product features or prices."
        )
    )

    print("\nLeadPilot AI response:")
    print(reply)

    print("\nGenerating voice using NVIDIA Magpie...")

    path = await tts.synthesize(
        text=reply,
        output_path=OUTPUT
    )

    print("\nSUCCESS: AI response converted to speech")
    print("Audio saved:", path)


if __name__ == "__main__":
    asyncio.run(main())
