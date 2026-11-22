import asyncio
import logging

import numpy as np
from fastapi import (
    APIRouter, WebSocket, WebSocketDisconnect
)

from .twilio_stream import LOCAL_HOSTS, StreamState
from .twilio_audio_out import (
    wav_to_mulaw8k,
    outbound_packets,
    mark_packet,
    clear_packet
)
from .twilio_playback_local import AUDIO_FILE

router = APIRouter()
logger = logging.getLogger(__name__)

FRAME_INTERVAL = 0.020


def speech_detected(pcm, threshold=700):
    if not pcm:
        return False

    samples = np.frombuffer(
        pcm, dtype="<i2"
    ).astype(np.float32)

    rms = float(np.sqrt(
        np.mean(samples * samples)
    ))

    return rms >= threshold


class PacedPlayback:
    def __init__(self, websocket, stream_sid):
        self.websocket = websocket
        self.stream_sid = stream_sid
        self.lock = asyncio.Lock()
        self.cancelled = asyncio.Event()

        self.loud_frames = 0
        self.sent_frames = 0
        self.mark_sent = False
        self.mark_acknowledged = False
        self.clear_sent = False

    async def play(self, audio):
        loop = asyncio.get_running_loop()
        started = loop.time()

        for index, packet in enumerate(
            outbound_packets(audio, self.stream_sid)
        ):
            deadline = (
                started + index * FRAME_INTERVAL
            )

            await asyncio.sleep(
                max(0.0, deadline - loop.time())
            )

            async with self.lock:
                if self.cancelled.is_set():
                    return

                await self.websocket.send_json(packet)
                self.sent_frames += 1

        async with self.lock:
            if not self.cancelled.is_set():
                await self.websocket.send_json(
                    mark_packet(self.stream_sid)
                )
                self.mark_sent = True

    async def observe_inbound(self, pcm):
        if (
            self.cancelled.is_set()
            or self.mark_acknowledged
        ):
            return

        if speech_detected(pcm):
            self.loud_frames += 1
        else:
            self.loud_frames = 0

        # Three consecutive loud 20 ms inbound frames.
        if self.loud_frames < 3:
            return

        self.cancelled.set()

        async with self.lock:
            await self.websocket.send_json(
                clear_packet(self.stream_sid)
            )
            self.clear_sent = True

    def acknowledge_mark(self, packet):
        if (
            packet.get("streamSid") == self.stream_sid
            and (
                (packet.get("mark") or {}).get("name")
                == "leadpilot-local-playback"
            )
        ):
            self.mark_acknowledged = True


@router.websocket("/twilio/local-paced-test")
async def local_paced_test(websocket: WebSocket):
    host = (
        websocket.client.host
        if websocket.client else ""
    )

    if host not in LOCAL_HOSTS:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    stream = StreamState()
    playback = None
    sender = None

    close_code = 1000
    disconnected = False

    try:
        while True:
            packet = await websocket.receive_json()

            if not isinstance(packet, dict):
                raise ValueError("Expected JSON object")

            event = packet.get("event")

            if event == "connected":
                continue

            elif event == "start":
                if playback is not None:
                    raise ValueError("Duplicate stream start")

                stream.start(packet)

                audio = wav_to_mulaw8k(AUDIO_FILE)

                if not audio or len(audio) > 8000 * 30:
                    raise ValueError(
                        "Invalid playback audio duration"
                    )

                playback = PacedPlayback(
                    websocket, stream.stream_sid
                )

                sender = asyncio.create_task(
                    playback.play(audio)
                )

            elif event == "media":
                if playback is None:
                    raise ValueError(
                        "Media received before start"
                    )

                pcm = stream.feed(packet)

                if pcm:
                    await playback.observe_inbound(pcm)

            elif event == "mark":
                if playback is not None:
                    playback.acknowledge_mark(packet)

            elif event == "stop":
                break

            elif event == "dtmf":
                continue

            else:
                raise ValueError(
                    "Unsupported Twilio event"
                )

    except WebSocketDisconnect:
        disconnected = True

    except (ValueError, TypeError, KeyError, OSError):
        logger.warning("Invalid local paced test request")
        close_code = 1003

    except Exception:
        logger.exception(
            "Unexpected local paced playback error"
        )
        close_code = 1011

    finally:
        if playback is not None:
            playback.cancelled.set()

        if sender is not None:
            try:
                await sender
            except Exception:
                logger.exception(
                    "Playback sender failed"
                )
                close_code = 1011

        if not disconnected:
            await websocket.close(code=close_code)
