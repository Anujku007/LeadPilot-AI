import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, ArrowRight, Bell, CalendarCheck2, CalendarClock, CalendarDays, CheckCircle2,
  ChevronDown, ChevronLeft, ChevronRight, CircleAlert, Clock3, Filter, Flame, Headphones,
  Inbox, LayoutDashboard, LogOut, MessageCircle, Mic2, MoreHorizontal, RefreshCw,
  Search, Send, ShieldCheck, Sparkles, Target, Trophy, UserRound, Users, Wallet, X,
  XCircle, Zap
} from 'lucide-react'
import { api, loadConversation, sendChat } from './api.js'
import VoiceReviewPanel from './VoiceReviewPanel.jsx'
import CalendarBookingPicker from './CalendarBookingPicker.jsx'
import './team-workspace.css'
import './sales-workspace-polish.css'
import './sales-viewport-fix.css'

const BANT = [
  { key: 'budget', label: 'Budget', icon: Wallet, values: { confirmed: 'Confirmed', limited: 'Limited' } },
  { key: 'authority', label: 'Authority', icon: ShieldCheck, values: { decision_maker: 'Decision maker', influencer: 'Influencer' } },
  { key: 'need', label: 'Need', icon: Target, values: { clear: 'Clear need', partial: 'Partial need' } },
  { key: 'timeline', label: 'Timeline', icon: Clock3, values: { within_30_days: 'Within 30 days', within_90_days: 'Within 90 days', later: 'Later' } },
]
const FILTERS = ['All', 'Hot', 'Warm', 'New', 'Booked', 'Follow-up', 'Won', 'Lost']
function shortId(id) { return String(id || '').slice(0, 8) }
function displayName(lead) { return `Lead ${shortId(lead?.id)}` }
function ist(value, options = {}) {
  if (!value) return 'Not scheduled'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? 'Invalid date' : d.toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', year: 'numeric',
    hour: 'numeric', minute: '2-digit', hour12: true, ...options
  }) + ' IST'
}
function localTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}
function leadStatus(lead, rows) {
  if (rows.some(r => (r.opportunity_outcome || r.outcome) === 'Won')) return 'Won'
  if (rows.some(r => (r.opportunity_outcome || r.outcome) === 'Lost')) return 'Lost'
  if (rows.some(r => (r.opportunity_outcome || r.outcome) === 'Follow-up Required')) return 'Follow-up'
  if (rows.some(r => r.meeting_status === 'Booked')) return 'Booked'
  if (lead?.lead?.category === 'Hot') return 'Hot'
  if (lead?.lead?.category === 'Warm') return 'Warm'
  return 'New'
}
function bestAction(lead, rows) {
  if (!lead) return { label: 'Select an assigned lead', description: 'Choose a conversation to see its next step.', type: 'none' }
  const status = leadStatus(lead, rows)
  if (status === 'Won') return { label: 'Opportunity won', description: 'The agreed deal is recorded. Review the meeting notes if needed.', type: 'meetings' }
  if (status === 'Lost') return { label: 'Review the loss reason', description: 'Check the recorded outcome and learn from this opportunity.', type: 'meetings' }
  const followUp = rows.find(r => (r.opportunity_outcome || r.outcome) === 'Follow-up Required')
  if (followUp) return { label: new Date(followUp.follow_up_at || 0) <= new Date() ? 'Follow-up is due' : 'Prepare your follow-up', description: followUp.follow_up_at ? `Scheduled for ${ist(followUp.follow_up_at)}.` : 'Review the follow-up details.', type: 'meetings' }
  const ended = rows.find(r => r.meeting_status !== 'Meeting Completed' && new Date(r.end) <= new Date())
  if (ended) return { label: 'Record meeting completion', description: 'The scheduled time has passed. Record notes only if the meeting actually occurred.', type: 'meetings' }
  if (rows.some(r => r.meeting_status === 'Meeting Completed' && !r.opportunity_outcome)) return { label: 'Record a sales outcome', description: 'Choose follow-up, won, or lost for the completed meeting.', type: 'meetings' }
  if (rows.some(r => r.meeting_status === 'Booked')) return { label: 'Prepare for the consultation', description: 'Review BANT information and the scheduled meeting.', type: 'meetings' }
  if (lead.lead?.category === 'Hot') return { label: 'Offer a consultation', description: 'The lead is qualified. Check real calendar availability before booking.', type: 'booking' }
  return { label: 'Continue qualification', description: 'Ask the customer for missing BANT details using the conversation.', type: 'chat' }
}
function countKnown(lead) { return BANT.filter(f => lead?.[f.key] && lead[f.key] !== 'unknown').length }
function amount(v) { return Number(v || 0).toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }) }

export default function TeamSalesWorkspace({ currentUser, onSignOut }) {
  const [leads, setLeads] = useState([])
  const [appointments, setAppointments] = useState([])
  const [selected, setSelected] = useState('')
  const [detail, setDetail] = useState(null)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [fetching, setFetching] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [voiceOpen, setVoiceOpen] = useState(false)
  const [bookingOpen, setBookingOpen] = useState(false)
  const [meetingsOpen, setMeetingsOpen] = useState(false)
  const [insightsOpen, setInsightsOpen] = useState(true)
  const [leadNavOpen, setLeadNavOpen] = useState(true)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('All')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [note, setNote] = useState('')
  const [outcome, setOutcome] = useState('Follow-up Required')
  const [followUp, setFollowUp] = useState('')
  const [deal, setDeal] = useState('')
  const [reason, setReason] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const messagesScrollRef = useRef(null)
  const actionsRef = useRef(null)
  const composeRef = useRef(null)
  const selectedRef = useRef('')
  selectedRef.current = selected

  async function refresh(options = {}) {
    try {
      const [leadResponse, pipelineResponse] = await Promise.all([api('/api/team/my-leads'), api('/api/team/my-pipeline')])
      const fetched = leadResponse.leads || []
      setLeads(fetched)
      setAppointments(pipelineResponse.appointments || [])
      setSelected(old => fetched.some(l => l.id === old) ? old : (fetched[0]?.id || ''))
      if (!options.quiet) setError('')
    } catch (e) {
      setError(e.message || 'Could not load your assigned CRM data.')
    } finally { setFetching(false) }
  }
  useEffect(() => { void refresh() }, [])
  useEffect(() => {
    let active = true
    setDetail(null)
    setDetailLoading(Boolean(selected))
    if (selected) loadConversation(selected)
      .then(result => { if (active) setDetail(result) })
      .catch(e => { if (active) setError(e.message) })
      .finally(() => { if (active) setDetailLoading(false) })
    return () => { active = false }
  }, [selected, refreshKey])
  // Scroll only the message panel. scrollIntoView() moved the entire browser page.
  useEffect(() => {
    const panel = messagesScrollRef.current
    if (panel) panel.scrollTop = panel.scrollHeight
  }, [detail?.messages?.length, selected])

  const lead = leads.find(l => l.id === selected)
  const sortedLeads = useMemo(() => [...leads].sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || ''))), [leads])
  const byConversation = useMemo(() => {
    const map = new Map()
    appointments.forEach(row => map.set(row.conversation_id, [...(map.get(row.conversation_id) || []), row]))
    return map
  }, [appointments])
  const ownAppointments = useMemo(() => [...(byConversation.get(selected) || [])].sort((a, b) => String(b.start).localeCompare(String(a.start))), [byConversation, selected])
  const decorated = useMemo(() => sortedLeads.map(l => ({ ...l, status: leadStatus(l, byConversation.get(l.id) || []) })), [sortedLeads, byConversation])
  const filteredLeads = decorated.filter(l => {
    const matches = filter === 'All' || l.status === filter || (filter === 'Hot' && l.lead?.category === 'Hot') || (filter === 'Warm' && l.lead?.category === 'Warm')
    const q = query.toLowerCase().trim()
    return matches && (!q || l.id.toLowerCase().includes(q) || String(l.last_message || '').toLowerCase().includes(q) || displayName(l).toLowerCase().includes(q))
  })
  const uniqueWon = new Set(appointments.filter(r => (r.opportunity_outcome || r.outcome) === 'Won').map(r => r.conversation_id)).size
  const uniqueDue = new Set(appointments.filter(r => (r.opportunity_outcome || r.outcome) === 'Follow-up Required' && r.follow_up_at && new Date(r.follow_up_at) <= new Date()).map(r => r.conversation_id)).size
  const bookedFuture = appointments.filter(r => r.meeting_status === 'Booked' && new Date(r.end) > new Date()).length
  const hotLeads = leads.filter(l => l.lead?.category === 'Hot').length
  const action = bestAction(lead, ownAppointments)
  const missing = BANT.filter(f => !detail?.lead?.[f.key] || detail.lead[f.key] === 'unknown')

  function chooseLead(id) {
    if (id === selected) return
    setSelected(id)
    setMessage('')
    setVoiceOpen(false)
    setBookingOpen(false)
    setMeetingsOpen(false)
    setNote(''); setOutcome('Follow-up Required'); setFollowUp(''); setDeal(''); setReason('')
    setError(''); setNotice('')
  }
  function openTool(which) {
    if (which === 'voice') setVoiceOpen(v => !v)
    if (which === 'booking') setBookingOpen(v => !v)
    if (which === 'meetings') setMeetingsOpen(v => !v)
    if (which === 'chat') { composeRef.current?.focus(); return }
    // Opening voice/calendar/meetings must not scroll the document itself.
    requestAnimationFrame(() => {
      if (actionsRef.current) actionsRef.current.scrollTop = 0
    })
  }
  async function run(fn, successMessage) {
    setLoading(true); setError(''); setNotice('')
    try {
      const result = await fn()
      await refresh({ quiet: true })
      setRefreshKey(k => k + 1)
      if (successMessage) setNotice(successMessage)
      return result
    } catch (e) {
      setError(e.message || 'Something went wrong.')
      throw e
    } finally { setLoading(false) }
  }
  async function send(text) {
    const value = String(text || '').trim()
    if (!selected || !value || loading) return null
    const requestedId = selected
    const result = await run(() => sendChat(requestedId, value))
    if (selectedRef.current === requestedId) setMessage('')
    return result?.reply
  }
  async function doComplete(id) {
    await run(() => api(`/api/sales/appointments/${id}/complete`, { method: 'POST', data: { meeting_notes: note } }), 'Meeting completion saved.')
  }
  async function doOutcome(id) {
    const data = { outcome }
    if (outcome === 'Follow-up Required') {
      if (!followUp || Number.isNaN(new Date(followUp).getTime())) { setError('Choose a valid follow-up date and time.'); return }
      if (new Date(followUp) <= new Date()) { setError('Follow-up date must be in the future.'); return }
      data.follow_up_at = new Date(followUp).toISOString()
    }
    if (outcome === 'Won') data.deal_value = deal
    if (outcome === 'Lost') data.lost_reason = reason.trim()
    await run(() => api(`/api/sales/appointments/${id}/outcome`, { method: 'PATCH', data }), 'Sales outcome saved.')
  }

  return <div className="lp-staff-shell lps-shell">
    <header className="lps-topbar">
      <div className="lps-brand"><span className="lps-brand-icon"><Sparkles size={22}/></span><div><strong>LeadPilot <em>AI</em></strong><small>Sales Copilot Workspace</small></div></div>
      <div className="lps-topbar-right"><span className="lps-secure-pill"><ShieldCheck size={15}/> Assigned leads only</span><button type="button" className="lps-icon-btn lps-header-refresh" title="Refresh my CRM data" aria-label="Refresh my CRM data" disabled={fetching} onClick={() => void refresh()}><RefreshCw size={18}/></button><div className="lps-profile"><span className="lps-avatar">{(currentUser.username || 'S').slice(0,1).toUpperCase()}</span><div><strong>{currentUser.username}</strong><small>Sales operator</small></div></div><button type="button" className="lps-signout" onClick={onSignOut}><LogOut size={16}/><span>Sign out</span></button></div>
    </header>

    <section className="lps-overview" aria-label="My sales snapshot">
      <div className="lps-overview-title"><div><span className="lps-eyebrow"><Zap size={13}/> YOUR DAILY WORKSPACE</span><h1>Good to see you, {currentUser.username}</h1><p>Review assigned leads, continue conversations, and move opportunities forward.</p></div><button type="button" className="lps-text-btn" onClick={() => void refresh()}><RefreshCw size={16}/> Refresh</button></div>
      <div className="lps-stats">
        <div className="lps-stat"><span className="lps-stat-icon purple"><Users size={20}/></span><div><strong>{leads.length}</strong><small>Assigned leads</small></div></div>
        <div className="lps-stat"><span className="lps-stat-icon coral"><Flame size={20}/></span><div><strong>{hotLeads}</strong><small>Hot leads</small></div></div>
        <div className="lps-stat"><span className="lps-stat-icon blue"><CalendarDays size={20}/></span><div><strong>{bookedFuture}</strong><small>Upcoming meetings</small></div></div>
        <div className="lps-stat"><span className="lps-stat-icon amber"><Bell size={20}/></span><div><strong>{uniqueDue}</strong><small>Follow-ups due</small></div></div>
        <div className="lps-stat"><span className="lps-stat-icon green"><Trophy size={20}/></span><div><strong>{uniqueWon}</strong><small>Won opportunities</small></div></div>
      </div>
    </section>

    {error && <div className="lps-alert error" role="alert"><CircleAlert size={17}/><span>{error}</span><button type="button" onClick={() => setError('')} aria-label="Dismiss error"><X size={16}/></button></div>}
    {notice && <div className="lps-alert success" role="status"><CheckCircle2 size={17}/><span>{notice}</span><button type="button" onClick={() => setNotice('')} aria-label="Dismiss notification"><X size={16}/></button></div>}

    <div className={`lps-workspace ${insightsOpen ? '' : 'lps-insights-hidden'} ${leadNavOpen ? '' : 'lps-leads-hidden'}`}>
      <aside className="lps-lead-pane" aria-label="Assigned leads">
        <div className="lps-pane-heading"><div><h2>My leads <span className="lps-count">{leads.length}</span></h2><p>Only leads assigned to you</p></div><button type="button" className="lps-icon-btn" title="Collapse leads" aria-label="Collapse leads" onClick={() => setLeadNavOpen(false)}><ChevronLeft size={17}/></button></div>
        <div className="lps-search"><Search size={16}/><input aria-label="Search assigned leads" placeholder="Search leads or messages…" value={query} onChange={e => setQuery(e.target.value)}/>{query && <button type="button" onClick={() => setQuery('')} aria-label="Clear search"><X size={14}/></button>}</div>
        <div className="lps-filters" aria-label="Filter leads by status">{FILTERS.map(f => <button type="button" key={f} className={filter === f ? 'active' : ''} aria-pressed={filter === f} onClick={() => setFilter(f)}>{f}</button>)}</div>
        <div className="lps-lead-list">{fetching && leads.length === 0 ? <div className="lps-loading"><span/><span/><span/></div> : filteredLeads.length === 0 ? <div className="lps-list-empty"><Inbox size={26}/><strong>{leads.length ? 'No matching leads' : 'No leads assigned'}</strong><span>{leads.length ? 'Try another filter or search.' : 'Ask your admin to assign a conversation.'}</span></div> : filteredLeads.map(l => <button type="button" key={l.id} className={`lps-lead-card ${selected === l.id ? 'selected' : ''}`} aria-current={selected === l.id ? 'true' : undefined} onClick={() => chooseLead(l.id)}><div className="lps-lead-card-top"><span className="lps-lead-avatar">{shortId(l.id).slice(0, 2).toUpperCase()}</span><span className="lps-lead-title"><strong>{displayName(l)}</strong><small>{localTime(l.updated_at)}</small></span><span className={`lps-chip ${l.status.toLowerCase().replace(/[^a-z]/g,'')}`}>{l.status}</span></div><p>{l.last_message || 'No messages yet — ready to start'}</p><div className="lps-lead-card-bottom"><span><Target size={13}/> {l.lead?.score ?? 0}/100 BANT</span><ArrowRight size={16}/></div></button>)}</div>
        <div className="lps-scoped-note"><ShieldCheck size={15}/> Your access is limited to assigned CRM conversations.</div>
      </aside>

      <main className="lps-chat-pane" aria-label="Lead conversation">
        <div className="lps-chat-head">
          {!leadNavOpen && <button type="button" className="lps-icon-btn" aria-label="Show assigned leads" onClick={() => setLeadNavOpen(true)}><ChevronRight size={18}/></button>}
          <div className="lps-chat-title"><span className="lps-chat-title-icon"><MessageCircle size={19}/></span><div><h2>{lead ? displayName(lead) : 'Select a conversation'}</h2><p>{lead ? `${lead.lead?.category || 'New'} lead · CRM conversation ${shortId(selected)}` : 'Choose a lead from the sidebar'}</p></div></div>
          <div className="lps-chat-head-actions"><span className={`lps-chip ${lead ? leadStatus(lead, ownAppointments).toLowerCase().replace(/[^a-z]/g, '') : ''}`}>{lead ? leadStatus(lead, ownAppointments) : 'Idle'}</span><button type="button" className="lps-icon-btn" title={insightsOpen ? 'Hide insights' : 'Show insights'} aria-label={insightsOpen ? 'Hide insights' : 'Show insights'} onClick={() => setInsightsOpen(v => !v)}><LayoutDashboard size={18}/></button></div>
        </div>
        {!selected ? <div className="lps-chat-empty"><span><MessageCircle size={29}/></span><h3>No conversation selected</h3><p>Choose one of your assigned leads to pick up where the customer left off.</p></div> : <>
          <div className="lps-messages" ref={messagesScrollRef} aria-label="Conversation history">
            {detailLoading ? <div className="lps-loading chat"><span/><span/><span/></div> : detail?.messages?.length ? detail.messages.map((m, i) => <div key={`${selected}-${i}`} className={`lps-message-row ${m.role === 'user' ? 'customer' : 'agent'}`}><span className="lps-message-avatar">{m.role === 'user' ? <UserRound size={15}/> : <Sparkles size={15}/>}</span><div className="lps-message-wrap"><span className="lps-message-author">{m.role === 'user' ? 'Customer' : 'LeadPilot AI'}</span><div className="lps-message-bubble">{m.content}</div></div></div>) : <div className="lps-chat-empty"><span><MessageCircle size={28}/></span><h3>Start the conversation</h3><p>Send a message to begin working with this assigned lead.</p></div>}
          </div>
          <div className="lps-chat-bottom">
            <div className="lps-chat-quick-actions"><span><Sparkles size={15}/> Sales copilot</span><button type="button" className={voiceOpen ? 'active' : ''} onClick={() => openTool('voice')}><Mic2 size={15}/> Voice review</button><button type="button" className={bookingOpen ? 'active' : ''} onClick={() => openTool('booking')}><CalendarClock size={15}/> Check slots</button><button type="button" className={meetingsOpen ? 'active' : ''} onClick={() => openTool('meetings')}><CalendarCheck2 size={15}/> Meetings</button></div>
            <form className="lps-composer" onSubmit={e => { e.preventDefault(); void send(message).catch(() => {}) }}><textarea ref={composeRef} maxLength={2000} rows={2} aria-label="Reply as customer for lead demo" value={message} onChange={e => setMessage(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(message).catch(() => {}) } }} placeholder="Reply as the customer during the lead demo…"/><div className="lps-compose-footer"><span>Enter to send · Shift+Enter for a new line · {message.length}/2000</span><button type="submit" disabled={loading || !message.trim()}><Send size={16}/>{loading ? 'Sending…' : 'Send to AI'}</button></div></form>
          </div>
          <div className="lps-tool-stack" ref={actionsRef}>
            {voiceOpen && <section className="lps-tool-card"><div className="lps-tool-title"><h3><Headphones size={18}/> Voice recording & review</h3><button type="button" className="lps-icon-btn" onClick={() => setVoiceOpen(false)} aria-label="Close voice panel"><X size={16}/></button></div><VoiceReviewPanel activeId={selected} resetKey={selected} busy={loading} onVoiceTurn={text => send(text)}/></section>}
            {bookingOpen && <section className="lps-tool-card"><div className="lps-tool-title"><h3><CalendarDays size={18}/> Schedule a consultation</h3><button type="button" className="lps-icon-btn" onClick={() => setBookingOpen(false)} aria-label="Close booking panel"><X size={16}/></button></div><CalendarBookingPicker conversationId={selected} messageCount={detail?.messages?.length || 0} isHot={lead?.lead?.category === 'Hot'} notify={text => setNotice(text)} onConfirmed={() => void refresh()}/>{lead?.lead?.category !== 'Hot' && <p className="lps-tool-hint">Complete BANT qualification before proposing an appointment.</p>}</section>}
            {meetingsOpen && <section className="lps-tool-card"><div className="lps-tool-title"><h3><CalendarCheck2 size={18}/> Meetings & sales outcomes</h3><button type="button" className="lps-icon-btn" onClick={() => setMeetingsOpen(false)} aria-label="Close meetings panel"><X size={16}/></button></div>{!ownAppointments.length ? <p className="lps-tool-hint">No confirmed meetings for this lead yet.</p> : ownAppointments.map(a => <article className="lps-meeting" key={a.request_id}><div className="lps-meeting-top"><strong>{ist(a.start)}</strong><span className={`lps-chip ${a.meeting_status === 'Meeting Completed' ? 'won' : 'booked'}`}>{a.meeting_status}</span></div><p>Outcome: {a.opportunity_outcome || a.outcome || 'Pending'}</p>
              {a.meeting_status !== 'Meeting Completed' && new Date(a.end) <= new Date() && <form className="lps-meeting-form" onSubmit={e => { e.preventDefault(); void doComplete(a.request_id).catch(() => {}) }}><label>Meeting notes<textarea maxLength={4000} required value={note} onChange={e => setNote(e.target.value)} placeholder="What actually happened in the consultation?"/></label><button type="submit" disabled={loading || !note.trim()}><CheckCircle2 size={15}/> Mark meeting completed</button></form>}
              {a.meeting_status === 'Booked' && new Date(a.end) > new Date() && <small className="lps-meeting-hint">Completion becomes available after the scheduled end, and only if the meeting actually happened.</small>}
              {a.meeting_status === 'Meeting Completed' && (!a.opportunity_owner_request_id || a.opportunity_owner_request_id === a.request_id) && <form className="lps-meeting-form" onSubmit={e => { e.preventDefault(); void doOutcome(a.request_id).catch(() => { }) }}><label>Sales outcome<select value={outcome} onChange={e => setOutcome(e.target.value)}><option>Follow-up Required</option><option>Won</option><option>Lost</option></select></label>
                {outcome === 'Follow-up Required' && <label>Follow-up date & time<input type="datetime-local" required value={followUp} onChange={e => setFollowUp(e.target.value)}/></label>}
                {outcome === 'Won' && <label>Agreed deal value (INR)<input type="number" min="0.01" step="0.01" required value={deal} onChange={e => setDeal(e.target.value)}/></label>}
                {outcome === 'Lost' && <label>Reason for losing the opportunity<textarea required maxLength={1000} value={reason} onChange={e => setReason(e.target.value)}/></label>}
                <button type="submit" disabled={loading}><CheckCircle2 size={15}/> Save outcome</button>
              </form>}
              {a.opportunity_owner_request_id && a.opportunity_owner_request_id !== a.request_id && <small className="lps-meeting-hint">The outcome for this conversation is managed on another appointment to avoid duplicate deals.</small>}
            </article>)}</section>}
          </div>
        </>}
      </main>

      {insightsOpen && <aside className="lps-insights" aria-label="Lead insights">
        <div className="lps-insights-head"><div><h2><Sparkles size={19}/> Lead Insights</h2><p>Live CRM qualification</p></div><button type="button" className="lps-icon-btn" title="Hide insights" aria-label="Hide insights" onClick={() => setInsightsOpen(false)}><ChevronRight size={17}/></button></div>
        {selected && lead ? <div className="lps-insights-scroll">
          <div className="lps-insights-card lps-score-card"><div className="lps-score-top"><div><small>Qualification score</small><strong>{detail?.lead?.score ?? lead.lead?.score ?? 0}<span>/100</span></strong></div><span className={`lps-chip ${(detail?.lead?.category || lead.lead?.category || 'new').toLowerCase()}`}>{detail?.lead?.category || lead.lead?.category || 'New'}</span></div><div className="lps-progress"><div style={{width: `${Math.min(100, Math.max(0, detail?.lead?.score ?? lead.lead?.score ?? 0))}%`}}/></div><small>{countKnown(detail?.lead || lead.lead)} of 4 BANT fields captured</small></div>
          <div className="lps-insights-card"><h3>Qualification details</h3><div className="lps-bant-grid">{BANT.map(({key,label,icon:Icon,values}) => {const raw = (detail?.lead || lead.lead || {})[key];return <div className="lps-bant" key={key}><span className="lps-bant-icon"><Icon size={16}/></span><div><strong>{label}</strong><small>{values[raw] || (raw && raw !== 'unknown' ? raw.replaceAll('_', ' ') : 'Not captured yet')}</small></div>{raw && raw !== 'unknown' ? <CheckCircle2 size={16} className="captured"/> : <CircleAlert size={15} className="missing"/>}</div>})}</div></div>
          <div className="lps-insights-card lps-next-action"><span className="lps-eyebrow"><Zap size={13}/> RULE-BASED NEXT ACTION</span><h3>{action.label}</h3><p>{action.description}</p><button type="button" onClick={() => openTool(action.type)} disabled={action.type === 'none'}>Take action <ArrowRight size={15}/></button></div>
          <div className="lps-insights-card"><h3><CalendarDays size={16}/> Appointment overview</h3><p className="lps-insight-count"><strong>{ownAppointments.length}</strong> booked meeting{ownAppointments.length === 1 ? '' : 's'}</p>{ownAppointments.slice(0,2).map(a => <div key={a.request_id} className="lps-mini-appointment"><strong>{ist(a.start)}</strong><small>{a.meeting_status} · {a.opportunity_outcome || a.outcome || 'No outcome recorded'}</small></div>)}<button type="button" className="lps-panel-link" onClick={() => openTool('meetings')}>Manage meetings <ArrowRight size={15}/></button></div>
          {missing.length > 0 && <div className="lps-insights-card"><h3>Still to qualify</h3><p>{missing.map(f => f.label).join(', ')}. Ask the customer for these details during the chat.</p></div>}
        </div> : <div className="lps-insight-empty"><Target size={26}/><p>Choose a lead to see its live BANT score and next action.</p></div>}
      </aside>}
    </div>
  </div>
}
