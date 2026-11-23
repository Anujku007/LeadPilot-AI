import { useEffect, useRef, useState } from 'react'
import { CalendarCheck2, CalendarClock, ChevronDown, Clock3, Info, LoaderCircle, RefreshCw, ShieldCheck } from 'lucide-react'
import { confirmProposal, createProposal, loadAvailable, loadPendingAppointment } from './api.js'
import { dayIST, formatSlot } from './utils.js'
import './chat-booking.css'
import './calendar-picker.css'

function inIST(value) {
  try { return new Date(value).toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata', weekday: 'short', day: 'numeric', month: 'short',
    year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true
  }) + ' IST' } catch { return String(value || '') }
}

export default function CalendarBookingPicker({ conversationId, messageCount, isHot, notify, onConfirmed }) {
  const [state, setState] = useState(null)
  const [statusLoading, setStatusLoading] = useState(true)
  const slotRequest = useRef(0)
  const [checked, setChecked] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [dateOpen, setDateOpen] = useState(false)
  const [date, setDate] = useState(() => dayIST())
  const [available, setAvailable] = useState(null)
  const [chosen, setChosen] = useState('')
  const [loadingSlots, setLoadingSlots] = useState(false)
  const [proposing, setProposing] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setChecked(false)
    setError('')
    setState(null)
    setStatusLoading(!!conversationId)
    if (conversationId) {
      loadPendingAppointment(conversationId)
        .then(result => { if (!cancelled) setState(result) })
        .catch(e => { if (!cancelled) setError(`Could not load appointment status: ${e.message}`) })
        .finally(() => { if (!cancelled) setStatusLoading(false) })
    }
    return () => { cancelled = true }
  }, [conversationId, messageCount, refreshKey])

  useEffect(() => {
    slotRequest.current += 1
    setLoadingSlots(false)
    setProposing(false)
    setDateOpen(false)
    setDate(dayIST())
    setAvailable(null)
    setChosen('')
  }, [conversationId])

  const proposal = state?.proposal
  const booked = state?.booking_created && state?.appointment
  if (!conversationId || (!isHot && !proposal && !booked && !error)) return null

  async function findTimes(e) {
    e?.preventDefault?.()
    if (!conversationId || loadingSlots || !date || date < dayIST()) return
    const token = ++slotRequest.current
    setLoadingSlots(true)
    setAvailable(null)
    setChosen('')
    setError('')
    try {
      const result = await loadAvailable(date)
      if (token === slotRequest.current) setAvailable(result)
    } catch (e) {
      if (token === slotRequest.current) setError(`Could not check Google Calendar: ${e.message}`)
    } finally {
      if (token === slotRequest.current) setLoadingSlots(false)
    }
  }

  async function requestSlot() {
    if (!chosen || !conversationId || proposing || booked) return
    setProposing(true)
    const token = ++slotRequest.current
    setError('')
    try {
      // This endpoint checks availability again before creating an expiring
      // proposal. It NEVER writes a Google Calendar event.
      const result = await createProposal(conversationId, chosen)
      if (!result?.proposal_id || result?.booking_created) throw new Error('No valid unbooked proposal returned.')
      if (token !== slotRequest.current) return
      setState({ success: true, booking_created: false, proposal: result })
      setChecked(false)
      setDateOpen(false)
      notify?.('Slot verified. Review the proposal below; it is not booked yet.')
      // Invalidate stale alternatives. The slot may have changed while fetching.
      setAvailable(null)
      setChosen('')
    } catch (e) {
      if (token === slotRequest.current) {
        setError(`Could not propose that slot: ${e.message}. Refresh available times and try again.`)
        setAvailable(null)
        setChosen('')
      }
    } finally {
      setProposing(false)
    }
  }

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
      setDateOpen(false)
      notify?.('Google Calendar booking confirmed. Your CRM appointment is saved.')
      onConfirmed?.()
    } catch (e) {
      setError(e.message)
      // Read canonical state after error; never assume the calendar insert failed.
      setRefreshKey(v => v + 1)
    } finally { setSaving(false) }
  }

  return <section className="chat-booking-card" aria-label="In-chat Google Calendar scheduling">
    {proposal ? <>
      <div className="chat-booking-heading"><CalendarCheck2 size={20}/><div>
        <strong>Consultation slot available</strong>
        <small>Google Calendar checked · Not booked yet</small>
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

    {isHot && !booked && !statusLoading && <div className="lp-calendar-picker">
      <button type="button" className="lp-calendar-toggler" onClick={() => setDateOpen(v => !v)} aria-expanded={dateOpen}>
        <CalendarClock size={18}/>
        <span>{proposal ? 'Choose another appointment time' : 'Choose a date & time instead of speaking it'}</span>
        <ChevronDown className={dateOpen ? 'lp-rotated' : ''} size={17}/>
      </button>
      {dateOpen && <div className="lp-calendar-body">
        <p>Pick a date, then select a <strong>real available slot</strong> from Google Calendar. This avoids misheard dates from voice transcription.</p>
        <form className="lp-calendar-date-form" onSubmit={findTimes}>
          <label htmlFor="lp-chat-appointment-date">Appointment date (IST)
            <input id="lp-chat-appointment-date" type="date" min={dayIST()} value={date} onChange={e => { slotRequest.current += 1; setDate(e.target.value); setAvailable(null); setChosen(''); setError(''); setLoadingSlots(false) }}/>
          </label>
          <button type="submit" className="secondary-button" disabled={loadingSlots || !date || date < dayIST()}>
            {loadingSlots ? <LoaderCircle size={16} className="spin"/> : <RefreshCw size={16}/>} Check live slots
          </button>
        </form>
        {available && <div className="lp-calendar-times">
          <div className="lp-calendar-times-title"><strong>Available times</strong><span>{available.available_count || 0} options · IST</span></div>
          {available.available_slots?.length ? <div className="lp-calendar-slot-grid">
            {available.available_slots.map(slot => <button key={slot.start} type="button" className={chosen === slot.start ? 'lp-calendar-slot selected' : 'lp-calendar-slot'}
              aria-pressed={chosen === slot.start} onClick={() => setChosen(slot.start)} disabled={proposing}>
              {formatSlot(slot.start)}
            </button>)}
          </div> : <p className="lp-calendar-none">{available.note || 'No available slots on that date. Choose another day.'}</p>}
          {chosen && <div className="lp-calendar-choice"><span>Selected: <strong>{inIST(chosen)}</strong></span><button type="button" className="primary-button" disabled={proposing} onClick={requestSlot}>
            {proposing ? <LoaderCircle size={17} className="spin"/> : <CalendarCheck2 size={17}/>} Propose selected slot
          </button></div>}
        </div>}
        <small className="lp-calendar-disclaimer"><ShieldCheck size={14}/> Proposing does not book anything. Booking requires checking the separate CONFIRM BOOKING checkbox above.</small>
      </div>}
    </div>}
    {error && <div className="chat-booking-error" role="alert"><Info size={16}/>{error}</div>}
  </section>
}
