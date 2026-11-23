import { useEffect, useRef, useState } from 'react'
import { BellRing, ArrowRight, X } from 'lucide-react'
import { loadSalesOverview } from './api.js'
import './sales-insights.css'

// Mounted across the workspace. Checks local CRM every minute, and when a tab
// becomes visible. No service worker or external notification is installed.
export default function FollowUpObserver({ navigate }) {
  const [due, setDue] = useState([])
  const [visible, setVisible] = useState(true)
  const delivered = useRef(new Set())
  useEffect(() => {
    let live = true
    async function check() {
      try {
        const overview = await loadSalesOverview()
        if (!live) return
        const records = overview?.reminders?.due || []
        setDue(records)
        if (typeof Notification === 'undefined' || Notification.permission !== 'granted'
          || localStorage.getItem('leadpilot_followup_desktop') !== 'on') return
        for (const record of records) {
          const key = `${record.conversation_id}:${record.follow_up_at}`
          if (delivered.current.has(key)) continue
          delivered.current.add(key)
          try { new Notification('LeadPilot AI · Follow-up due', {
            body: `${record.display_name} · ${new Date(record.follow_up_at).toLocaleString('en-IN')}`,
            tag: `leadpilot-${record.conversation_id}`,
          }) } catch { /* Browser notifications can be unavailable despite permission. */ }
        }
      } catch { /* A transient offline API must not crash or blank the workspace. */ }
    }
    const onVisible = () => { if (document.visibilityState === 'visible') void check() }
    void check()
    const timer = window.setInterval(() => { void check() }, 60000)
    document.addEventListener('visibilitychange', onVisible)
    return () => { live = false; clearInterval(timer); document.removeEventListener('visibilitychange', onVisible) }
  }, [])
  if (!due.length || !visible) return null
  return <aside role="status" className="followup-floating-notice" aria-live="polite">
    <BellRing size={17}/>
    <span><strong>{due.length} follow-up{due.length === 1 ? '' : 's'} due</strong><small>Review the sales pipeline</small></span>
    <button type="button" className="followup-floating-action" onClick={() => navigate('sales')}>Open <ArrowRight size={14}/></button>
    <button type="button" aria-label="Dismiss in-app follow-up reminder for this session" onClick={() => setVisible(false)}><X size={15}/></button>
  </aside>
}
