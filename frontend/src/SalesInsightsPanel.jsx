import { useEffect, useState } from 'react'
import { Bell, BellRing, CalendarClock, Check, AlertCircle, TrendingUp, RefreshCcw } from 'lucide-react'
import { loadSalesOverview } from './api.js'
import './sales-insights.css'

function money(value) {
  const n = Number(value)
  return Number.isFinite(n) ? new Intl.NumberFormat('en-IN', { style:'currency', currency:'INR', maximumFractionDigits:2 }).format(n) : '₹0'
}
function showTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Invalid time' : new Intl.DateTimeFormat('en-IN', {
    day:'numeric', month:'short', year:'numeric', hour:'numeric', minute:'2-digit', timeZone:'Asia/Kolkata', timeZoneName:'short'
  }).format(date)
}
function ReminderRow({ item, overdue, onSelect }) {
  return <button type="button" className="si-reminder-row" onClick={() => onSelect(item.request_id)}>
    <span className={`si-reminder-dot ${overdue ? 'late' : ''}`}/>
    <span className="si-reminder-main"><strong>{item.display_name}</strong><small>{showTime(item.follow_up_at)}{item.appointment_count > 1 ? ` · ${item.appointment_count} bookings, one opportunity` : ''}</small></span>
    <span className={`si-reminder-pill ${overdue ? 'late' : ''}`}>{overdue ? 'Due now' : 'Upcoming'}</span>
  </button>
}
export default function SalesInsightsPanel({ pipeline, onSelectAppointment }) {
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState('')
  const [enabled, setEnabled] = useState(() => localStorage.getItem('leadpilot_followup_desktop') === 'on')
  async function load() { try { setOverview(await loadSalesOverview()); setError('') } catch (e) { setError(`Could not refresh analytics: ${e.message}`) } }
  useEffect(() => { void load() }, [pipeline])
  useEffect(() => {
    const timer = setInterval(() => { void load() }, 60000)
    const visible = () => { if (document.visibilityState === 'visible') void load() }
    document.addEventListener('visibilitychange', visible)
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', visible) }
  }, [])
  async function toggleDesktop() {
    if (enabled) { localStorage.setItem('leadpilot_followup_desktop', 'off'); setEnabled(false); return }
    if (typeof Notification === 'undefined' || !window.isSecureContext) {
      setError('Browser notifications are unavailable. In-app alerts still work while the workspace is open.')
      return
    }
    const permission = Notification.permission === 'granted' ? 'granted' : await Notification.requestPermission()
    if (permission !== 'granted') { setError('Notification permission not granted. In-app alerts remain active.'); return }
    localStorage.setItem('leadpilot_followup_desktop', 'on')
    setEnabled(true)
  }
  const a = overview?.analytics || {}
  const reminders = overview?.reminders || {}
  return <section className="si-overview" aria-label="Sales analytics and follow-up reminders">
    <div className="si-section-head"><div><TrendingUp size={18}/><h3>Sales Analytics</h3></div><button type="button" onClick={() => void load()}><RefreshCcw size={14}/> Refresh analytics</button></div>
    {error && <div className="si-error" role="alert"><AlertCircle size={15}/>{error}</div>}
    <div className="si-analytics-grid">
      <div><small>Distinct opportunities</small><strong>{a.distinct_opportunities ?? '—'}</strong><span>One per CRM lead conversation</span></div>
      <div><small>Meeting completion rate</small><strong>{a.meeting_completion_percent == null ? '—' : `${a.meeting_completion_percent}%`}</strong><span>{a.completed_meetings ?? '—'} / {a.booked_appointments ?? '—'} booked meetings</span></div>
      <div><small>Won / decided</small><strong>{a.win_rate_decided_percent == null ? '—' : `${a.win_rate_decided_percent}%`}</strong><span>{a.won ?? '—'} won · {a.lost ?? '—'} lost</span></div>
      <div><small>Won deal value</small><strong>{money(a.won_deal_value_inr)}</strong><span>Agreed deal values, not payments</span></div>
    </div>
    <div className="si-funnel"><span>Booked leads <b>{a.distinct_opportunities ?? '—'}</b></span><span>Met <b>{a.opportunities_with_completed_meetings ?? '—'}</b></span><span>Won <b>{a.won ?? '—'}</b></span><span>Lost <b>{a.lost ?? '—'}</b></span><span>Awaiting decision <b>{a.pending_decision ?? '—'}</b></span></div>
    <div className="si-section-head reminders"><div><BellRing size={18}/><h3>Follow-up reminders</h3><span className="si-due-count">{reminders.due_count ?? 0} due</span></div><button type="button" onClick={() => void toggleDesktop()}><Bell size={14}/>{enabled ? 'Turn off desktop alerts' : 'Enable desktop alerts'}</button></div>
    <p className="si-caption">In-app reminders check automatically every 60 seconds while the workspace is open. Optional browser notifications need your permission. No emails, SMS, or customer calls are sent. Due follow-ups stay visible until you update their outcome or schedule a new follow-up.</p>
    <div className="si-reminder-columns">
      <div className="si-reminder-group"><h4>Due or overdue ({reminders.due_count ?? 0})</h4>{(reminders.due || []).length ? reminders.due.map(r=><ReminderRow item={r} overdue key={r.conversation_id} onSelect={onSelectAppointment}/>) : <p className="si-empty"><Check size={15}/> No overdue follow-ups</p>}</div>
      <div className="si-reminder-group"><h4>Upcoming within 7 days ({reminders.upcoming_count ?? 0})</h4>{(reminders.upcoming || []).length ? reminders.upcoming.map(r=><ReminderRow item={r} key={r.conversation_id} onSelect={onSelectAppointment}/>) : <p className="si-empty"><CalendarClock size={15}/> None due in the next 7 days</p>}</div>
    </div>
    {Number(a.historical_conflicts) > 0 && <p className="si-error"><AlertCircle size={15}/> {a.historical_conflicts} legacy duplicate outcome(s) require review. Each lead is counted only once.</p>}
  </section>
}
