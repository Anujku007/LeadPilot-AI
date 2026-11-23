import { useCallback, useEffect, useState } from 'react'
import { Users, X, UserPlus, RefreshCw, ShieldCheck, KeyRound } from 'lucide-react'
import { api } from './api.js'
import './team-workspace.css'

export default function TeamAdminPanel({ onClose }) {
  const [users, setUsers] = useState([])
  const [leads, setLeads] = useState([])
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [reset, setReset] = useState({ id: '', password: '' })
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const refresh = useCallback(async () => {
    const [a,b] = await Promise.all([api('/api/team/operators'),api('/api/team/leads')])
    setUsers(a.operators || []);setLeads(b.leads || [])
  }, [])
  useEffect(() => { refresh().catch(e=>setError(e.message)) },[refresh])
  async function action(fn, success) {
    setBusy(true);setError('');setMessage('')
    try { await fn();await refresh();setMessage(success) } catch (e) { setError(e.message) } finally {setBusy(false)}
  }
  async function create(e) {
    e.preventDefault()
    await action(() => api('/api/team/operators',{method:'POST', data:{username,password}}), 'Sales account created. Share credentials securely outside this app.')
    setPassword('')
  }
  return <div className="lp-team-overlay" role="dialog" aria-modal="true" aria-label="Team and lead assignments">
    <div className="lp-team-modal">
      <header className="lp-team-top"><div><h2><Users size={22}/> Team & lead access</h2><p>Create sales operators and assign existing CRM conversations. Admin retains all records.</p></div><button className="lp-team-icon" aria-label="Close team management" onClick={onClose}><X/></button></header>
      {error && <p className="lp-team-error" role="alert">{error}</p>}
      {message && <p className="lp-team-success" role="status">{message}</p>}
      <div className="lp-team-columns">
        <section><h3><UserPlus size={19}/> Create salesperson</h3><form className="lp-team-form" onSubmit={create}>
          <label>Username<input value={username} onChange={e=>setUsername(e.target.value)} pattern="[A-Za-z][A-Za-z0-9_.-]{2,49}" required placeholder="sales01" autoComplete="off"/></label>
          <label>Temporary password (12+ characters)<input value={password} type="password" onChange={e=>setPassword(e.target.value)} minLength={12} maxLength={128} required autoComplete="new-password"/></label>
          <button className="lp-team-primary" disabled={busy}>Create sales account</button>
        </form>
        <h3>Operators</h3><div className="lp-team-list">{users.map(u=><div className="lp-team-user" key={u.id}><div><strong>{u.username}</strong><small>{u.role} · {u.assigned_leads} assigned · {u.active?'Active':'Disabled'}</small></div>{u.role==='sales'&&<button disabled={busy} onClick={()=>action(()=>api(`/api/team/operators/${u.id}/active`,{method:'PATCH',data:{active:!u.active}}),u.active?'Account disabled and sessions revoked':'Account enabled')}>{u.active?'Disable':'Enable'}</button>}</div>)}</div>
        <h3><KeyRound size={18}/> Reset salesperson password</h3><form className="lp-team-form" onSubmit={e=>{e.preventDefault();action(()=>api(`/api/team/operators/${reset.id}/reset-password`,{method:'POST',data:{new_password:reset.password}}),'Password reset; previous sessions revoked.');setReset({id:'',password:''})}}>
          <select required value={reset.id} onChange={e=>setReset(v=>({...v,id:e.target.value}))}><option value="">Choose salesperson</option>{users.filter(u=>u.role==='sales').map(u=><option key={u.id} value={u.id}>{u.username}</option>)}</select>
          <input type="password" required minLength={12} maxLength={128} placeholder="New password (12+ characters)" value={reset.password} onChange={e=>setReset(v=>({...v,password:e.target.value}))}/>
          <button disabled={busy}>Reset password</button>
        </form></section>
        <section><div className="lp-team-heading"><h3><ShieldCheck size={19}/> Assign CRM leads</h3><button onClick={()=>refresh().catch(e=>setError(e.message))} disabled={busy} aria-label="Refresh team lists"><RefreshCw size={17}/></button></div>
          <p className="lp-team-hint">Sales staff see only assigned leads. Unassigned leads stay admin-only. Existing conversation messages are not changed.</p>
          <div className="lp-team-leads">{leads.map(l=><div key={l.id} className="lp-team-lead"><div><strong>Lead {l.id.slice(0,8)}</strong><small>{l.category} · Score {l.score ?? '—'} · {l.id}</small></div><select value={l.assigned_to||''} disabled={busy} aria-label={`Assign lead ${l.id}`} onChange={e=>action(()=>api(`/api/team/leads/${l.id}/assign`,{method:'PUT',data:{user_id:e.target.value||null}}),'Lead assignment saved')}><option value="">Unassigned (admin only)</option>{users.filter(u=>u.role==='sales'&&u.active).map(u=><option key={u.id} value={u.id}>{u.username}</option>)}</select></div>)}{leads.length===0&&<p>No CRM leads yet.</p>}</div>
        </section>
      </div>
    </div>
  </div>
}
