import { useEffect, useMemo, useRef, useState } from 'react'
import { TrendingUp } from 'lucide-react'
import SalesPipelinePage from './SalesPipelinePage.jsx'
import FollowUpObserver from './FollowUpObserver.jsx'
import CalendarBookingPicker from './CalendarBookingPicker.jsx'
import SalesPipelineErrorBoundary from './SalesPipelineErrorBoundary.jsx'
import {
  Activity, ArrowLeft, ArrowRight, ArrowUpRight, Bell, BookOpen, Bot, CalendarCheck2,
  CalendarDays, Check, CheckCircle2, ChevronDown, CircleHelp, Clock3, Copy, Database,
  Ellipsis, Flame, Headphones, HeartHandshake, Info, LayoutDashboard, ListFilter, LogOut,
  LoaderCircle, LockKeyhole, Menu, MessageCircle, MessagesSquare, Mic2, PanelLeftClose,
  PanelLeftOpen, PanelRightClose, PanelRightOpen, PhoneCall, PhoneOff, Pencil, Plus, RefreshCcw,
  Search, Send, Settings2, ShieldCheck, Sparkles, Target, UsersRound, Wallet, X
} from 'lucide-react'
import {
  api, loadSummary, loadConversations, loadAppointments, loadConversation,
  startConversation, sendChat, loadAvailable, createProposal, confirmProposal, loadGatewayHealth, saveLeadLabel
} from './api.js'
import {
  SCORE_FIELDS, LABELS, nextQuestion, shortDate, formatSlot, dayIST, leadName,
  shortId, scoreLabel, getInitials
} from './utils.js'
import VoiceReviewPanel from './VoiceReviewPanel.jsx'

const MENU = [
  { id: 'dashboard', name: 'Dashboard', icon: LayoutDashboard },
  { id: 'leads', name: 'Leads', icon: UsersRound },
  { id: 'conversations', name: 'Conversations', icon: MessagesSquare },
  { id: 'calls', name: 'Voice Calls', icon: PhoneCall },
  { id: 'appointments', name: 'Appointments', icon: CalendarDays },
  { id: 'sales', name: 'Sales Pipeline', icon: TrendingUp },
  { id: 'settings', name: 'Settings', icon: Settings2 }
]
const DEFAULT_SUMMARY = { total_leads: 0, hot_leads: 0, qualified_leads: 0, appointments_booked: 0, total_conversations: 0 }
function persisted(key, defaultValue) {
  try { const v = localStorage.getItem(key); return v === null ? defaultValue : JSON.parse(v) }
  catch { return defaultValue }
}
function Badge({ label, variant = 'muted', dot = false }) {
  return <span className={`lp-badge ${variant}`}>{dot && <span className="badge-dot" />}{label}</span>
}
function Logo() {
  return <div className="brand">
    <span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 48 48" width="35" height="35"><defs><linearGradient id="g" x1="0%" y1="100%" x2="100%" y2="0%"><stop offset="0%" stopColor="#6150ec" /><stop offset="100%" stopColor="#a46bff" /></linearGradient></defs><path d="M24 3c2.3 0 3.8 1.2 5.2 3.6L46 36.4c1.7 3-.3 6.7-3.8 6.7H34L24 24.5 14 43.1H5.8c-3.5 0-5.5-3.7-3.8-6.7L18.8 6.6C20.2 4.2 21.7 3 24 3Z" fill="url(#g)"/><path d="M24 25 34 43.1H14L24 25Z" fill="#dbd1ff"/></svg></span>
    <span className="brand-text">LeadPilot <strong>AI</strong></span>
  </div>
}
function Empty({ icon: Icon = MessagesSquare, title, message, action, actionText }) {
  return <div className="empty-state"><div className="empty-icon"><Icon size={28} strokeWidth={1.65} /></div>
    <h3>{title}</h3><p>{message}</p>{action && <button type="button" onClick={action} className="primary-button"><Plus size={16}/>{actionText || 'Create conversation'}</button>}</div>
}
function Toast({ message, onDismiss }) {
  if (!message) return null
  return <div className="toast" role="status"><Info size={17}/><span>{message}</span><button aria-label="Dismiss message" onClick={onDismiss}><X size={16}/></button></div>
}
function Kpi({ label, value, icon: Icon, tone, note }) {
  return <article className="kpi-card"><span className={`kpi-icon ${tone}`}><Icon size={23} strokeWidth={2.1}/></span>
    <span className="kpi-data"><span className="kpi-label">{label}</span><strong>{value?.toLocaleString?.('en-IN') ?? '—'}</strong></span>
    <span className="kpi-note" title={note || 'Live CRM data'}><span className="live-mini-dot"/>{note || 'From CRM'}</span>
  </article>
}
function UserAvatar({ name, size = 'normal', assistant = false }) {
  return <span className={`user-avatar ${assistant ? 'is-bot' : ''} ${size === 'small' ? 'small' : ''}`} aria-hidden="true">{assistant ? <Sparkles size={18}/> : getInitials(name)}</span>
}
function LeftNav({ collapsed, toggle, navigate, page, onMobileClose }) {
  return <>
    <div className="sidebar-brand"><Logo />
      <button className="icon-button sidebar-collapse" title={collapsed ? 'Expand navigation' : 'Collapse navigation'} onClick={toggle} aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}>{collapsed ? <PanelLeftOpen size={19}/> : <PanelLeftClose size={19}/>}</button>
      <button className="icon-button mobile-close" aria-label="Close navigation" onClick={onMobileClose}><X size={20}/></button>
    </div>
    <nav className="nav-items" aria-label="Primary navigation">
      {MENU.map(({ id, name, icon: Icon }) => <button key={id} className={`nav-link ${page === id ? 'active' : ''}`} title={collapsed ? name : ''} aria-current={page === id ? 'page' : undefined} onClick={() => {navigate(id); onMobileClose()}}><Icon size={20} strokeWidth={2}/><span className="nav-text">{name}</span></button>)}
    </nav>
    <div className="sidebar-grow"/>
    <div className="sidebar-promo"><div className="promo-stars">✦</div><div className="promo-orb"><Bot size={35}/></div><strong>AI Copilot<br/>Workspace</strong><p>Qualify leads. Start meaningful conversations. Stay organized.</p></div>
    <div className="sidebar-foot"><span className="foot-dot"/> Local workspace <span className="foot-short">LP</span></div>
  </>
}
function TopBar({ search, setSearch, onMenu, onToggleRight, rightOpen, connected, refresh, busy, searchRef, currentUser, onSignOut, onTeamOpen, signOutBusy, signOutError }) {
  const [accountOpen, setAccountOpen] = useState(false)
  const accountRef = useRef(null)
  useEffect(() => {
    if (!accountOpen) return undefined
    const onOutside = (event) => {
      if (accountRef.current && !accountRef.current.contains(event.target)) setAccountOpen(false)
    }
    const onEscape = (event) => { if (event.key === 'Escape') setAccountOpen(false) }
    document.addEventListener('pointerdown', onOutside)
    document.addEventListener('keydown', onEscape)
    return () => {
      document.removeEventListener('pointerdown', onOutside)
      document.removeEventListener('keydown', onEscape)
    }
  }, [accountOpen])
  const operatorName = currentUser?.username || 'Operator'
  return <header className="topbar">
    <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={onMenu}><Menu size={22}/></button>
    <div className="search-wrap"><Search size={19}/><input ref={searchRef} aria-label="Search conversations and leads" placeholder="Search leads, conversations, or IDs..." value={search} onChange={e => setSearch(e.target.value)}/><kbd>Ctrl K</kbd></div>
    <div className="top-actions"><button title="Refresh CRM data" className="icon-button" aria-label="Refresh CRM data" onClick={refresh} disabled={busy}><RefreshCcw size={19} className={busy ? 'spin' : ''}/></button>
      <span className={`connection-chip ${connected ? 'online' : 'offline'}`}><i/>{connected ? 'API connected' : 'API offline'}</span>
      <button title={rightOpen ? 'Hide lead insights' : 'Show lead insights'} aria-label={rightOpen ? 'Hide lead insights' : 'Show lead insights'} aria-expanded={rightOpen} className="icon-button insights-toggle" onClick={onToggleRight}>{rightOpen ? <PanelRightClose size={20}/> : <PanelRightOpen size={20}/>}</button>
      <span className="header-separator"/>
      <div className="lp-account-menu" ref={accountRef}>
        <button type="button" className="lp-account-trigger" aria-label={`Account menu for ${operatorName}`} aria-expanded={accountOpen} aria-haspopup="true" onClick={() => setAccountOpen(open => !open)}>
          <UserAvatar name={operatorName} size="small"/>
          <span className="lp-account-identity"><strong>{operatorName}</strong><small>Signed in</small></span>
          <ChevronDown size={15} className={accountOpen ? 'lp-account-arrow open' : 'lp-account-arrow'}/>
        </button>
        {accountOpen && <div className="lp-account-popover" role="group" aria-label="Account actions">
          <div className="lp-account-summary"><strong>{operatorName}</strong><small>Local LeadPilot AI operator</small></div>
          {signOutError && <p className="lp-account-error" role="alert">{signOutError}</p>}
          {onTeamOpen && <button type="button" className="lp-account-signout" onClick={() => { setAccountOpen(false); onTeamOpen() }}><UsersRound size={17}/> Manage team & assignments</button>}
          <button type="button" className="lp-account-signout" disabled={signOutBusy || !onSignOut} onClick={onSignOut}><LogOut size={17}/>{signOutBusy ? 'Signing out…' : 'Sign out'}</button>
        </div>}
      </div>
    </div>
  </header>
}
function scoreVariant(category) {
  if (category === 'Hot') return 'hot'
  if (category === 'Warm') return 'warm'
  if (category === 'Cold') return 'cold'
  return 'muted'
}
function Insights({ selected, selectedDetail, appointments, goSchedule, close, loading }) {
  const lead = selectedDetail?.lead || selected?.lead
  const booked = appointments?.filter(a => a.conversation_id === selected?.id) || []
  const score = lead?.score || 0
  const filled = SCORE_FIELDS.filter(f => lead?.[f.key] && lead[f.key] !== 'unknown')
  const next = SCORE_FIELDS.find(f => !lead?.[f.key] || lead[f.key] === 'unknown')
  return <div className="insights-inner">
    <div className="insights-header"><div className="insights-title-row"><span className="insights-icon"><Sparkles size={22}/></span><div><h2>Lead Insights <span>(BANT)</span></h2><p>AI-powered qualification & next best action</p></div></div><button onClick={close} className="icon-button right-close" title="Collapse insights" aria-label="Collapse lead insights"><PanelRightClose size={19}/></button></div>
    {!selected ? <Empty icon={Target} title="No lead selected" message="Start or select a conversation to see the BANT intelligence panel."/> : <>
      <div className="selected-lead-card"><div className="selected-lead-top"><UserAvatar name={leadName(selected)}/><div><strong>{leadName(selected)}</strong><span>Conversation {selected.id.slice(0, 12)}...</span></div></div><Badge variant={scoreVariant(lead?.category)} label={scoreLabel(lead)}/></div>
      <section className="insight-card score-card"><div className="insight-score-info"><div className="subsection-label">Lead Score <Info size={14}/></div><div className="score-big">{score}<span> / 100</span></div><Badge label={lead?.category ? `${lead.category} lead` : 'Not qualified'} variant={scoreVariant(lead?.category)} /></div><div className="score-ring" style={{ '--score': `${Math.min(100, Math.max(0, score))}%` }}><span>{score}</span></div></section>
      <div className="bant-stack">{SCORE_FIELDS.map(({ key, letter, label }) => {
        const completed = lead?.[key] && lead[key] !== 'unknown'
        return <div className="bant-row" key={key}><span className="bant-letter">{letter}</span><div className="bant-value"><strong>{label}</strong><small>{LABELS[lead?.[key]] || 'Not yet captured'}</small></div>{completed ? <span className="qualified-mark"><Check size={13}/><span>Captured</span></span> : <span className="pending-mark">Pending</span>}</div>
      })}</div>
      <div className="completion-card"><span>Qualification progress</span><strong>{filled.length} / 4</strong><div className="progress-track"><span style={{ width: `${filled.length * 25}%` }}/></div></div>
      <div className="booking-card"><CalendarDays size={19}/><span>Booking status</span><Badge label={booked.length ? `${booked.length} saved` : "No saved booking"} variant={booked.length ? "green" : "purple"}/></div>
      <div className="next-action-card"><div className="next-head"><Sparkles size={20}/><strong>Suggested Next Action</strong></div>{next ? <><h3>Ask about {next.label.toLowerCase()}</h3><p>{nextQuestion[next.key]}</p><div className="next-foot">Continue the conversation to capture this information.</div></> : <><h3>Offer a 30-minute consultation</h3><p>All four BANT fields are captured. Check Google Calendar availability and ask for explicit confirmation.</p><button className="primary-button full-width" onClick={goSchedule}><CalendarDays size={17}/> View appointment slots <ArrowRight size={16}/></button></>}</div>
      {loading && <div className="sidebar-loading"><LoaderCircle className="spin" size={15}/> Updating lead profile...</div>}
    </>}
  </div>
}
function ConversationPicker({ conversations, selectedId, onSelect, search }) {
  const [open, setOpen] = useState(false)
  return <div className="picker-wrap">
    <button className="conversation-picker" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(!open)}><span>{conversations.find(c => c.id === selectedId) ? leadName(conversations.find(c => c.id === selectedId)) : 'Select a conversation'}</span><ChevronDown size={15}/></button>
    {open && <div className="picker-menu" role="listbox">{conversations.filter(c => `${leadName(c)} ${c.id} ${c.last_message?.content || ''}`.toLowerCase().includes(search.toLowerCase())).length ? conversations.filter(c => `${leadName(c)} ${c.id} ${c.last_message?.content || ''}`.toLowerCase().includes(search.toLowerCase())).slice(0, 50).map(c => <button role="option" aria-selected={c.id === selectedId} key={c.id} onClick={() => { onSelect(c.id); setOpen(false) }}><span className="picker-initials"><MessageCircle size={15}/></span><span><strong>{leadName(c)}</strong><small>{c.lead?.category || 'New'} · {shortDate(c.updated_at)}</small></span>{c.id === selectedId && <Check size={15}/>}</button>) : <div className="picker-empty">No matching conversations</div>}</div>}
  </div>
}
function ChatWorkspace({ selected, detail, conversations, select, newConversation, creating, sending, send, search, navigate, onRename, draftKey, notify, onBookingConfirmed }) {
  const [message, setMessage] = useState('')
  const [draft, setDraft] = useState('')
  const composerRef = useRef(null)
  useEffect(() => { setMessage(''); setDraft(''); setVoiceOpen(false); composerRef.current?.focus() }, [draftKey])
  const [voiceOpen, setVoiceOpen] = useState(false)
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [nameBusy, setNameBusy] = useState(false)
  const chatScroll = useRef(null)
  useEffect(() => {
    const panel = chatScroll.current
    if (panel) panel.scrollTo({ top: panel.scrollHeight, behavior: 'smooth' })
  }, [detail?.messages?.length, draft, sending])
  useEffect(() => { setEditingName(false); setNameDraft('') }, [selected?.id])
  async function saveName(e) {
    e.preventDefault()
    if (!selected?.id || nameBusy) return
    setNameBusy(true)
    try { const ok = await onRename(selected.id, nameDraft.trim()); if (ok) setEditingName(false) }
    finally { setNameBusy(false) }
  }
  const active = selected?.id
  const canSend = !sending && !creating
  const submit = async e => {
    e.preventDefault()
    const text = message.trim()
    if (!text || !canSend) return
    setMessage(''); setDraft(text)
    try { const reply = await send(text, active); if(!reply)setMessage(old=>old||text) } finally { setDraft('') }
  }
  return <section className="conversation-card">
    <div className="conversation-head"><div className="conv-person"><UserAvatar name={selected ? leadName(selected) : 'LP'}/><div><div className="person-title"><h2>{selected ? leadName(selected) : 'AI Sales Copilot'}</h2>{selected && <button className="icon-button rename-trigger" type="button" onClick={() => {setNameDraft(selected.display_name || '');setEditingName(v => !v)}} title="Edit lead display name" aria-label="Edit lead display name"><Pencil size={14}/></button>}{selected?.lead && <Badge variant={scoreVariant(selected.lead.category)} label={`${selected.lead.category} Lead`}/>}</div><p>{selected ? `CRM conversation ${selected.id.slice(0, 12)}...` : 'Your personal AI sales qualification workspace'}</p>{editingName && <form className="rename-form" onSubmit={saveName}><input autoFocus aria-label="Lead display name" maxLength={64} value={nameDraft} placeholder="Customer / company label" onChange={e=>setNameDraft(e.target.value)} disabled={nameBusy}/><button className="rename-save" disabled={nameBusy} type="submit">Save</button><button type="button" className="rename-cancel" onClick={()=>setEditingName(false)}>Cancel</button><small>Saved in local CRM. Leave blank to reset.</small></form>}</div></div><div className="conv-tools"><ConversationPicker selectedId={active} conversations={conversations} onSelect={select} search={search}/><button type="button" className="new-conversation-button" title="Open blank chat; it is saved on your first message" aria-label="New conversation" onClick={newConversation} disabled={creating || sending}>{creating ? <LoaderCircle size={16} className="spin"/> : <Plus size={17}/>}<span>New conversation</span></button><button className="icon-button" title="Schedule meeting" aria-label="Open appointments" onClick={() => navigate('appointments')}><CalendarDays size={19}/></button></div></div>
    <div className="conv-tabs"><span className="tab-active"><MessageCircle size={17}/> Conversation</span><span className="tab-secondary"><ShieldCheck size={16}/> CRM-backed</span><span className="tab-secondary"><Sparkles size={16}/> NVIDIA AI</span><button type="button" className={`voice-tab ${voiceOpen ? 'active' : ''}`} onClick={()=>setVoiceOpen(v=>!v)} aria-expanded={voiceOpen}><Mic2 size={16}/> {voiceOpen ? 'Hide voice demo' : 'Browser voice'}</button></div>
    <div className="chat-scroll" ref={chatScroll}><div className="chat-day">Conversation history</div>{!selected && !sending ? <Empty icon={Bot} title="Meet your AI sales copilot" message="Write your first message below. A CRM conversation is created only when you send it." action={()=>composerRef.current?.focus()} actionText="Write a message"/> : <>{!(detail?.messages?.length) && !draft && <div className="chat-intro"><div className="chat-intro-glow"><Sparkles size={25}/></div><h3>Your conversation is ready</h3><p>Send a customer statement. LeadPilot will reply, extract BANT signals and save the exchange in SQLite.</p><div className="prompt-samples"><button onClick={() => setMessage('I need a CRM to improve follow-up with our sales leads.')}>I need a sales CRM <ArrowUpRight size={14}/></button><button onClick={() => setMessage('We have a budget approved for a new sales tool.')}>We have an approved budget <ArrowUpRight size={14}/></button></div></div>}
      {detail?.messages?.map((row, index) => <div className={`chat-line ${row.role === 'user' ? 'from-user' : 'from-bot'}`} key={`${index}-${row.role}`}><UserAvatar name={row.role === 'user' ? 'Customer' : 'LeadPilot AI'} assistant={row.role !== 'user'}/><div className="chat-content"><div className="chat-sender">{row.role === 'user' ? 'Customer (demo)' : 'LeadPilot AI'}</div><div className="chat-bubble">{row.content}</div></div></div>)}
      {draft && <div className="chat-line from-user pending-message"><UserAvatar name="Customer"/><div className="chat-content"><div className="chat-sender">Customer (demo)</div><div className="chat-bubble">{draft}</div></div></div>}
      {sending && <div className="chat-line from-bot"><UserAvatar assistant/><div className="chat-content"><div className="chat-sender">LeadPilot AI</div><div className="chat-bubble typing-bubble"><span/><span/><span/> <small>Extracting BANT and composing a reply...</small></div></div></div>}
      </>}
      </div>
    {active && <CalendarBookingPicker isHot={detail?.lead?.category === "Hot" || selected?.lead?.category === "Hot"} conversationId={active} messageCount={detail?.messages?.length ?? 0} notify={notify} onConfirmed={onBookingConfirmed}/>}
    {voiceOpen && <VoiceReviewPanel resetKey={draftKey} activeId={active} busy={sending || creating} onVoiceTurn={(text,id)=>send(text,id,{rethrow:true})}/>}
    <form className="chat-compose" onSubmit={submit}><div className="composer-box"><Sparkles size={20} className="composer-spark"/><textarea rows="1" maxLength={2000} aria-label="Message to simulate a customer statement" placeholder={active ? 'Enter a customer statement for LeadPilot AI...' : 'Type your first message to start a conversation...'} disabled={sending || creating} ref={composerRef} value={message} onChange={e => setMessage(e.target.value)} onKeyDown={e => {if(e.key === 'Enter' && !e.shiftKey){e.preventDefault();submit(e)}}}/><span className="char-count">{message.length}/2000</span><button className="send-button" aria-label="Send message to LeadPilot AI" type="submit" disabled={!canSend || !message.trim()}>{sending ? <LoaderCircle className="spin" size={19}/> : <Send size={19}/>}</button></div><div className="composer-footer"><span><span className="dot-purple"/> AI qualification active</span><div><span>Quick actions:</span><button type="button" onClick={()=>setVoiceOpen(v=>!v)} disabled={sending || creating}><Mic2 size={15}/> {voiceOpen ? 'Hide voice' : 'Talk to AI'}</button><button type="button" onClick={() => navigate('appointments')} disabled={!active}><CalendarDays size={15}/> Book meeting</button><button type="button" onClick={() => navigate('leads')}><UsersRound size={15}/> View leads</button></div></div></form>
  </section>
}
function DashboardHome({ conversations, summary, navigate, select }) {
  return <div className="page-content dashboard-content"><div className="grid-panels"><section className="panel recent-panel"><div className="panel-header"><div><h2>Recent Conversations</h2><p>Latest interactions saved in your CRM</p></div><button className="text-button" onClick={() => navigate('conversations')}>View all <ArrowRight size={16}/></button></div>
    {conversations.length === 0 ? <Empty icon={MessageCircle} title="No conversations yet" message="Create your first AI sales conversation from the Conversations tab." action={() => navigate('conversations')} actionText="Open conversations"/> : <div className="recent-list">{conversations.slice(0, 6).map(c => <button className="recent-row" key={c.id} onClick={() => {select(c.id); navigate('conversations',{preserveConversation:true})}}><UserAvatar name={leadName(c)}/><div><strong>{leadName(c)}</strong><small>{c.last_message?.content || 'No messages yet'}</small></div><div className="recent-meta"><Badge label={c.lead?.category || 'New'} variant={scoreVariant(c.lead?.category)}/><small>{shortDate(c.updated_at)}</small></div></button>)}</div>}
  </section><section className="panel pipeline-panel"><div className="panel-header"><div><h2>Qualification Overview</h2><p>Actual lead counts from SQLite</p></div><span className="pipeline-icon"><Target size={20}/></span></div><div className="pipeline-body"><div className="pipeline-total">{summary.total_leads}<span>Lead profiles</span></div><div className="pipeline-track"><span style={{ width: summary.total_leads ? `${summary.hot_leads / summary.total_leads * 100}%` : '0%' }}/></div><div className="pipeline-rows"><div><span><span className="legend-dot violet"/> Hot leads</span><strong>{summary.hot_leads}</strong></div><div><span><span className="legend-dot green"/> Qualified leads</span><strong>{summary.qualified_leads}</strong></div><div><span><span className="legend-dot blue"/> CRM conversations</span><strong>{summary.total_conversations}</strong></div><div><span><span className="legend-dot orange"/> Booked appointments</span><strong>{summary.appointments_booked}</strong></div></div></div></section></div>
  <div className="dashboard-bottom"><div className="soft-feature"><span className="feature-icon"><Bot size={27}/></span><div><h3>Meet your NVIDIA-powered agent</h3><p>Practice a sales conversation, capture BANT fields and see the qualification score update in real time.</p><button className="primary-button" onClick={() => navigate('conversations')}><MessageCircle size={17}/> Open AI Workspace <ArrowRight size={16}/></button></div></div><div className="soft-feature lavender"><span className="feature-icon"><CalendarDays size={26}/></span><div><h3>Appointment workflows</h3><p>Explore available Google Calendar slots. Real bookings always require explicit confirmation.</p><button className="secondary-button" onClick={() => navigate('appointments')}>View appointments <ArrowRight size={16}/></button></div></div></div></div>
}
function LeadsPage({ conversations, search, select, navigate, newConversation }) {
  const filtered = conversations.filter(c => `${c.id} ${c.lead?.category || ''} ${c.last_message?.content || ''}`.toLowerCase().includes(search.toLowerCase()))
  return <section className="page-content"><div className="section-row"><div><h2 className="section-title">Lead Management</h2><p className="section-subtitle">Lead profiles and qualification from your local CRM</p></div><button className="primary-button" onClick={newConversation}><Plus size={17}/> New conversation</button></div><div className="table-card"><div className="table-heading"><span>Lead / Conversation</span><span>Latest activity</span><span>BANT progress</span><span>Score</span><span>Status</span><span></span></div>
    {filtered.length === 0 ? <Empty icon={UsersRound} title="No matching leads" message="Create or qualify a conversation to populate your CRM lead list." action={newConversation} actionText="Start a conversation"/> : filtered.map(c => {const captured=SCORE_FIELDS.filter(f => c.lead?.[f.key] && c.lead[f.key] !== 'unknown').length;return <button className="table-row" onClick={() => {select(c.id);navigate('conversations',{preserveConversation:true})}} key={c.id}><span className="name-cell"><UserAvatar name={leadName(c)}/><span><strong>{leadName(c)}</strong><small>{c.id.slice(0, 18)}...</small></span></span><span className="activity-cell">{c.last_message?.content || 'No messages yet'}</span><span className="progress-cell"><span className="mini-track"><i style={{width: `${captured*25}%`}}/></span><small>{captured}/4</small></span><strong className="score-cell">{c.lead?.score ?? '—'}</strong><span><Badge label={c.lead?.category || 'New'} variant={scoreVariant(c.lead?.category)}/></span><ArrowRight size={17} className="row-arrow"/></button>})}
  </div></section>
}
function AppointmentPage({ conversations, selected, select, appointments, refresh, notify, navigate }) {
  const [date, setDate] = useState(dayIST)
  const [slots, setSlots] = useState(null)
  const [busy, setBusy] = useState(false)
  const [chosen, setChosen] = useState(null)
  const [proposal, setProposal] = useState(null)
  const [confirming, setConfirming] = useState(false)
  const [localError, setLocalError] = useState('')
  const hotLeads = conversations.filter(c => c.lead?.category === 'Hot')
  const id = selected?.id
  async function checkSlots(e) {
    e?.preventDefault?.();setBusy(true);setLocalError('');setSlots(null);setProposal(null);setChosen(null)
    try { setSlots(await loadAvailable(date)) }
    catch (e) { setLocalError(e.message) }
    finally { setBusy(false) }
  }
  async function propose(start) {
    if (!id) return
    setBusy(true);setLocalError('');setChosen(start);setProposal(null)
    try {const p=await createProposal(id,start);setProposal(p);notify('Slot available. No booking has been created. Review and confirm explicitly.')}
    catch (e) {setLocalError(e.message)}
    finally {setBusy(false)}
  }
  async function confirm() {
    if (!id || !proposal?.proposal_id || !confirming) return
    setBusy(true);setLocalError('')
    try { const result=await confirmProposal(id,proposal.proposal_id); if(result.booking_created){notify('Google Calendar booking confirmed.');setProposal(null);setConfirming(false);refresh()} }
    catch (e) {setLocalError(e.message)}
    finally {setBusy(false)}
  }
  return <div className="page-content appointments-page"><div className="section-row"><div><h2 className="section-title">Appointments</h2><p className="section-subtitle">Check availability, propose a time, then explicitly confirm a booking.</p></div><Badge label="Asia/Kolkata · 30 minutes" variant="purple"/></div>
    <div className="appointment-layout"><section className="panel scheduler-panel"><div className="panel-header"><div><h2>Find a consultation slot</h2><p>Weekdays · 10:00 AM–6:00 PM IST</p></div><CalendarDays size={21} className="purple-icon"/></div><div className="form-grid"><label>Qualified lead<select value={id || ''} onChange={e => {select(e.target.value);setProposal(null);setChosen(null)}}><option value="">Select a Hot lead</option>{hotLeads.map(c=><option key={c.id} value={c.id}>{leadName(c)} — {c.lead?.score}/100</option>)}</select></label><label>Appointment date<input type="date" min={dayIST()} value={date} onChange={e=>{setDate(e.target.value);setSlots(null);setProposal(null)}}/></label></div><button className="secondary-button schedule-find" onClick={checkSlots} disabled={busy || !date}>{busy ? <LoaderCircle className="spin" size={17}/> : <Search size={17}/>} Check available slots</button>
      {localError && <div className="inline-alert"><Info size={18}/>{localError}</div>}
      {slots && <div className="slot-results"><div className="slot-results-head"><strong>Available slots</strong><span>{slots.available_count} found</span></div>{slots.available_slots.length ? <div className="slot-grid">{slots.available_slots.map(s => <button type="button" key={s.start} className={`slot-button ${chosen === s.start ? 'chosen' : ''}`} disabled={busy || !hotLeads.some(c=>c.id===id)} title={!id?'Select a Hot lead first':''} onClick={()=>propose(s.start)}>{formatSlot(s.start)}</button>)}</div> : <p className="subtle-copy">{slots.note || 'No openings on this date.'}</p>}</div>}
      {proposal && <div className="confirmation-card"><div className="confirmation-title"><CheckCircle2 size={21}/><div><strong>Time available — confirmation required</strong><p>No calendar event has been created yet.</p></div></div><p><strong>Selected:</strong> {formatSlot(proposal.start)}</p><p><strong>Proposal expires:</strong> {shortDate(proposal.expires_at)}</p><label className="confirmation-check"><input type="checkbox" checked={confirming} onChange={e=>setConfirming(e.target.checked)}/> <span>I understand this will create a real event on my connected Google Calendar.</span></label><button className="primary-button full-width" onClick={confirm} disabled={!confirming || busy}>{busy?<LoaderCircle className="spin" size={18}/>:<CalendarCheck2 size={18}/>} CONFIRM BOOKING</button></div>}
      <div className="schedule-note"><ShieldCheck size={17}/><span>Booking requires a Hot lead, calendar OAuth and an explicit final confirmation. No invitation email is sent automatically.</span></div></section>
      <section className="panel booked-panel"><div className="panel-header"><div><h2>Saved appointments</h2><p>Bookings recorded in SQLite</p><button type="button" className="sales-open-link" onClick={()=>navigate('sales')}>Manage meeting outcomes <ArrowRight size={14}/></button></div><Badge label={`${appointments.length} loaded`} variant="muted"/></div>{appointments.length===0?<Empty icon={CalendarCheck2} title="No appointments recorded" message="Confirmed Google Calendar events will appear here after being saved by the API."/>:<div className="booked-list">{appointments.map(a=><div key={a.request_id} className="booked-row"><div className="booked-date"><CalendarCheck2 size={19}/></div><div><strong>{formatSlot(a.start)}</strong><p>{shortId(a.conversation_id)} · 30 min</p></div><Badge label="Saved" variant="green"/></div>)}</div>}</section></div></div>
}
function CallsPage({ gateway, connected, copy }) {
  const configured = !!gateway?.configured
  return <div className="page-content"><div className="section-row"><div><h2 className="section-title">Voice Calls</h2><p className="section-subtitle">NVIDIA local audio workflows and secure Twilio gateway status.</p></div><Badge label="Local development" variant="purple"/></div><div className="calls-grid"><article className="panel voice-hero"><div className="voice-hero-icon"><Mic2 size={33}/></div><Badge label="Voice workspace" variant="purple"/><h2>Practice with your AI voice agent</h2><p>Run NVIDIA Parakeet → Nemotron → Magpie voice demos from a local Windows terminal. The microphone demos are not connected to a live Twilio phone call.</p><div className="terminal-snippet"><code>python test_two_way_voice.py</code><button aria-label="Copy voice demo command" onClick={()=>copy('python test_two_way_voice.py')}><Copy size={17}/></button></div><div className="terminal-snippet"><code>python test_voice_vad_crm.py</code><button aria-label="Copy CRM voice command" onClick={()=>copy('python test_voice_vad_crm.py')}><Copy size={17}/></button></div></article><article className="panel gateway-panel"><div className="panel-header"><div><h2>Twilio gateway</h2><p>Port 8002 · isolated webhook service</p></div><Headphones className="purple-icon" size={23}/></div><div className="gateway-status"><Badge label={gateway ? 'Gateway reachable' : 'Gateway offline'} variant={gateway ? 'green' : 'muted'} dot/><Badge label={configured ? 'Credentials configured' : 'Credentials not configured'} variant={configured?'purple':'muted'}/></div><div className="status-row"><span>Signed webhook validation</span><CheckCircle2 size={19}/></div><div className="status-row"><span>AI-connected real telephone calls</span><Badge label="Not enabled" variant="muted"/></div><div className="status-row"><span>Private CRM API</span><Badge label={connected?'Connected':'Offline'} variant={connected?'green':'muted'}/></div><div className="call-warning"><PhoneOff size={19}/><span>Do not advertise live Twilio + NVIDIA calls as deployed: the default /twilio/voice endpoint returns a safe greeting and hangs up.</span></div></article></div></div>
}
function SettingsPage({ connected, gateway, refresh }) {
  return <div className="page-content"><div className="section-row"><div><h2 className="section-title">Workspace Settings</h2><p className="section-subtitle">Local API connectivity, privacy and deployment readiness.</p></div><button className="secondary-button" onClick={refresh}><RefreshCcw size={16}/> Refresh checks</button></div><div className="settings-grid"><article className="panel settings-card"><div className="setting-icon"><Database size={24}/></div><h3>Main CRM API</h3><Badge label={connected?'Connected':'Not responding'} variant={connected?'green':'muted'} dot/><p>The frontend proxy uses FastAPI on <code>127.0.0.1:8001</code>.</p></article><article className="panel settings-card"><div className="setting-icon"><Headphones size={24}/></div><h3>Twilio gateway</h3><Badge label={gateway?'Reachable':'Offline / not started'} variant={gateway?'green':'muted'} dot/><p>Optional isolated gateway on <code>127.0.0.1:8002</code>.</p></article><article className="panel settings-card"><div className="setting-icon"><LockKeyhole size={24}/></div><h3>Deployment security</h3><Badge label="Local only" variant="purple"/><p>CRM APIs currently lack public-user authentication. Keep both services bound to 127.0.0.1.</p></article></div><div className="settings-help"><ShieldCheck size={20}/><div><strong>Built for safe local demonstrations</strong><p>Conversations and lead scores are read from SQLite. No example customer data is fabricated, and real calendar writes require a second confirmation step. Add authentication before public hosting.</p></div></div></div>
}
export default function App({ currentUser, onSignOut, onTeamOpen, signOutBusy = false, signOutError = "" }) {
  const [page, setPage] = useState('conversations')
  const [leftOpen, setLeftOpen] = useState(()=>persisted('leadpilot:left-open',true))
  const [rightOpen, setRightOpen] = useState(()=>persisted('leadpilot:right-open',true))
  const [mobileLeft, setMobileLeft] = useState(false)
  const [mobileRight, setMobileRight] = useState(false)
  const [search, setSearch] = useState('')
  const [summary, setSummary] = useState(DEFAULT_SUMMARY)
  const [conversations, setConversations] = useState([])
  const [appointments, setAppointments] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const selectedIdRef = useRef(null)
  const sendingRef = useRef(false)
  const [draftKey, setDraftKey] = useState(0)
  const [detail, setDetail] = useState(null)
  const [connected, setConnected] = useState(false)
  const [gateway, setGateway] = useState(null)
  const [busy, setBusy] = useState(false)
  const [creating, setCreating] = useState(false)
  const creatingRef = useRef(false)
  const [sending, setSending] = useState(false)
  const [toast, setToast] = useState('')
  const searchRef = useRef(null)
  const init = useRef(false)
  const selected = useMemo(()=>conversations.find(c => c.id === selectedId) || null,[conversations,selectedId])
  const notify = text => setToast(text)
  const filtered = useMemo(()=>conversations.filter(c=>`${leadName(c)} ${c.id} ${c.lead?.category || ''} ${c.last_message?.content || ''}`.toLowerCase().includes(search.toLowerCase())),[conversations,search])

  useEffect(()=>{localStorage.setItem('leadpilot:left-open',JSON.stringify(leftOpen))},[leftOpen])
  useEffect(()=>{localStorage.setItem('leadpilot:right-open',JSON.stringify(rightOpen))},[rightOpen])
  useEffect(()=>{const key=e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();searchRef.current?.focus()}if(e.key==='Escape'){setMobileLeft(false);setMobileRight(false)}};window.addEventListener('keydown',key);return ()=>window.removeEventListener('keydown',key)},[])
  async function refresh({silent=false}={}) {
    if(!silent)setBusy(true)
    const results = await Promise.allSettled([loadSummary(),loadConversations(),loadAppointments(),api('/health'),loadGatewayHealth()])
    if(results[0].status==='fulfilled')setSummary(results[0].value)
    if(results[1].status==='fulfilled'){
      const next=results[1].value.conversations || []
      setConversations(next)
      setSelectedId(old => old && next.some(c=>c.id===old) ? old : null)
    }
    if(results[2].status==='fulfilled')setAppointments(results[2].value.appointments || [])
    setConnected(results[3].status==='fulfilled')
    setGateway(results[4].status==='fulfilled'?results[4].value:null)
    if(results[3].status==='rejected' && !silent)notify('Main API unavailable. Start LeadPilot FastAPI on port 8001.')
    setBusy(false)
  }
  useEffect(()=>{if(!init.current){init.current=true;void refresh({silent:true})}},[])
  useEffect(()=>{let ignore=false;if(!selectedId){setDetail(null);return}
    loadConversation(selectedId).then(v=>{if(!ignore)setDetail(v)}).catch(()=>{if(!ignore)setDetail(null)})
    return()=>{ignore=true}
  },[selectedId])
  function select(id){selectedIdRef.current=id;setSelectedId(id);setDetail(null);setMobileRight(false);setDraftKey(x=>x+1)}
  // ChatGPT-style draft: no database row until the first submitted message.
  function newConversation(){
    if (sendingRef.current || creatingRef.current){notify('Wait for the current AI response before starting a new chat.');return}
    selectedIdRef.current=null
    setSelectedId(null)
    setDetail(null)
    setPage('conversations')
    setSearch('')
    setDraftKey(key=>key+1)
  }
  async function send(text,id,{rethrow=false}={}){
    if(sendingRef.current){
      const error=new Error('An AI response is already in progress.')
      if(rethrow)throw error
      notify(error.message)
      return null
    }
    sendingRef.current=true
    setSending(true)
    let targetId=id || selectedIdRef.current
    try{
      if(!targetId){
        creatingRef.current=true
        setCreating(true)
        const created=await startConversation()
        if(!created?.conversation_id)throw new Error('CRM returned no conversation ID')
        targetId=created.conversation_id
        selectedIdRef.current=targetId
        setSelectedId(targetId)
        setDetail({conversation_id:targetId,messages:[],lead:null})
      }
      const result=await sendChat(targetId,text)
      const updated=await loadConversation(targetId)
      if(selectedIdRef.current===targetId)setDetail(updated)
      await refresh({silent:true})
      return result?.reply || null
    }catch(e){
      notify(`AI request failed: ${e.message}`)
      if(targetId){
        try{
          const updated=await loadConversation(targetId)
          if(selectedIdRef.current===targetId)setDetail(updated)
        }catch{}
        await refresh({silent:true}).catch(()=>{})
      }
      if(rethrow)throw e
      return null
    }finally{
      creatingRef.current=false
      setCreating(false)
      sendingRef.current=false
      setSending(false)
    }
  }
  async function renameConversation(id, name){
    try {await saveLeadLabel(id,name);await refresh({silent:true});notify(name ? 'Lead display name saved in CRM.' : 'Display name cleared.');return true}
    catch(e){notify(`Could not save lead name: ${e.message}`);return false}
  }
  async function copy(str){try{await navigator.clipboard.writeText(str);notify('Command copied to clipboard.')}catch{notify('Copy not available. Select the command manually.')}}
  function navigate(next, {preserveConversation=false}={}){if(next==='conversations'&&!preserveConversation){void newConversation();return}setPage(next);setSearch('')}
  function onRightToggle(){if(window.innerWidth<=1100){setMobileRight(v=>!v);setRightOpen(true)}else{setRightOpen(v=>!v)}}
  const metricCards = [
    {label:'Total Leads',value:summary.total_leads,icon:UsersRound,tone:'violet'},
    {label:'Hot Leads',value:summary.hot_leads,icon:Flame,tone:'coral'},
    {label:'Qualified',value:summary.qualified_leads,icon:Target,tone:'blue'},
    {label:'Meetings Booked',value:summary.appointments_booked,icon:CalendarDays,tone:'violet'}
  ]
  return <div className={`app-shell ${leftOpen?'':'left-collapsed'} ${rightOpen?'':'right-collapsed'}`}>
    {(mobileLeft||mobileRight)&&<button className="mobile-scrim" aria-label="Close sidebar" onClick={()=>{setMobileLeft(false);setMobileRight(false)}}/>}
    <aside className={`left-sidebar ${mobileLeft?'mobile-visible':''}`}><LeftNav collapsed={!leftOpen} toggle={()=>setLeftOpen(v=>!v)} onMobileClose={()=>setMobileLeft(false)} navigate={navigate} page={page}/></aside>
    <div className="app-main"><TopBar search={search} setSearch={setSearch} searchRef={searchRef} onMenu={()=>setMobileLeft(true)} onToggleRight={onRightToggle} rightOpen={rightOpen} connected={connected} refresh={()=>refresh()} busy={busy} currentUser={currentUser} onSignOut={onSignOut} signOutBusy={signOutBusy} signOutError={signOutError} onTeamOpen={onTeamOpen}/>
      <main className={`main-inner ${page === 'conversations' ? 'conversation-view' : ''}`}>{page!=='conversations' && <div className="page-header"><div className="page-heading"><div className="heading-icon"><Sparkles size={23}/></div><div><h1>{page==='conversations'?'AI Copilot Workspace':MENU.find(m=>m.id===page)?.name}</h1><p>{page==='conversations'?'Live qualification, customer conversations and next best actions — powered by AI.':page==='dashboard'?'Your sales agent and CRM overview':page==='leads'?'Every qualified opportunity in one place':page==='calls'?'Voice agent development and call readiness':page==='appointments'?'Choose a consultation time with real calendar availability':page==='sales'?'Record meetings, follow-ups and sales outcomes':'Local configuration and connection status'}</p></div></div><Badge label={connected?'AI Copilot Ready':'Connect FastAPI'} variant={connected?'green':'muted'} dot/></div>}
      {page==='dashboard'&&<div className="kpi-grid">{metricCards.map(x=><Kpi key={x.label} {...x}/>)}</div>}
      {page==='conversations'&&<ChatWorkspace selected={selected} detail={detail} conversations={filtered} select={select} newConversation={newConversation} creating={creating} sending={sending} draftKey={draftKey} send={send} search={search} navigate={navigate} onRename={renameConversation} notify={notify} onBookingConfirmed={()=>refresh({silent:true})}/>}
      {page==='dashboard'&&<DashboardHome conversations={filtered} summary={summary} navigate={navigate} select={select}/>}
      {page==='leads'&&<LeadsPage conversations={filtered} search="" select={select} navigate={navigate} newConversation={newConversation}/>}
      {page==='appointments'&&<AppointmentPage conversations={conversations} selected={selected} select={select} appointments={appointments} refresh={()=>refresh({silent:true})} notify={notify} navigate={navigate}/>}
      {page==='sales'&&<SalesPipelineErrorBoundary><SalesPipelinePage notify={notify} onOpenConversation={id=>{select(id);navigate('conversations',{preserveConversation:true})}}/></SalesPipelineErrorBoundary>}
      {page==='calls'&&<CallsPage gateway={gateway} connected={connected} copy={copy}/>}
      {page==='settings'&&<SettingsPage connected={connected} gateway={gateway} refresh={()=>refresh()}/>}
      </main>
    </div>
    {rightOpen && <aside className={`right-sidebar ${mobileRight?'mobile-visible':''}`}><Insights selected={selected} selectedDetail={detail} appointments={appointments} goSchedule={()=>{navigate('appointments');setMobileRight(false)}} close={()=>{setRightOpen(false);setMobileRight(false)}} loading={sending}/></aside>}
    <FollowUpObserver navigate={navigate}/>
    <Toast message={toast} onDismiss={()=>setToast('')}/>
  </div>
}
