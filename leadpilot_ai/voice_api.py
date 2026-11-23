"""Local-only browser voice endpoints for LeadPilot AI.

The browser uploads short, decoded PCM WAV audio directly (not multipart).
No media or transcript is logged or permanently stored by this module.
Existing CRM turns are still handled by /api/conversations/{id}/chat.
Never expose the unauthenticated parent FastAPI app publicly.
"""
import io
import logging
import tempfile
import wave
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .nvidia_asr_service import NvidiaASRService
from .nvidia_tts_service import NvidiaTTSService

router = APIRouter(prefix="/api/voice", tags=["Local Browser Voice Demo"])
logger = logging.getLogger(__name__)
asr = NvidiaASRService()
tts = NvidiaTTSService()

SAMPLE_RATE = 16000
MAX_SECONDS = 20
# WAV may contain small non-audio chunks. Still cap the entire upload.
MAX_WAV_BYTES = SAMPLE_RATE * 2 * MAX_SECONDS + 8192
MAX_TTS_BYTES = 12 * 1024 * 1024


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=850)


def validate_wav(raw: bytes):
    if len(raw) < 44 or len(raw) > MAX_WAV_BYTES:
        raise ValueError("Audio must be a short WAV recording (up to 20 seconds).")
    try:
        with wave.open(io.BytesIO(raw), "rb") as audio:
            if (
                audio.getnchannels() != 1 or
                audio.getsampwidth() != 2 or
                audio.getframerate() != SAMPLE_RATE or
                audio.getcomptype() != "NONE"
            ):
                raise ValueError("Expected mono, 16-bit PCM, 16 kHz WAV audio")
            frames = audio.getnframes()
            if not 0 < frames <= SAMPLE_RATE * MAX_SECONDS:
                raise ValueError("Recording duration must be between 0 and 20 seconds")
            if len(audio.readframes(frames)) != frames * 2:
                raise ValueError("Recording appears truncated")
    except (wave.Error, EOFError) as error:
        raise ValueError("Invalid WAV data") from error
    return frames


@router.post("/transcribe")
async def transcribe_browser_audio(request: Request):
    if request.headers.get("content-type", "").split(";", 1)[0].lower().strip() != "audio/wav":
        raise HTTPException(status_code=415, detail="Send an audio/wav body")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_WAV_BYTES:
            raise HTTPException(status_code=413, detail="Recording exceeds the 20-second audio limit")
    try:
        validate_wav(bytes(data))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    try:
        with tempfile.TemporaryDirectory(prefix="leadpilot_browser_voice_") as tempdir:
            wav_file = Path(tempdir) / "input.wav"
            wav_file.write_bytes(data)
            transcript = await asr.transcribe(wav_file)
        return {"success": True, "transcript": transcript}
    except Exception as error:
        logger.warning("Browser ASR request failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="NVIDIA speech recognition unavailable") from error


@router.post("/synthesize")
async def synthesize_browser_response(body: SpeechRequest):
    speech = body.text.strip()
    if not speech:
        raise HTTPException(status_code=422, detail="Speech text cannot be blank")
    try:
        with tempfile.TemporaryDirectory(prefix="leadpilot_browser_voice_") as tempdir:
            path = Path(tempdir) / "reply.wav"
            result_path = await tts.synthesize(speech, path)
            output_path = Path(result_path)
            # Protect against unexpectedly large generated responses.
            if output_path.stat().st_size > MAX_TTS_BYTES:
                raise ValueError("Voice output exceeded the safety limit")
            response = output_path.read_bytes()
            if not (len(response) > 44 and response[:4] == b"RIFF" and response[8:12] == b"WAVE"):
                raise ValueError("NVIDIA did not return valid WAV output")
        return Response(
            content=response, media_type="audio/wav",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        )
    except Exception as error:
        logger.warning("Browser TTS request failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="NVIDIA speech synthesis unavailable") from error
