import base64
import wave
from pathlib import Path

import numpy as np


def wav_to_mulaw8k(path):
    """Convert PCM16 WAV into headerless 8 kHz G.711 mu-law."""
    with wave.open(str(Path(path)), "rb") as reader:
        rate = reader.getframerate()
        channels = reader.getnchannels()
        width = reader.getsampwidth()
        count = reader.getnframes()

        if (
            reader.getcomptype() != "NONE"
            or width != 2
            or channels not in (1, 2)
        ):
            raise ValueError(
                "Expected uncompressed 16-bit mono/stereo WAV"
            )

        if (
            not 8000 <= rate <= 48000
            or count == 0
            or count > rate * 30
        ):
            raise ValueError(
                "Unsupported audio rate or duration"
            )

        raw = reader.readframes(count)

    samples = np.frombuffer(
        raw, dtype="<i2"
    ).astype(np.float64)

    if channels == 2:
        samples = samples.reshape(-1, 2).mean(axis=1)

    if rate != 8000:
        # Apply a low-pass filter before downsampling.
        taps = np.arange(-64, 65, dtype=np.float64)
        cutoff = 3600.0 / rate

        filt = (
            2 * cutoff
            * np.sinc(2 * cutoff * taps)
            * np.hamming(taps.size)
        )
        filt /= filt.sum()

        padded = np.pad(
            samples, (64, 64), mode="edge"
        )
        filtered = np.convolve(
            padded, filt, mode="valid"
        )

        output_count = max(
            1, round(len(samples) * 8000 / rate)
        )

        positions = (
            np.arange(output_count) * (rate / 8000)
        )

        samples = np.interp(
            positions,
            np.arange(len(samples)),
            filtered
        )

    pcm = np.clip(
        np.rint(samples), -32768, 32767
    ).astype(np.int32)

    negative = pcm < 0
    magnitude = np.minimum(np.abs(pcm), 32635) + 132

    exponent = np.clip(
        np.floor(np.log2(magnitude)).astype(np.int32) - 7,
        0, 7
    )
    mantissa = (magnitude >> (exponent + 3)) & 15

    encoded = np.bitwise_xor(
        (negative.astype(np.int32) << 7)
        | (exponent << 4)
        | mantissa,
        0xFF
    )

    return encoded.astype(np.uint8).tobytes()


def outbound_packets(audio_bytes, stream_sid):
    if not isinstance(stream_sid, str) or not (
        1 <= len(stream_sid) <= 128
    ):
        raise ValueError("Invalid stream SID")

    if not isinstance(audio_bytes, bytes) or not audio_bytes:
        raise ValueError("No audio supplied")

    # 160 bytes is 20 milliseconds at 8 kHz mu-law.
    for offset in range(0, len(audio_bytes), 160):
        chunk = audio_bytes[offset:offset + 160]

        yield {
            "event": "media",
            "streamSid": stream_sid,
            "media": {
                "payload": base64.b64encode(
                    chunk
                ).decode("ascii")
            }
        }


def mark_packet(stream_sid):
    return {
        "event": "mark",
        "streamSid": stream_sid,
        "mark": {"name": "leadpilot-local-playback"}
    }


def clear_packet(stream_sid):
    return {
        "event": "clear",
        "streamSid": stream_sid
    }
