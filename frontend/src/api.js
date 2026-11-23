export async function api(path, { method = 'GET', data, signal } = {}) {
  const response = await fetch(path, {
    method,
    signal,
    headers: data === undefined ? {} : { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data)
  })
  const raw = await response.text()
  let result
  try { result = raw ? JSON.parse(raw) : null } catch { result = { detail: raw } }
  if (!response.ok) {
    const detail = result?.detail
    const message = typeof detail === 'string'
      ? detail
      : Array.isArray(detail) ? detail.map(item => item.msg || 'Validation error').join('; ')
        : `Request failed (${response.status})`
    throw new Error(message)
  }
  return result
}

export const loadSummary = () => api('/api/dashboard/summary')
export const loadConversations = () => api('/api/dashboard/conversations?limit=150')
export const loadAppointments = () => api('/api/dashboard/appointments?limit=50')
export const loadConversation = (id) => api(`/api/conversations/${encodeURIComponent(id)}`)
export const startConversation = () => api('/api/conversations/start', { method: 'POST' })
export const sendChat = (id, message) => api(`/api/conversations/${encodeURIComponent(id)}/chat`, { method: 'POST', data: { message } })
export const loadAvailable = (date) => api(`/api/appointments/availability?date=${encodeURIComponent(date)}`)
export const createProposal = (id, start) => api(`/api/conversations/${encodeURIComponent(id)}/appointment-proposal`, { method: 'POST', data: { start } })
export const confirmProposal = (id, proposalId) => api(`/api/conversations/${encodeURIComponent(id)}/confirm-appointment`, { method: 'POST', data: { proposal_id: proposalId, confirmation_text: 'CONFIRM BOOKING' } })
export const loadGatewayHealth = () => api('/gateway/health')

// Human-entered post-meeting outcomes; these APIs never book or change calendar events.
export const loadSalesPipeline = () => api('/api/sales/pipeline')
export const completeSalesMeeting = (requestId, meeting_notes) => api(
  `/api/sales/appointments/${encodeURIComponent(requestId)}/complete`,
  { method: 'POST', data: { meeting_notes } }
)
export const saveSalesOutcome = (requestId, outcomeData) => api(
  `/api/sales/appointments/${encodeURIComponent(requestId)}/outcome`,
  { method: 'PATCH', data: outcomeData }
)
export const loadSalesHistory = (requestId) => api(
  `/api/sales/appointments/${encodeURIComponent(requestId)}/history`
)

// Browser voice demo: raw audio/wav uploads, not multipart.
export async function transcribeAudio(wavBlob) {
  const response = await fetch('/api/voice/transcribe', {
    method: 'POST', headers: { 'Content-Type': 'audio/wav' }, body: wavBlob
  })
  const result = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(result.detail || 'Speech recognition failed')
  return result
}
export async function synthesizeSpeech(text) {
  const response = await fetch('/api/voice/synthesize', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text })
  })
  if (!response.ok) {
    const result = await response.json().catch(() => ({}))
    throw new Error(result.detail || 'Speech synthesis failed')
  }
  return response.blob()
}
export const saveLeadLabel = (id, display_name) => api(
  `/api/dashboard/conversations/${encodeURIComponent(id)}/label`,
  { method: 'PATCH', data: { display_name } }
)

// Read-only CRM statistics and due/upcoming follow-ups; no external delivery.
export const loadSalesOverview = () => api('/api/sales/overview')

// Read-only view of a pending appointment proposal for the active chat.
export const loadPendingAppointment = (id) => api(`/api/conversations/${encodeURIComponent(id)}/pending-appointment`)
