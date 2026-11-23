"""Offline browser-voice validation and provider-mock tests; no NVIDIA calls."""
import io
import wave
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from leadpilot_ai import voice_api


def wav_bytes(frames=1600, rate=16000, channels=1):
    b = io.BytesIO()
    with wave.open(b, 'wb') as f:
        f.setnchannels(channels)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(b'\x00\x00' * frames * channels)
    return b.getvalue()


class BrowserVoiceTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(voice_api.router)
        self.client = TestClient(app)

    def test_transcribe_uses_temp_wav_and_deletes_it(self):
        touched = []
        async def recognize(path):
            touched.append(Path(path))
            self.assertTrue(path.is_file())
            return 'We need a better CRM.'
        with patch.object(voice_api.asr, 'transcribe', new=recognize):
            response = self.client.post('/api/voice/transcribe', content=wav_bytes(), headers={'content-type':'audio/wav'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['transcript'], 'We need a better CRM.')
        self.assertFalse(touched[0].exists())

    def test_reject_invalid_type_and_audio(self):
        self.assertEqual(self.client.post('/api/voice/transcribe', content=b'hello').status_code,415)
        self.assertEqual(self.client.post('/api/voice/transcribe', content=b'fake', headers={'content-type':'audio/wav'}).status_code,422)
        self.assertEqual(self.client.post('/api/voice/transcribe', content=wav_bytes(rate=8000),headers={'content-type':'audio/wav'}).status_code,422)
        self.assertEqual(self.client.post('/api/voice/transcribe', content=wav_bytes(channels=2),headers={'content-type':'audio/wav'}).status_code,422)

    def test_enforce_max_recording(self):
        oversized=b'R'* (voice_api.MAX_WAV_BYTES+1)
        self.assertEqual(self.client.post('/api/voice/transcribe', content=oversized, headers={'content-type':'audio/wav'}).status_code,413)
        self.assertEqual(self.client.post('/api/voice/transcribe', content=wav_bytes(frames=21*16000), headers={'content-type':'audio/wav'}).status_code,413)

    def test_tts_response_and_cleanup(self):
        paths=[]
        async def speak(text,path):
            self.assertEqual(text,'Hello!')
            paths.append(path)
            path.write_bytes(wav_bytes(2000))
            return str(path)
        with patch.object(voice_api.tts, 'synthesize',new=speak):
            response=self.client.post('/api/voice/synthesize',json={'text':' Hello! '})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers.get('cache-control'),'no-store')
        self.assertEqual(response.content[:4],b'RIFF')
        self.assertFalse(paths[0].exists())

    def test_tts_reject_blank_or_long(self):
        self.assertEqual(self.client.post('/api/voice/synthesize',json={'text':'   '}).status_code,422)
        self.assertEqual(self.client.post('/api/voice/synthesize',json={'text':'a'*851}).status_code,422)

    def test_failures_dont_leak_exception_details(self):
        with patch.object(voice_api.asr,'transcribe',new=AsyncMock(side_effect=RuntimeError('secret api error'))):
            response=self.client.post('/api/voice/transcribe',content=wav_bytes(),headers={'content-type':'audio/wav'})
        self.assertEqual(response.status_code,502)
        self.assertNotIn('secret',response.text)


if __name__=='__main__':
    unittest.main()
