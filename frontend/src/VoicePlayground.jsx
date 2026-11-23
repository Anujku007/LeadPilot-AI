import { useEffect, useRef, useState } from 'react'
import { Headphones, LoaderCircle, Mic, MicOff, Play, ShieldCheck, Sparkles, Square, Volume2 } from 'lucide-react'
import { recorderBlobToWav, supportedRecordingMime } from './browserAudio.js'
import { transcribeAudio, synthesizeSpeech } from './api.js'

const MAX_MS = 19500
const STATUS = {
  idle: 'Ready for a local voice turn',
  recording: 'Listening… speak clearly',
  converting: 'Preparing a 16-kHz WAV recording…',
  transcribing: 'NVIDIA Parakeet is transcribing…',
  qualifying: 'Nemotron is responding and updating CRM…',
  speaking: 'NVIDIA Magpie is synthesizing the reply…',
  ready: 'Voice response is ready',
  error: 'Voice request could not complete'
}

export default function VoicePlayground({ activeId, busy, onVoiceTurn }) {
  const [stage, setStage] = useState('idle')
  const [transcript, setTranscript] = useState('')
  const [reply, setReply] = useState('')
  const [error, setError] = useState('')
  const [audioUrl, setAudioUrl] = useState(null)
  const recorder = useRef(null)
  const stream = useRef(null)
  const timer = useRef(null)
  const chunks = useRef([])
  const alive = useRef(true)
  const activeIdRef = useRef(activeId)
  const lastUrl = useRef(null)
  const audio = useRef(null)
  const inFlight = useRef(false)
  const busyState = !['idle', 'ready', 'error'].includes(stage)

  useEffect(() => { activeIdRef.current = activeId }, [activeId])
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      window.clearTimeout(timer.current)
      recorder.current?.state === 'recording' && recorder.current.stop()
      stream.current?.getTracks().forEach(track => track.stop())
      if (lastUrl.current) URL.revokeObjectURL(lastUrl.current)
    }
  }, [])

  function stopTracks() {
    window.clearTimeout(timer.current)
    stream.current?.getTracks().forEach(t => t.stop())
    stream.current = null
  }

  async function handleRecording(blob, idAtStart) {
    if (!alive.current || !blob.size || inFlight.current) return
    inFlight.current = true
    try {
      if (activeIdRef.current !== idAtStart) throw new Error('Conversation changed during recording. Try again.')
      setStage('converting')
      const wav = await recorderBlobToWav(blob)
      if (!alive.current) return
      setStage('transcribing')
      const result = await transcribeAudio(wav)
      const text = result.transcript?.trim()
      if (!text) throw new Error('No speech recognized. Check your microphone and try again.')
      setTranscript(text)
      if (activeIdRef.current !== idAtStart) throw new Error('Conversation changed. Transcript was not sent.')
      setStage('qualifying')
      // Persist exactly the same way as typed customer messages.
      const response = await onVoiceTurn(text, idAtStart)
      if (!response) throw new Error('No AI reply was returned.')
      setReply(response)
      if (!alive.current) return
      setStage('speaking')
      const wavResponse = await synthesizeSpeech(response.slice(0, 850))
      if (!alive.current) return
      const url = URL.createObjectURL(wavResponse)
      if (lastUrl.current) URL.revokeObjectURL(lastUrl.current)
      lastUrl.current = url
      setAudioUrl(url)
      setStage('ready')
      // Autoplay may be blocked because AI processing is asynchronous.
      // The standard audio controls remain available for manual playback.
      window.setTimeout(() => { if (alive.current) audio.current?.play()?.catch(() => {}) }, 10)
    } catch (err) {
      if (alive.current) { setStage('error'); setError(err.message || 'Voice processing failed') }
    } finally { inFlight.current = false }
  }

  async function start() {
    if (busy || busyState || inFlight.current) return
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('Microphone capture requires localhost or HTTPS and a supported browser (Chrome/Edge).')
      setStage('error')
      return
    }
    setError('');setTranscript('');setReply('')
    if (audio.current) audio.current.pause()
    if (lastUrl.current) {URL.revokeObjectURL(lastUrl.current);lastUrl.current = null;setAudioUrl(null)}
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false })
      if (!alive.current) {stopTracks();return}
      const mime = supportedRecordingMime()
      recorder.current = new MediaRecorder(stream.current, mime ? { mimeType: mime } : undefined)
      const idAtStart = activeId
      chunks.current = []
      recorder.current.ondataavailable = e => {if (e.data?.size) chunks.current.push(e.data)}
      recorder.current.onerror = () => { if (alive.current) {setError('Microphone recording failed');setStage('error')} stopTracks() }
      recorder.current.onstop = () => {
        stopTracks()
        const recorded = new Blob(chunks.current, { type: recorder.current?.mimeType || 'audio/webm' })
        if (alive.current) handleRecording(recorded, idAtStart)
      }
      recorder.current.start(250)
      setStage('recording')
      timer.current = window.setTimeout(() => stop(), MAX_MS)
    } catch (err) {
      stopTracks()
      setStage('error')
      setError(err?.name === 'NotAllowedError' ? 'Microphone permission was denied. Allow access in the browser address bar.' : (err?.message || 'Could not start microphone'))
    }
  }
  function stop() {
    if (recorder.current?.state === 'recording') {
      recorder.current.stop()
      setStage('converting')
    }
    stopTracks()
  }

  return <section className="voice-playground" aria-label="Local browser NVIDIA voice playground">
    <div className="voice-identity"><span className={`voice-pulse ${stage === 'recording' ? 'recording' : ''}`}><Headphones size={20}/></span><div><strong>Browser Voice Playground</strong><p>Parakeet ASR → Nemotron + CRM → Magpie TTS · Local demo</p></div></div>
    <div className="voice-controls">
      <span className={`voice-stage ${stage === 'recording' ? 'active' : ''}`}>{busyState && stage !== 'recording' ? <LoaderCircle size={14} className="spin"/> : stage === 'recording' ? <span className="red-dot"/> : <Sparkles size={14}/>} {STATUS[stage]}</span>
      {stage === 'recording'
        ? <button type="button" className="voice-stop" onClick={stop}><Square size={15}/> Stop &amp; send</button>
        : <button type="button" className="voice-record" onClick={start} disabled={busyState || busy}><Mic size={17}/> {stage === 'ready' ? 'Record again' : 'Start talking'}</button>}
    </div>
    {transcript && <div className="voice-result"><strong>You said</strong><p>{transcript}</p></div>}
    {reply && <div className="voice-result voice-answer"><strong>LeadPilot replied</strong><p>{reply}</p></div>}
    {audioUrl && <div className="voice-audio"><Volume2 size={17}/><audio ref={audio} src={audioUrl} controls preload="metadata" aria-label="Play NVIDIA Magpie reply" /></div>}
    {error && <div className="voice-error" role="alert"><MicOff size={15}/>{error}</div>}
    <div className="voice-privacy"><ShieldCheck size={13}/> Recording is limited to 20 seconds. Audio is sent to NVIDIA for processing and not saved by this demo API. Real Twilio/NVIDIA calls are not enabled.</div>
  </section>
}
