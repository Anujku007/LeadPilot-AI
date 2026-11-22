import base64
import binascii
import logging

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# Local test only. Public connections must be authenticated
# before exposing this endpoint to Twilio.
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def decode_mulaw_to_pcm16k(payload):
    if not isinstance(payload, str):
        raise ValueError("Missing base64 audio payload")

    if len(payload) > 12000:
        raise ValueError("Audio message exceeds test limit")

    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("Invalid base64 audio") from error

    if not raw or len(raw) > 8192:
        raise ValueError("Invalid audio frame size")

    # ITU-T G.711 mu-law -> signed 16-bit PCM
    values = np.bitwise_xor(
        np.frombuffer(raw, dtype=np.uint8), 0xFF
    ).astype(np.int32)

    magnitude = (
        ((values & 15) << 3) + 0x84
    ) << ((values >> 4) & 7)

    pcm8k = np.where(
        (values & 0x80) != 0,
        0x84 - magnitude,
        magnitude - 0x84
    ).astype(np.int16)

    # Simple 8 kHz -> 16 kHz interpolation for local testing.
    # Upgrade to a proper streaming resampler later.
    positions = np.arange(pcm8k.size, dtype=np.float32)
    target = np.arange(pcm8k.size * 2, dtype=np.float32) / 2

    pcm16k = np.interp(
        target, positions, pcm8k.astype(np.float32)
    )

    return np.clip(
        np.rint(pcm16k), -32768, 32767
    ).astype("<i2").tobytes()


class StreamState:

    def __init__(self):
        self.stream_sid = None
        self.media_count = 0
        self.input_bytes = 0
        self.pcm_bytes = 0

    def start(self, packet):
        details = packet.get("start") or {}
        fmt = details.get("mediaFormat") or {}

        if (
            fmt.get("encoding") != "audio/x-mulaw"
            or str(fmt.get("sampleRate")) != "8000"
            or str(fmt.get("channels")) != "1"
        ):
            raise ValueError("Unsupported Twilio audio format")

        sid = details.get("streamSid") or packet.get("streamSid")

        if not isinstance(sid, str) or not sid:
            raise ValueError("Missing stream SID")

        self.stream_sid = sid

    def feed(self, packet):
        if not self.stream_sid:
            raise ValueError("Media received before start")

        media = packet.get("media") or {}

        if media.get("track", "inbound") != "inbound":
            return b""

        payload = media.get("payload")
        pcm = decode_mulaw_to_pcm16k(payload)

        self.media_count += 1
        self.pcm_bytes += len(pcm)
        self.input_bytes += len(
            base64.b64decode(payload, validate=True)
        )

        # Return converted audio for future NVIDIA integration.
        # Do not store customer audio in this local test.
        return pcm


@router.websocket("/twilio/media-stream")
async def twilio_media_stream(websocket: WebSocket):
    host = websocket.client.host if websocket.client else ""

    if host not in LOCAL_HOSTS:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    state = StreamState()

    try:
        while True:
            packet = await websocket.receive_json()

            if not isinstance(packet, dict):
                raise ValueError("Expected JSON object")

            event = packet.get("event")

            if event == "connected":
                continue

            if event == "start":
                state.start(packet)
                logger.info("Local Twilio test stream started")

            elif event == "media":
                state.feed(packet)

            elif event == "stop":
                break

            elif event in ("mark", "dtmf"):
                continue

            else:
                raise ValueError("Unsupported Twilio event")

    except WebSocketDisconnect:
        logger.info("Local Twilio test disconnected")
        return

    except (ValueError, TypeError):
        logger.warning("Invalid local Twilio stream message")
        await websocket.close(code=1003)
        return

    logger.info(
        "Stream ended: frames=%s pcm_bytes=%s",
        state.media_count,
        state.pcm_bytes
    )

    await websocket.close(code=1000)
