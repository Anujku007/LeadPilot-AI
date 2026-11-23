import { useEffect, useMemo, useState } from 'react'
import {
  ArrowRight, CalendarCheck2, CalendarClock, CheckCircle2, ClipboardList,
  Clock3, IndianRupee, LoaderCircle, RefreshCcw, Save, Search,
  TrendingUp, Trophy, UserRound, XCircle, AlertCircle
} from 'lucide-react'
import { loadSalesPipeline, completeSalesMeeting, saveSalesOutcome, loadSalesHistory } from './api.js'
import './sales-pipeline.css'
import SalesInsightsPanel from './SalesInsightsPanel.jsx'

const CATEGORIES = [
  { key: 'all', label: 'All meetings' },
  { key: 'booked', label: 'Booked' },
  { key: 'completed', label: 'Meeting completed' },
  { key: 'followup', label: 'Follow-up required' },
  { key: 'won', label: 'Won' },
  { key: 'lost', label: 'Lost' },
]

function showDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Invalid date'
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit',
    timeZone: 'Asia/Kolkata', timeZoneName: 'short'
  }).format(date)
}

function localInputTime(iso) {
  if (!iso) return ''
  const dt = new Date(iso)
  if (Number.isNaN(dt.getTime())) return ''
  return new Date(dt.getTime() - dt.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

function formatMoney(value) {
  const number = Number(value || 0)
  if (!Number.isFinite(number)) return '₹0'
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(number)
}

function nameFor(item) { return item.display_name || `Lead ${item.conversation_id.slice(0, 8)}` }
function currentStatus(item) { return item.outcome || item.meeting_status }
function typeFor(status) {
  return status === 'Won' ? 'won' : status === 'Lost' ? 'lost' :
    status === 'Follow-up Required' ? 'followup' : status === 'Meeting Completed' ? 'completed' : 'booked'
}
function pill(status) { return <span className={`sales-pill ${typeFor(status)}`}>{status}</span> }

function Metric({ icon: Icon, title, value, sub }) {
  return <div className="sales-metric"><span className="sales-metric-icon"><Icon size={20}/></span>
    <div><span className="sales-muted">{title}</span><strong>{value}</strong><small>{sub}</small></div>
  </div>
}

export default function SalesPipelinePage({ onOpenConversation, notify }) {
  const [pipeline, setPipeline] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  const [notes, setNotes] = useState('')
  const [outcome, setOutcome] = useState('Follow-up Required')
  const [followup, setFollowup] = useState('')
  const [dealValue, setDealValue] = useState('')
  const [lostReason, setLostReason] = useState('')
  const [history, setHistory] = useState([])
  const [error, setError] = useState('')

  async function refresh({ initial = false } = {}) {
    if (initial) setLoading(true)
    try {
      const result = await loadSalesPipeline()
      setPipeline(result)
      setSelectedId(id => id && result.appointments.some(a => a.request_id === id)
        ? id : (result.appointments[0]?.request_id || null))
      setError('')
    } catch (e) { setError(`Could not load the sales pipeline: ${e.message}`) }
    finally { setLoading(false) }
  }

  useEffect(() => { void refresh({ initial: true }) }, [])
  const rows = pipeline?.appointments || []
  const selected = rows.find(r => r.request_id === selectedId) || null
  const summary = pipeline?.summary || {}

  useEffect(() => {
    setNotes(selected?.meeting_notes || '')
    setOutcome(selected?.outcome || 'Follow-up Required')
    // A new decision must be deliberate; no stale form data from another customer.
    setFollowup(selected?.outcome === 'Follow-up Required' ? localInputTime(selected.follow_up_at) : '')
    setDealValue(selected?.outcome === 'Won' ? selected.deal_value || '' : '')
    setLostReason(selected?.outcome === 'Lost' ? selected.lost_reason || '' : '')
    setHistory([])
    if (selected?.request_id) {
      let mounted = true
      loadSalesHistory(selected.request_id).then(result => {
        if (mounted) setHistory(result.activities || [])
      }).catch(() => {})
      return () => { mounted = false }
    }
  }, [selectedId, selected?.meeting_notes, selected?.outcome, selected?.deal_value, selected?.lost_reason])

  const filtered = useMemo(() => rows.filter(row => {
    const status = typeFor(currentStatus(row))
    const matches = filter === 'all' || status === filter || (filter === 'completed' && row.meeting_status === 'Meeting Completed')
    return matches && `${nameFor(row)} ${row.conversation_id} ${row.lead_category || ''}`.toLowerCase().includes(search.toLowerCase())
  }), [rows, filter, search])

  const canComplete = selected && new Date(selected.end).getTime() <= Date.now()
  async function markCompleted(e) {
    e.preventDefault()
    if (!selected || saving) return
    setSaving(true); setError('')
    try {
      await completeSalesMeeting(selected.request_id, notes)
      await refresh()
      notify?.('Meeting completion and notes saved in CRM.')
    } catch (e) { setError(e.message) }
    finally { setSaving(false) }
  }

  async function saveOutcome(e) {
    e.preventDefault()
    if (!selected || saving) return
    setError('')
    const payload = { outcome }
    if (outcome === 'Follow-up Required') {
      if (!followup || !Number.isFinite(new Date(followup).getTime())) {
        setError('Choose a valid follow-up date and time.'); return
      }
      payload.follow_up_at = new Date(followup).toISOString()
    } else if (outcome === 'Won') {
      if (!(Number(dealValue) > 0)) { setError('Enter a positive deal value in INR.'); return }
      payload.deal_value = dealValue
    } else if (outcome === 'Lost') {
      if (!lostReason.trim()) { setError('Add a reason for the lost deal.'); return }
      payload.lost_reason = lostReason.trim()
    }
    setSaving(true)
    try {
      await saveSalesOutcome(selected.request_id, payload)
      await refresh()
      notify?.(`${outcome} saved for ${nameFor(selected)}.`)
    } catch (e) { setError(e.message) }
    finally { setSaving(false) }
  }

  return <div className="page-content sales-page">
    <div className="sales-intro">
      <div><h2 className="section-title">After the appointment</h2><p className="section-subtitle">Finish meetings, schedule follow-ups, and record won or lost deals. Every change is saved to the local CRM. {summary.opportunities != null && <strong>{summary.opportunities} distinct lead opportunities</strong>}</p></div>
      <button className="secondary-button" onClick={() => refresh({ initial: true })} disabled={loading || saving}>
        <RefreshCcw size={16} className={loading ? 'spin' : ''}/> Refresh pipeline
      </button>
    </div>
    <div className="sales-metrics">
      <Metric icon={CalendarCheck2} title="Appointments booked" value={summary.booked ?? '—'} sub="Confirmed calendar bookings"/>
      <Metric icon={CheckCircle2} title="Meetings completed" value={summary.completed ?? '—'} sub={`${summary.pending_outcome ?? 0} awaiting an outcome`}/>
      <Metric icon={CalendarClock} title="Follow-up required" value={summary.follow_up_required ?? '—'} sub={`${summary.followups_due ?? 0} due or overdue`}/>
      <Metric icon={Trophy} title="Deals won" value={summary.won ?? '—'} sub={`${summary.lost ?? 0} lost`}/>
      <Metric icon={IndianRupee} title="Won deal value" value={formatMoney(summary.won_revenue_inr)} sub="Recorded INR deal value (not payments)"/>
    </div>
    {Number(summary.opportunity_conflicts)>0 && <div className="sales-alert" role="alert"><AlertCircle size={17}/><span>{summary.opportunity_conflicts} lead(s) have conflicting historical outcomes across appointments. The totals count each lead only once. Review the duplicate records before treating the report as final.</span></div>}
    {error && <div className="sales-alert" role="alert"><AlertCircle size={17}/><span>{error}</span><button onClick={()=>setError('')} aria-label="Dismiss error"><XCircle size={17}/></button></div>}
    <SalesInsightsPanel pipeline={pipeline} onSelectAppointment={id=>{setSelectedId(id);setError('')}}/>
    <div className="sales-layout">
      <section className="panel sales-list-panel">
        <div className="sales-panel-title"><div><h3>Appointments pipeline</h3><p>Select a saved booking to manage its outcome.</p></div><span className="sales-count">{filtered.length} shown</span></div>
        <div className="sales-search"><Search size={16}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search lead or conversation ID" aria-label="Search sales appointments"/></div>
        <div className="sales-tabs" role="group" aria-label="Filter appointment statuses">{CATEGORIES.map(c=><button type="button" key={c.key} className={filter===c.key?'active':''} onClick={()=>setFilter(c.key)}>{c.label}</button>)}</div>
        <div className="sales-items">
          {loading && !pipeline ? <p className="sales-empty"><LoaderCircle className="spin" size={19}/> Loading saved meetings…</p>
            : filtered.length === 0 ? <div className="sales-empty"><CalendarCheck2 size={28}/><strong>No matching appointments</strong><p>Confirmed calendar bookings will appear here. Change the filter if needed.</p></div>
              : filtered.map(row => <button type="button" key={row.request_id} className={`sales-item ${selectedId===row.request_id?'selected':''}`} onClick={()=>{setSelectedId(row.request_id);setError('')}}>
                <div className="sales-item-top"><strong>{nameFor(row)}</strong>{pill(currentStatus(row))}</div>
                <div className="sales-item-meta"><Clock3 size={13}/>{showDate(row.start)}</div>
                <div className="sales-item-bottom"><span>{row.lead_category || 'Unqualified'} lead{row.lead_score==null?'':` · ${row.lead_score}/100`}</span>{row.outcome==='Won'?<strong>{formatMoney(row.deal_value)}</strong>:row.follow_up_at?<span>Next: {showDate(row.follow_up_at)}</span>:null}</div>
                {row.opportunity_appointment_count>1 && <div className="sales-shared-opportunity">One lead opportunity · {row.opportunity_appointment_count} appointments{row.opportunity_outcome?` · ${row.opportunity_outcome}`:''}</div>}
              </button>)}
        </div>
      </section>
      <section className="panel sales-detail-panel">
        {!selected ? <div className="sales-empty large"><ClipboardList size={35}/><strong>Select a booked appointment</strong><p>You can mark a finished meeting complete, then record follow-up, won or lost.</p></div>
          : <>
            <div className="sales-panel-title"><div><h3>{nameFor(selected)}</h3><p>{showDate(selected.start)} – {showDate(selected.end)}</p></div>{pill(currentStatus(selected))}</div>
            <div className="sales-summary-strip"><div><small>CRM lead</small><strong>{selected.lead_category || 'Unknown'}{selected.lead_score==null?'':` · ${selected.lead_score}/100`}</strong></div><div><small>Appointment</small><strong>{selected.request_id.slice(0, 8)}…</strong></div></div>
            {selected.opportunity_appointment_count>1 && <div className="sales-opportunity-banner">
              <strong>One sales opportunity · {selected.opportunity_appointment_count} appointments</strong>
              <span>Lead outcome: {selected.opportunity_outcome || 'Not recorded yet'}. Meeting notes remain separate for each appointment; a Won/Lost amount is counted once per lead.</span>
              {selected.opportunity_owner_request_id && selected.opportunity_owner_request_id!==selected.request_id && <button type="button" onClick={()=>setSelectedId(selected.opportunity_owner_request_id)}>Open appointment with recorded outcome <ArrowRight size={13}/></button>}
            </div>}
            <button className="sales-open-lead" onClick={()=>onOpenConversation(selected.conversation_id)}><UserRound size={16}/> Open the original CRM conversation <ArrowRight size={15}/></button>
            <div className="sales-step"><span className="sales-step-number">1</span><div><h4>Meeting completed</h4><p>After the scheduled consultation ends, record what was discussed.</p></div></div>
            <form className="sales-edit-form" onSubmit={markCompleted}>
              <label htmlFor="sales-meeting-notes">Meeting notes</label><textarea id="sales-meeting-notes" rows={4} maxLength={4000} value={notes} onChange={e=>setNotes(e.target.value)} placeholder="Example: Demonstrated CRM, discussed integrations, pricing, and implementation timeline."/>
              <div className="sales-form-foot"><small>{notes.length}/4000 characters</small><button className="primary-button" type="submit" disabled={saving || !canComplete}>{saving?<LoaderCircle className="spin" size={15}/>:<CheckCircle2 size={15}/>} {selected.completed_at?'Save meeting notes':'Mark meeting completed'}</button></div>
              {!canComplete && <p className="sales-help">This appointment has not ended yet. You can mark it completed after its scheduled end time.</p>}
              {selected.completed_at && <p className="sales-confirmed"><CheckCircle2 size={15}/> Completed {showDate(selected.completed_at)}</p>}
            </form>
            <div className="sales-step"><span className="sales-step-number">2</span><div><h4>What happened next?</h4><p>Choose the actual sales outcome. You can update it later if a follow-up converts to a deal.</p></div></div>
            {selected.meeting_status!=='Meeting Completed' ? <div className="sales-locked"><ClipboardList size={19}/> Complete the meeting first to unlock sales outcomes.</div>
              : selected.opportunity_owner_request_id && selected.opportunity_owner_request_id!==selected.request_id ? <div className="sales-locked sales-opportunity-lock"><ClipboardList size={19}/><span>This lead already has a <strong>{selected.opportunity_outcome}</strong> outcome on another appointment. To avoid double counting, update that existing record instead.</span><button type="button" onClick={()=>setSelectedId(selected.opportunity_owner_request_id)}>Manage existing outcome <ArrowRight size={13}/></button></div>
              : <form className="sales-edit-form" onSubmit={saveOutcome}>
                <div className="sales-outcome-options" role="group" aria-label="Sales outcome">{['Follow-up Required','Won','Lost'].map(opt=><button type="button" key={opt} aria-pressed={outcome===opt} className={`sales-outcome-option ${outcome===opt?'chosen':''}`} onClick={()=>{setOutcome(opt);setError('')}}>{opt==='Follow-up Required'?<CalendarClock size={17}/>:opt==='Won'?<Trophy size={17}/>:<XCircle size={17}/>}<span>{opt}</span></button>)}</div>
                {outcome==='Follow-up Required' && <label className="sales-control">Follow-up date & time (your computer's local timezone)<input type="datetime-local" required value={followup} onChange={e=>setFollowup(e.target.value)}/><small>The date must be in the future. Local in-app reminders appear automatically while LeadPilot is open; desktop alerts are optional.</small></label>}
                {outcome==='Won' && <div className="sales-control"><label htmlFor="sales-deal-value">Agreed deal value (INR)</label><div className="sales-money-field"><span aria-hidden="true">₹</span><input id="sales-deal-value" type="number" required min="0.01" max="9999999999.99" step="0.01" value={dealValue} placeholder="45000" onChange={e=>setDealValue(e.target.value)}/></div><small>This is a recorded deal value, not verified payment or realized revenue.</small></div>}
                {outcome==='Lost' && <label className="sales-control">Why was the deal lost?<textarea rows={3} required maxLength={1000} value={lostReason} onChange={e=>setLostReason(e.target.value)} placeholder="Example: Price exceeded budget or customer chose another provider."/></label>}
                <div className="sales-form-foot"><span className="sales-help">Changes are saved to SQLite; Google Calendar is not modified.</span><button className="primary-button" disabled={saving} type="submit">{saving?<LoaderCircle size={16} className="spin"/>:<Save size={16}/>} Save outcome</button></div>
              </form>}
            {history.length>0 && <div className="sales-history"><h4>Activity history</h4>{history.map((h,i)=><div className="sales-activity" key={`${h.created_at}-${i}`}><span className="sales-activity-dot"/><div><strong>{h.description}</strong><small>{showDate(h.created_at)}</small></div></div>)}</div>}
          </>}
      </section>
    </div>
    <p className="sales-disclaimer"><TrendingUp size={15}/> This local pipeline records salesperson-entered results. It does not automatically contact customers, issue invoices, collect payments, or infer meeting outcomes from AI.</p>
  </div>
}
