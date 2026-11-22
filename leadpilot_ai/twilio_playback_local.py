import logging
import wave
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .twilio_stream import LOCAL_HOSTS, StreamState
from .twilio_audio_out import (
    wav_to_mulaw8k, outbound_packets, mark_packet
)

router = APIRouter()
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
AUDIO_FILE = (
    ROOT / "leadpilot_audio" / "leadpilot_ai_response.wav"
)


@router.websocket("/twilio/local-playback-test")
async def local_playback(websocket: WebSocket):
    host = (
        websocket.client.host
        if websocket.client else ""
    )

    if host not in LOCAL_HOSTS:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    try:
        packet = await websocket.receive_json()

        if packet.get("event") == "connected":
            packet = await websocket.receive_json()

        if packet.get("event") != "start":
            raise ValueError("Expected Twilio start message")

        state = StreamState()
        state.start(packet)

        audio = wav_to_mulaw8k(AUDIO_FILE)

        for message in outbound_packets(
            audio, state.stream_sid
        ):
            await websocket.send_json(message)

        await websocket.send_json(
            mark_packet(state.stream_sid)
        )

        await websocket.close(code=1000)

    except WebSocketDisconnect:
        return

    except (ValueError, OSError, wave.Error) as error:
        logger.warning(
            "Local playback failed: %s",
            type(error).__name__
        )
        await websocket.close(code=1003)
