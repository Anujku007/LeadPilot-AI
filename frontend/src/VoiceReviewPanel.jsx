import { useEffect, useRef, useState } from 'react'
import { Check, Headphones, LoaderCircle, Mic, MicOff, RotateCcw, Send, ShieldCheck, Square, Trash2, Volume2 } from 'lucide-react'
import { recorderBlobToWav, supportedRecordingMime } from './browserAudio.js'
import { transcribeAudio, synthesizeSpeech } from './api.js'
import './voice-review.css'

const MAX_MS = 19500
const STATUS = {
  idle: 'Ready to record',
  recording: 'Recording — speak clearly',
  finalizing: 'Finishing recording…',
  review: 'Recording ready — listen before sending',
  converting: 'Preparing 16-kHz WAV…',
  transcribing: 'NVIDIA Parakeet is transcribing…',
  transcript_ready: 'Review or correct your transcript',
  qualifying: 'Sending to LeadPilot and updating CRM…',
  speaking: 'NVIDIA Magpie is generating the voice reply…',
  ready: 'Voice exchange complete',
  error: 'Voice request could not complete'
}

export default function VoiceReviewPanel({ activeId, busy, resetKey, onVoiceTurn }) {
  const [stage, setStage] = useState('idle')
  const [recordingUrl, setRecordingUrl] = useState(null)
  const [transcript, setTranscript] = useState('')
  const [reply, setReply] = useState('')
  const [error, setError] = useState('')
  const [audioUrl, setAudioUrl] = useState(null)
  const recorder = useRef(null)
  const stream = useRef(null)
  const timer = useRef(null)
  const chunks = useRef([])
  const recordedBlob = useRef(null)
  const recordedConversation = useRef(null)
  const alive = useRef(false)
  const activeIdRef = useRef(activeId)
  const recordingObjectUrl = useRef(null)
  const replyObjectUrl = useRef(null)
  const audio = useRef(null)
  const inFlight = useRef(false)
  const contextVersion = useRef(0)
  const hasRecorderError = useRef(false)
  const busyState = ['recording', 'finalizing', 'converting', 'transcribing', 'qualifying', 'speaking'].includes(stage)

  useEffect(() => { activeIdRef.current = activeId }, [activeId])
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      contextVersion.current += 1
      clearTimeout(timer.current)
      if (recorder.current?.state === 'recording') recorder.current.stop()
      stream.current?.getTracks().forEach(track => track.stop())
      if (recordingObjectUrl.current) URL.revokeObjectURL(recordingObjectUrl.current)
      if (replyObjectUrl.current) URL.revokeObjectURL(replyObjectUrl.current)
    }
  }, [])

  // Switching to another saved chat, or explicitly choosing New conversation,
  // must never send a recording captured for the previous context.
  useEffect(() => {
    contextVersion.current += 1
    if (recorder.current?.state === 'recording') recorder.current.stop()
    clearTimeout(timer.current)
    stream.current?.getTracks().forEach(track => track.stop())
    stream.current = null
    recordedBlob.current = null
    recordedConversation.current = null
    if (recordingObjectUrl.current) URL.revokeObjectURL(recordingObjectUrl.current)
    if (replyObjectUrl.current) URL.revokeObjectURL(replyObjectUrl.current)
    recordingObjectUrl.current = null
    replyObjectUrl.current = null
    setRecordingUrl(null)
    setAudioUrl(null)
    setTranscript('')
    setReply('')
    setError('')
    setStage('idle')
    // resetKey changes when the user switches chats; activeId may become
    // non-null on the *first sent message*, which should NOT reset playback.
  }, [resetKey])

  function stopTracks() {
    clearTimeout(timer.current)
    stream.current?.getTracks().forEach(track => track.stop())
    stream.current = null
  }

  function clearRecording() {
    recordedBlob.current = null
    recordedConversation.current = null
    if (recordingObjectUrl.current) URL.revokeObjectURL(recordingObjectUrl.current)
    recordingObjectUrl.current = null
    setRecordingUrl(null)
    setTranscript('')
  }

  function discard() {
    if (inFlight.current || busyState) return
    clearRecording()
    setError('')
    setStage('idle')
  }

  async function start() {
    if (busy || busyState || inFlight.current) return
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('Microphone capture requires localhost or HTTPS and a supported browser (Chrome/Edge).')
      setStage('error')
      return
    }
    clearRecording()
    setError('')
    setReply('')
    if (audio.current) audio.current.pause()
    if (replyObjectUrl.current) URL.revokeObjectURL(replyObjectUrl.current)
    replyObjectUrl.current = null
    setAudioUrl(null)
    const version = contextVersion.current
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true }, video: false
      })
      if (!alive.current || version !== contextVersion.current) {
        mediaStream.getTracks().forEach(track => track.stop())
        return
      }
      stream.current = mediaStream
      const mime = supportedRecordingMime()
      recorder.current = new MediaRecorder(mediaStream, mime ? { mimeType: mime } : undefined)
      recordedConversation.current = activeIdRef.current
      hasRecorderError.current = false
      chunks.current = []
      recorder.current.ondataavailable = e => { if (e.data?.size) chunks.current.push(e.data) }
      recorder.current.onerror = () => {
        hasRecorderError.current = true
        if (alive.current) { setError('Microphone recording failed. Please try again.'); setStage('error') }
        stopTracks()
      }
      recorder.current.onstop = () => {
        stopTracks()
        if (!alive.current || version !== contextVersion.current || hasRecorderError.current) return
        const blob = new Blob(chunks.current, { type: recorder.current?.mimeType || 'audio/webm' })
        if (!blob.size) {
          setError('No audio captured. Check your microphone and record again.')
          setStage('error')
          return
        }
        recordedBlob.current = blob
        const url = URL.createObjectURL(blob)
        recordingObjectUrl.current = url
        setRecordingUrl(url)
        setStage('review') // STOP does not transmit any audio or message.
      }
      recorder.current.start(250)
      setStage('recording')
      timer.current = setTimeout(stop, MAX_MS)
    } catch (err) {
      stopTracks()
      if (alive.current && version === contextVersion.current) {
        setError(err?.name === 'NotAllowedError' ? 'Microphone access denied. Enable it in the browser.' : err?.message || 'Could not record audio.')
        setStage('error')
      }
    }
  }

  function stop() {
    if (recorder.current?.state === 'recording') {
      setStage('finalizing')
      recorder.current.stop()
    }
    stopTracks()
  }

  function assertSameContext(version) {
    if (!alive.current || version !== contextVersion.current || activeIdRef.current !== recordedConversation.current) {
      throw new Error('You changed conversations. Please record again for the current chat.')
    }
  }

  async function processRecording(sendImmediately = false) {
    if (busy || inFlight.current || !recordedBlob.current) return
    const version = contextVersion.current
    inFlight.current = true
    setError('')
    try {
      assertSameContext(version)
      setStage('converting')
      const wav = await recorderBlobToWav(recordedBlob.current)
      assertSameContext(version)
      setStage('transcribing')
      const asr = await transcribeAudio(wav)
      assertSameContext(version)
      const text = String(asr?.transcript || '').trim()
      if (!text) throw new Error('No speech recognized. Try recording again.')
      setTranscript(text)
      if (sendImmediately) {
        await dispatchMessage(text, version)
      } else {
        setStage('transcript_ready')
      }
    } catch (err) {
      if (alive.current && version === contextVersion.current) {
        setStage('error')
        setError(err?.message || 'Voice processing failed.')
      }
    } finally {
      inFlight.current = false
    }
  }

  async function dispatchMessage(message, version = contextVersion.current) {
    const text = String(message || '').trim()
    if (!text || text.length > 2000) {
      setError('Please enter between 1 and 2,000 characters.')
      return
    }
    assertSameContext(version)
    setError('')
    setStage('qualifying')
    const response = await onVoiceTurn(text, recordedConversation.current)
    if (!response) throw new Error('LeadPilot returned no AI reply.')
    if (!alive.current || version !== contextVersion.current) return
    setReply(response)
    setStage('speaking')
    try {
      const wavResponse = await synthesizeSpeech(response.slice(0, 850))
      if (!alive.current || version !== contextVersion.current) return
      const url = URL.createObjectURL(wavResponse)
      if (replyObjectUrl.current) URL.revokeObjectURL(replyObjectUrl.current)
      replyObjectUrl.current = url
      setAudioUrl(url)
      setStage('ready')
      setTimeout(() => { if (alive.current && version === contextVersion.current) audio.current?.play()?.catch(() => {}) }, 10)
    } catch (err) {
      // The CRM write already succeeded. Don't suggest the message was lost.
      setError('Message saved and AI replied, but Magpie voice playback is unavailable: ' + (err.message || 'Unknown error'))
      setStage('ready')
    }
  }

  async function sendReviewedTranscript() {
    if (busy || inFlight.current || stage !== 'transcript_ready') return
    const version = contextVersion.current
    inFlight.current = true
    try {
      await dispatchMessage(transcript, version)
    } catch (err) {
      if (alive.current && version === contextVersion.current) {
        setError(err?.message || 'Message could not be sent. Please retry.')
        setStage('transcript_ready') // preserve the editable transcript for retry
      }
    } finally {
      inFlight.current = false
    }
  }

  return <section className="voice-playground" aria-label="Local browser NVIDIA voice playground">
    <div className="voice-identity"><span className={`voice-pulse ${stage === 'recording' ? 'recording' : ''}`}><Headphones size={20}/></span><div><strong>Browser Voice Playground</strong><p>Record → Review → Parakeet → Nemotron + CRM → Magpie</p></div></div>
    <div className="voice-controls">
      <span className={`voice-stage ${stage === 'recording' ? 'active' : ''}`}>
        {busyState && stage !== 'recording' ? <LoaderCircle size={14} className="spin"/> : stage === 'recording' ? <span className="red-dot"/> : <Check size={14}/>}
        {STATUS[stage]}
      </span>
      {stage === 'recording'
        ? <button type="button" className="voice-stop" onClick={stop}><Square size={15}/> Stop recording</button>
        : <button type="button" className="voice-record" onClick={start} disabled={busyState || busy || inFlight.current}>
          <Mic size={17}/> {stage === 'idle' ? 'Start recording' : 'Record again'}
        </button>}
    </div>
    {recordingUrl && <div className="voice-recording-review">
      <strong><Headphones size={16}/> Your recorded audio</strong>
      <audio src={recordingUrl} controls preload="metadata" aria-label="Listen to your voice recording"/>
      {(stage === 'review' || (stage === 'error' && recordedBlob.current)) && <div className="voice-review-actions">
        <button type="button" className="voice-review-primary" onClick={() => processRecording(false)} disabled={busy}>
          <Check size={16}/> Transcribe &amp; review
        </button>
        <button type="button" className="voice-review-secondary" onClick={() => processRecording(true)} disabled={busy}>
          <Send size={15}/> Send recording now
        </button>
        <button type="button" className="voice-review-quiet" onClick={discard}><Trash2 size={15}/> Discard</button>
      </div>}
    </div>}
    {['transcript_ready','qualifying','speaking','ready'].includes(stage) && transcript && <div className="voice-review-transcript">
      <label htmlFor="leadpilot-voice-transcript"><strong>Recognized speech</strong><span>{stage === 'transcript_ready' ? 'Correct names, dates, or times before sending.' : 'Sent customer message'}</span></label>
      <textarea id="leadpilot-voice-transcript" value={transcript} maxLength={2000} rows={3}
        readOnly={stage !== 'transcript_ready'} onChange={e => setTranscript(e.target.value)} aria-label="Edit recognized speech"/>
      {stage === 'transcript_ready' && <div className="voice-review-actions">
        <button type="button" className="voice-review-primary" disabled={busy || !transcript.trim() || inFlight.current} onClick={sendReviewedTranscript}><Send size={16}/> Send to LeadPilot</button>
        <button type="button" className="voice-review-quiet" onClick={discard}><RotateCcw size={15}/> Discard</button>
      </div>}
    </div>}
    {reply && <div className="voice-result voice-answer"><strong>LeadPilot replied</strong><p>{reply}</p></div>}
    {audioUrl && <div className="voice-audio"><Volume2 size={17}/><audio ref={audio} src={audioUrl} controls preload="metadata" aria-label="Play NVIDIA Magpie reply" /></div>}
    {error && <div className="voice-error" role="alert"><MicOff size={15}/>{error}</div>}
    <div className="voice-privacy"><ShieldCheck size={13}/> Stop only saves a local preview; no audio or CRM message is sent until you choose a send action. Preview locally, correct Parakeet's transcript if needed, then submit. Recording limit: 20 seconds. Audio is processed by NVIDIA services and not stored in the CRM.</div>
  </section>
}
