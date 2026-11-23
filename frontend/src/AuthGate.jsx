import { useCallback, useEffect, useState } from 'react'
import { Eye, EyeOff, LockKeyhole, LogOut, ShieldCheck, Sparkles, UserRound } from 'lucide-react'
import App from './App.jsx'
import TeamAdminPanel from './TeamAdminPanel.jsx'
import TeamSalesWorkspace from './TeamSalesWorkspace.jsx'
import './auth.css'
import './account-menu.css'

async function request(path, data) {
  const res = await fetch(path, {
    method: data ? 'POST' : 'GET',
    credentials: 'same-origin',
    headers: data ? { 'Content-Type': 'application/json' } : {},
    body: data ? JSON.stringify(data) : undefined,
    cache: 'no-store',
  })
  const json = await res.json().catch(() => ({}))
  if (!res.ok) throw Object.assign(new Error(json.detail || `Request failed (${res.status})`), { status: res.status })
  return json
}

export default function AuthGate() {
  const [status, setStatus] = useState('checking')
  const [user, setUser] = useState(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const [epoch, setEpoch] = useState(0)
  const [teamOpen, setTeamOpen] = useState(false)
  const checkSession = useCallback(async () => {
    try {
      const me = await request('/api/auth/me')
      setUser(me.user)
      setStatus('signed-in')
    } catch (err) {
      if (err.status === 401) {
        setUser(null)
        try {
          const setup = await request('/api/auth/setup-status')
          setStatus(setup.setup_complete ? 'login' : 'setup')
        } catch { setStatus('unavailable') }
      } else {
        setStatus('unavailable')
      }
    }
  }, [])
  useEffect(() => { void checkSession() }, [checkSession])
  useEffect(() => {
    if (status !== 'signed-in') return undefined
    const timer = window.setInterval(() => void checkSession(), 45000)
    const onVisible = () => { if (document.visibilityState === 'visible') void checkSession() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', onVisible) }
  }, [checkSession, status])
  async function login(event) {
    event.preventDefault()
    if (working) return
    setWorking(true); setError('')
    try {
      const result = await request('/api/auth/login', { username, password })
      setPassword(''); setUser(result.user); setEpoch(n => n + 1); setStatus('signed-in')
    } catch (err) {
      setError(err.message)
    } finally { setWorking(false) }
  }
  async function logout() {
    if (working) return
    setWorking(true); setError('')
    try {
      await request('/api/auth/logout', {})
      setUser(null); setPassword(''); setEpoch(n => n + 1); setStatus('login')
    } catch (err) { setError(`Logout failed: ${err.message}`) }
    finally { setWorking(false) }
  }
  if (status === 'signed-in' && user) return user.role === 'sales'
    ? <TeamSalesWorkspace key={`sales-${epoch}`} currentUser={user} onSignOut={logout}/>
    : <>
        <App key={`signed-in-${epoch}`} currentUser={user} onSignOut={logout} onTeamOpen={() => setTeamOpen(true)} signOutBusy={working} signOutError={error}/>
        {teamOpen && <TeamAdminPanel onClose={() => setTeamOpen(false)}/>}
      </>
  return <main className="lp-auth-page">
    <section className="lp-auth-card" aria-label="LeadPilot AI login">
      <div className="lp-auth-logo"><Sparkles size={25}/></div>
      <h1>LeadPilot <strong>AI</strong></h1>
      <p className="lp-auth-caption">Protected sales copilot workspace</p>
      {status === 'checking' && <p role="status">Checking operator session...</p>}
      {status === 'unavailable' && <div className="lp-auth-alert"><p>FastAPI is unavailable. Start the backend on port 8001.</p><button type="button" onClick={checkSession}>Retry connection</button></div>}
      {status === 'setup' && <div className="lp-auth-alert">
        <h2>One-time administrator setup</h2>
        <p>Create an operator on your local PC, using the terminal command below. There is no public self-registration.</p>
        <code>python scripts/create_leadpilot_admin.py</code>
        <button type="button" onClick={checkSession}>I've created the account · Refresh</button>
      </div>}
      {status === 'login' && <form onSubmit={login} className="lp-auth-form">
        <h2>Sign in to your workspace</h2>
        <label htmlFor="lp-auth-username">Username</label>
        <input id="lp-auth-username" value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" minLength={3} maxLength={50} required placeholder="operator" autoFocus />
        <label htmlFor="lp-auth-password">Password</label>
        <div className="lp-auth-password"><input id="lp-auth-password" type={showPassword ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" required placeholder="Your password"/><button type="button" onClick={() => setShowPassword(v => !v)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div>
        {error && <div className="lp-auth-error" role="alert">{error}</div>}
        <button type="submit" className="lp-auth-submit" disabled={working}><LockKeyhole size={17}/>{working ? 'Signing in...' : 'Sign in'}</button>
      </form>}
      <div className="lp-auth-foot"><ShieldCheck size={17}/> Shared local CRM · Authorized operators only</div>
    </section>
  </main>
}
