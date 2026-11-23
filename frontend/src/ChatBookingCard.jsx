import { useEffect, useState } from 'react'
import { CalendarCheck2, Clock3, Info, LoaderCircle, ShieldCheck } from 'lucide-react'
import { confirmProposal, loadPendingAppointment } from './api.js'
import './chat-booking.css'

function inIST(value) {
  try { return new Date(value).toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata', weekday: 'short', day: 'numeric', month: 'short',
    year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true
  }) + ' IST' } catch { return String(value || '') }
}

export default function ChatBookingCard({ conversationId, messageCount, notify, onConfirmed }) {
  const [state, setState] = useState(null)
  const [checked, setChecked] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setChecked(false)
    setError('')
    setState(null)
    if (conversationId) {
      loadPendingAppointment(conversationId)
        .then(result => { if (!cancelled) setState(result) })
        .catch(e => { if (!cancelled) setError(`Could not load appointment status: ${e.message}`) })
    }
    return () => { cancelled = true }
  }, [conversationId, messageCount])

  const proposal = state?.proposal
  const booked = state?.booking_created && state?.appointment
  if (!conversationId || (!proposal && !booked && !error)) return null

  async function confirm() {
    if (!checked || !proposal || saving) return
    setSaving(true)
    setError('')
    try {
      const result = await confirmProposal(conversationId, proposal.proposal_id)
      if (!result?.booking_created) throw new Error('Calendar did not confirm the booking.')
      setState({ booking_created: true, proposal: null, appointment: {
        start: result.start, end: result.end, event_id: result.event_id
      } })
      setChecked(false)
      notify?.('Google Calendar booking confirmed. Your CRM appointment is saved.')
      onConfirmed?.()
    } catch (e) {
      setError(e.message)
      // Always refresh the canonical calendar/proposal state after an error.
      loadPendingAppointment(conversationId).then(setState).catch(() => {})
    } finally { setSaving(false) }
  }

  return <section className="chat-booking-card" aria-label="In-chat appointment confirmation">
    {proposal ? <>
      <div className="chat-booking-heading"><CalendarCheck2 size={20}/><div>
        <strong>Consultation slot available</strong>
        <small>Calendar checked · Not booked yet</small>
      </div></div>
      <div className="chat-booking-datetime"><Clock3 size={16}/> {inIST(proposal.start)} · 30 minutes</div>
      <label className="chat-booking-consent"><input type="checkbox" checked={checked} onChange={e=>setChecked(e.target.checked)} disabled={saving}/><span>I authorize creating a real event in my connected Google Calendar.</span></label>
      <button type="button" className="primary-button chat-booking-confirm" onClick={confirm} disabled={!checked || saving}>
        {saving ? <LoaderCircle className="spin" size={17}/> : <CalendarCheck2 size={17}/>} CONFIRM BOOKING
      </button>
      <small className="chat-booking-safety"><ShieldCheck size={14}/> Proposal expires at {inIST(proposal.expires_at)}. No invitation email is sent automatically.</small>
    </> : booked ? <div className="chat-booking-heading confirmed"><CalendarCheck2 size={21}/><div>
      <strong>Google Calendar appointment confirmed</strong>
      <small>{inIST(state.appointment.start)} · 30 minutes · Saved in CRM</small>
    </div></div> : null}
    {error && <div className="chat-booking-error" role="alert"><Info size={16}/>{error}</div>}
  </section>
}
