// Browser MediaRecorder audio is decoded and resampled locally to NVIDIA's
// required mono, 16-kHz, 16-bit PCM WAV. No third-party conversion service.
export async function recorderBlobToWav(blob) {
  const AudioContextType = window.AudioContext || window.webkitAudioContext
  if (!AudioContextType || !window.OfflineAudioContext) {
    throw new Error('This browser does not support audio conversion. Try desktop Chrome or Edge.')
  }
  const context = new AudioContextType()
  let decoded
  try {
    decoded = await context.decodeAudioData(await blob.arrayBuffer())
  } finally { await context.close() }

  if (!decoded.length || decoded.duration > 20.5) {
    throw new Error('Voice recording must be between 0 and 20 seconds.')
  }
  const duration = Math.min(20, decoded.duration)
  const length = Math.max(1, Math.round(duration * 16000))
  const target = new OfflineAudioContext(1, length, 16000)
  const source = target.createBufferSource()
  const mono = target.createBuffer(1, decoded.length, decoded.sampleRate)
  const channels = decoded.numberOfChannels
  const dest = mono.getChannelData(0)
  for (let ch = 0; ch < channels; ch++) {
    const samples = decoded.getChannelData(ch)
    for (let i = 0; i < dest.length; i++) dest[i] += samples[i] / channels
  }
  source.buffer = mono
  source.connect(target.destination)
  source.start(0)
  const rendered = await target.startRendering()
  const data = rendered.getChannelData(0)

  const buffer = new ArrayBuffer(44 + data.length * 2)
  const view = new DataView(buffer)
  const writeString = (offset, text) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i))
  }
  writeString(0, 'RIFF')
  view.setUint32(4, 36 + data.length * 2, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, 16000, true)
  view.setUint32(28, 32000, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, data.length * 2, true)
  for (let i = 0; i < data.length; i++) {
    const sample = Math.max(-1, Math.min(1, data[i]))
    view.setInt16(44 + i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

export function supportedRecordingMime() {
  if (!window.MediaRecorder) return null
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg']
  return types.find(type => MediaRecorder.isTypeSupported(type)) || ''
}
