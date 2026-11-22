import logging
import tempfile
import wave
from collections import deque
from pathlib import Path
from uuid import UUID

import httpx
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .nvidia_asr_service import NvidiaASRService
from .nvidia_tts_service import NvidiaTTSService
from .twilio_stream import LOCAL_HOSTS, StreamState
from .twilio_audio_out import (
    wav_to_mulaw8k, outbound_packets, mark_packet
)

logger = logging.getLogger(__name__)
router = APIRouter()

FRAME_BYTES = 640
SILENCE_FRAMES = 30
VOICE_THRESHOLD = 250.0


class SpeechSegmenter:
    """Simple local energy VAD over 20 ms PCM16 frames."""

    def __init__(self):
        self.pending = bytearray()
        self.pre_roll = deque(maxlen=10)
        self.frames = []
        self.started = False
        self.consecutive = 0
        self.voice_frames = 0
        self.quiet_frames = 0

    def feed(self, pcm):
        self.pending.extend(pcm)

        while len(self.pending) >= FRAME_BYTES:
            frame = bytes(self.pending[:FRAME_BYTES])
            del self.pending[:FRAME_BYTES]

            samples = np.frombuffer(
                frame, dtype="<i2"
            ).astype(np.float32)

            rms = float(np.sqrt(
                np.mean(samples * samples)
            ))

            loud = rms >= VOICE_THRESHOLD

            if not self.started:
                self.pre_roll.append(frame)
                self.consecutive = (
                    self.consecutive + 1 if loud else 0
                )

                if self.consecutive >= 3:
                    self.started = True
                    self.frames = list(self.pre_roll)
                    self.pre_roll.clear()
                    self.voice_frames = 3

            else:
                self.frames.append(frame)

                if loud:
                    self.voice_frames += 1
                    self.quiet_frames = 0
                else:
                    self.quiet_frames += 1

                if (
                    self.voice_frames >= 8
                    and self.quiet_frames >= SILENCE_FRAMES
                ):
                    result = b"".join(self.frames)
                    self.__init__()
                    return result

                if len(self.frames) >= 1000:
                    result = b"".join(self.frames)
                    self.__init__()
                    return result

        return None


def extract_reply(data):
    if not isinstance(data, dict):
        raise ValueError("Invalid CRM response")

    for field in (
        "assistant_response", "ai_response",
        "assistant_reply", "reply",
        "response", "answer"
    ):
        value = data.get(field)

        if isinstance(value, str) and value.strip():
            return value.strip()

    raise ValueError("CRM response has no assistant reply")


async def process_turn(pcm, app, conversation_id):
    """
    Actual NVIDIA ASR -> existing CRM/Nemotron -> TTS.
    Returns raw 8 kHz G.711 mu-law audio.
    No appointment booking is performed.
    """
    with tempfile.TemporaryDirectory(
        prefix="leadpilot_twilio_"
    ) as directory:
        directory = Path(directory)
        input_wav = directory / "customer.wav"
        output_wav = directory / "assistant.wav"

        with wave.open(str(input_wav), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(pcm)

        transcript = await NvidiaASRService().transcribe(
            input_wav
        )

        logger.info(
            "Local duplex speech transcribed: %s characters",
            len(transcript)
        )

        # Invoke the existing FastAPI CRM chat route internally.
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://leadpilot.internal",
            timeout=180
        ) as client:
            response = await client.post(
                f"/api/conversations/{conversation_id}/chat",
                json={"message": transcript}
            )

            response.raise_for_status()
            reply = extract_reply(response.json())

        await NvidiaTTSService().synthesize(
            reply, output_wav
        )

        return wav_to_mulaw8k(output_wav)


@router.websocket("/twilio/local-duplex-test")
async def local_duplex(websocket: WebSocket):
    host = (
        websocket.client.host
        if websocket.client else ""
    )

    if host not in LOCAL_HOSTS:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    stream = StreamState()
    segmenter = SpeechSegmenter()
    conversation_id = None

    try:
        while True:
            packet = await websocket.receive_json()

            if not isinstance(packet, dict):
                raise ValueError("Expected JSON message")

            event = packet.get("event")

            if event == "connected":
                continue

            elif event == "start":
                if stream.stream_sid is not None:
                    raise ValueError("Duplicate start message")

                stream.start(packet)

                params = (
                    packet.get("start", {})
                    .get("customParameters", {})
                )

                conversation_id = str(
                    UUID(params["conversation_id"])
                )

            elif event == "media":
                if not conversation_id:
                    raise ValueError("Stream not started")

                pcm = stream.feed(packet)

                if not pcm:
                    continue

                completed = segmenter.feed(pcm)

                if completed is None:
                    continue

                audio = await process_turn(
                    completed,
                    websocket.scope["app"],
                    conversation_id
                )

                for outbound in outbound_packets(
                    audio, stream.stream_sid
                ):
                    await websocket.send_json(outbound)

                await websocket.send_json(
                    mark_packet(stream.stream_sid)
                )

            elif event == "mark":
                # Local simulator acknowledges playback.
                continue

            elif event == "stop":
                break

            elif event == "dtmf":
                continue

            else:
                raise ValueError("Unsupported event")

    except WebSocketDisconnect:
        return

    except (ValueError, KeyError, TypeError):
        logger.warning("Invalid local duplex message")
        await websocket.close(code=1003)
        return

    except Exception:
        logger.exception("Local duplex processing failed")
        await websocket.close(code=1011)
        return

    await websocket.close(code=1000)
