import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .twilio_stream import LOCAL_HOSTS, StreamState
from .twilio_duplex_local import (
    SpeechSegmenter, process_turn
)
from .twilio_paced_local import (
    PacedPlayback, speech_detected
)
from .twilio_audio_out import clear_packet

logger = logging.getLogger(__name__)
router = APIRouter()


class LocalCallSession:

    def __init__(self, websocket):
        self.websocket = websocket
        self.stream = StreamState()
        self.segmenter = SpeechSegmenter()

        self.conversation_id = None

        self.queue = asyncio.Queue(maxsize=1)
        self.worker = None
        self.sender = None
        self.playback = None

        self.processing = False
        self.version = 0
        self.loud_frames = 0
        self.barge_triggered = False
        self.closed = False

    def start(self, packet):
        if self.conversation_id is not None:
            raise ValueError("Duplicate start message")

        self.stream.start(packet)

        params = (
            packet.get("start", {})
            .get("customParameters", {})
        )

        self.conversation_id = str(
            UUID(params["conversation_id"])
        )

        self.worker = asyncio.create_task(
            self.process_utterances()
        )

    async def receive_audio(self, packet):
        if self.conversation_id is None:
            raise ValueError("Media received before start")

        if packet.get("streamSid") != self.stream.stream_sid:
            raise ValueError("Incorrect stream SID")

        pcm = self.stream.feed(packet)

        if not pcm:
            return

        active = (
            self.processing
            or (
                self.playback is not None
                and not self.playback.mark_acknowledged
                and not self.playback.cancelled.is_set()
            )
        )

        if active:
            if speech_detected(pcm):
                self.loud_frames += 1
            else:
                self.loud_frames = 0

            if self.playback is not None:
                await self.playback.observe_inbound(pcm)

            if (
                self.loud_frames >= 3
                and not self.barge_triggered
            ):
                # Any unfinished AI response is now stale.
                self.version += 1
                self.barge_triggered = True

        completed = self.segmenter.feed(pcm)

        if completed is None:
            return

        self.version += 1

        # Keep only the latest unprocessed utterance.
        if self.queue.full():
            self.queue.get_nowait()
            self.queue.task_done()

        self.queue.put_nowait(
            (completed, self.version)
        )

        self.loud_frames = 0
        self.barge_triggered = False

    async def begin_playback(self, audio):
        if (
            not isinstance(audio, bytes)
            or not audio
            or len(audio) > 8000 * 30
        ):
            raise ValueError("Invalid AI playback audio")

        # Clear any previous unfinished playback.
        if (
            self.playback is not None
            and not self.playback.mark_acknowledged
            and not self.playback.cancelled.is_set()
        ):
            self.playback.cancelled.set()

            async with self.playback.lock:
                await self.websocket.send_json(
                    clear_packet(self.stream.stream_sid)
                )

        if self.sender is not None:
            await self.sender

        self.playback = PacedPlayback(
            self.websocket,
            self.stream.stream_sid
        )

        self.sender = asyncio.create_task(
            self.playback.play(audio)
        )

    async def process_utterances(self):
        try:
            while True:
                pcm, version = await self.queue.get()

                try:
                    self.processing = True

                    audio = await process_turn(
                        pcm,
                        self.websocket.scope["app"],
                        self.conversation_id
                    )

                    # Do not speak an outdated answer.
                    if (
                        not self.closed
                        and version == self.version
                    ):
                        await self.begin_playback(audio)

                finally:
                    self.processing = False
                    self.queue.task_done()

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Local live call processing failed"
            )

            self.closed = True

            try:
                await self.websocket.close(code=1011)
            except RuntimeError:
                pass

    def acknowledge_mark(self, packet):
        if self.playback is not None:
            self.playback.acknowledge_mark(packet)

    async def shutdown(self):
        self.closed = True

        if self.playback is not None:
            self.playback.cancelled.set()

        tasks = [
            task for task in (self.worker, self.sender)
            if task is not None
        ]

        for task in tasks:
            if not task.done():
                task.cancel()

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True
            )


@router.websocket("/twilio/local-live-test")
async def local_live_test(websocket: WebSocket):
    host = (
        websocket.client.host
        if websocket.client else ""
    )

    if host not in LOCAL_HOSTS:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    session = LocalCallSession(websocket)

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
                session.start(packet)

            elif event == "media":
                await session.receive_audio(packet)

            elif event == "mark":
                session.acknowledge_mark(packet)

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

    except (ValueError, KeyError, TypeError):
        logger.warning(
            "Invalid local live call message"
        )
        close_code = 1003

    except Exception:
        logger.exception("Local live call failed")
        close_code = 1011

    finally:
        # Capture whether the worker already closed the socket.
        # shutdown() always marks the session as closed.
        already_closed = session.closed

        await session.shutdown()

        if not disconnected and not already_closed:
            await websocket.close(code=close_code)
