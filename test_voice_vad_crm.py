import argparse
import asyncio
import os
import time
import wave
import winsound

from collections import deque
from pathlib import Path
from uuid import UUID

import httpx
import numpy as np
import sounddevice as sd

from leadpilot_ai.nvidia_asr_service import NvidiaASRService
from leadpilot_ai.nvidia_tts_service import NvidiaTTSService
from test_voice_with_crm import read_reply, display_lead


ROOT = Path(__file__).resolve().parent
AUDIO_DIR = ROOT / "leadpilot_audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

INPUT_FILE = AUDIO_DIR / "voice_vad_input.wav"
OUTPUT_FILE = AUDIO_DIR / "voice_vad_reply.wav"

API_URL = "http://127.0.0.1:8001"

SAMPLE_RATE = 16000
BLOCK_FRAMES = 320
BLOCK_SECONDS = BLOCK_FRAMES / SAMPLE_RATE

SILENCE_SECONDS = 0.9
SPEECH_TIMEOUT = 12
MAX_SPEECH_SECONDS = 20

MIN_SPEECH_BLOCKS = 10
START_TRIGGER_BLOCKS = 3

SILENCE_BLOCKS = int(
    SILENCE_SECONDS / BLOCK_SECONDS
)


def calculate_rms(samples):
    samples = samples.astype(np.float32)
    return float(np.sqrt(np.mean(samples * samples)))


def record_until_silence():
    print("\nPreparing microphone...")
    print("Stay quiet for a moment during calibration.")

    noise_levels = []
    pre_roll = deque(maxlen=15)
    recorded = []

    speech_started = False
    trigger_blocks = 0
    silent_blocks = 0
    voice_blocks = 0
    overflow_reported = False

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=BLOCK_FRAMES
    ) as stream:

        # Calibrate background microphone noise.
        for _ in range(35):
            data, _ = stream.read(BLOCK_FRAMES)
            noise_levels.append(
                calculate_rms(data[:, 0])
            )

        noise_floor = float(np.median(noise_levels))

        threshold = max(
            250.0,
            min(3000.0, noise_floor * 3.5)
        )

        custom_threshold = os.getenv(
            "LEADPILOT_VAD_THRESHOLD"
        )

        if custom_threshold:
            threshold = float(custom_threshold)

        if threshold <= 0:
            raise ValueError(
                "VAD threshold must be positive"
            )

        print(
            "Noise level:",
            round(noise_floor, 1)
        )
        print(
            "Speech threshold:",
            round(threshold, 1)
        )
        print("\nSpeak now. Recording ends after silence.")

        waiting_started = time.monotonic()
        speech_started_at = None

        while True:
            data, overflowed = stream.read(BLOCK_FRAMES)
            samples = data[:, 0].copy()

            if overflowed and not overflow_reported:
                print("Warning: microphone buffer overflow")
                overflow_reported = True

            rms = calculate_rms(samples)
            is_voice = rms >= threshold

            if not speech_started:
                pre_roll.append(samples)

                if is_voice:
                    trigger_blocks += 1
                else:
                    trigger_blocks = 0

                if trigger_blocks >= START_TRIGGER_BLOCKS:
                    speech_started = True
                    speech_started_at = time.monotonic()

                    recorded.extend(pre_roll)
                    pre_roll.clear()
                    voice_blocks = trigger_blocks

                    print("Speech detected...")

                elif (
                    time.monotonic() - waiting_started
                    >= SPEECH_TIMEOUT
                ):
                    print("No speech detected. Try again.")
                    return None

            else:
                recorded.append(samples)

                if is_voice:
                    voice_blocks += 1
                    silent_blocks = 0
                else:
                    silent_blocks += 1

                if silent_blocks >= SILENCE_BLOCKS:
                    print("End of speech detected.")
                    break

                if (
                    time.monotonic() - speech_started_at
                    >= MAX_SPEECH_SECONDS
                ):
                    print("Maximum recording duration reached.")
                    break

    if voice_blocks < MIN_SPEECH_BLOCKS:
        print("Speech was too short. Please retry.")
        return None

    audio = np.concatenate(recorded).astype(np.int16)

    with wave.open(str(INPUT_FILE), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(audio.tobytes())

    duration = len(audio) / SAMPLE_RATE

    print(
        "Recorded duration:",
        round(duration, 2),
        "seconds"
    )

    return INPUT_FILE


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
    print("      LEADPILOT AI - SPEECH ACTIVATED CRM")
    print("=" * 52)
    print("Microphone:", sd.query_devices(kind="input")["name"])

    async with httpx.AsyncClient(
        base_url=API_URL,
        timeout=180
    ) as client:

        health = await client.get("/health")
        health.raise_for_status()

        if args.conversation_id:
            cid = str(UUID(args.conversation_id))

            response = await client.get(
                f"/api/conversations/{cid}"
            )
            response.raise_for_status()

            print("Resumed existing CRM conversation")

        else:
            response = await client.post(
                "/api/conversations/start"
            )
            response.raise_for_status()

            cid = response.json().get(
                "conversation_id"
            )

            if not cid:
                raise RuntimeError(
                    "Conversation ID not returned"
                )

            print("Created new CRM conversation")

        print("Conversation ID:", cid)

        while True:
            command = input(
                "\nENTER to speak / q to quit: "
            ).strip().lower()

            if command in ("q", "quit", "exit"):
                break

            try:
                path = record_until_silence()

                if path is None:
                    continue

                print("\n[NVIDIA ASR] Transcribing...")

                started = time.perf_counter()
                transcript = await asr.transcribe(path)
                asr_seconds = time.perf_counter() - started

                print("\nCUSTOMER:")
                print(transcript)

                print("\n[NVIDIA NEMOTRON + CRM]")

                started = time.perf_counter()

                response = await client.post(
                    f"/api/conversations/{cid}/chat",
                    json={"message": transcript}
                )
                response.raise_for_status()

                result = response.json()
                reply = read_reply(result)

                llm_seconds = time.perf_counter() - started

                print("\nLEADPILOT AI:")
                print(reply)

                display_lead(result)

                print("\n[NVIDIA MAGPIE TTS]")

                started = time.perf_counter()

                audio_path = await tts.synthesize(
                    text=reply,
                    output_path=OUTPUT_FILE
                )

                tts_seconds = time.perf_counter() - started

                print("\n[PLAYING AI RESPONSE]")
                winsound.PlaySound(
                    str(audio_path),
                    winsound.SND_FILENAME
                )

                print("\nLATENCY REPORT")
                print("ASR:", round(asr_seconds, 2), "seconds")
                print("CRM + LLM:", round(llm_seconds, 2), "seconds")
                print("TTS:", round(tts_seconds, 2), "seconds")

                total = (
                    asr_seconds
                    + llm_seconds
                    + tts_seconds
                )

                print(
                    "Total processing:",
                    round(total, 2),
                    "seconds"
                )
                print("Voice turn completed.")

            except httpx.HTTPStatusError as error:
                print(
                    "API ERROR:",
                    error.response.status_code
                )
                print(error.response.text[:500])

            except Exception as error:
                print(
                    "VOICE ERROR:",
                    type(error).__name__,
                    str(error)
                )

        saved = await client.get(
            f"/api/conversations/{cid}"
        )
        saved.raise_for_status()

        result = saved.json()

        print("\nFINAL CRM RESULTS")
        print(
            "Messages saved:",
            len(result.get("messages", []))
        )
        display_lead(result)

        print("\nConversation ID:", cid)
        print("Session ended. No booking created.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nVoice session stopped")
