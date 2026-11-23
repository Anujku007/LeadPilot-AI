export const SCORE_FIELDS = [
  { key: 'budget', letter: 'B', label: 'Budget', icon: 'wallet' },
  { key: 'authority', letter: 'A', label: 'Authority', icon: 'award' },
  { key: 'need', letter: 'N', label: 'Need', icon: 'target' },
  { key: 'timeline', letter: 'T', label: 'Timeline', icon: 'clock' },
]

export const LABELS = {
  confirmed: 'Approved budget', limited: 'Limited budget',
  decision_maker: 'Decision maker', influencer: 'Influencer',
  clear: 'Clear business need', partial: 'Partially defined',
  within_30_days: 'Within 30 days', within_90_days: 'Within 90 days', later: 'Later',
  unknown: 'Not yet captured'
}
export const nextQuestion = {
  budget: 'Do you have an allocated budget?',
  authority: 'Who makes the purchasing decision?',
  need: 'What problem do you want to solve?',
  timeline: 'When are you planning to implement a solution?'
}
export function scoreLabel(lead) { return lead?.category || 'Unqualified' }
export function shortId(id) { return id ? `Lead ${id.slice(0, 8)}` : 'New lead' }
export function leadName(c) {
  // The CRM stores conversation IDs, not customer identity. Avoid fabricating names.
  return c?.display_name || shortId(c?.id || c?.conversation_id)
}
export function shortDate(value) {
  if (!value) return '—'
  const dt = new Date(value)
  return Number.isNaN(dt.getTime()) ? '—' : new Intl.DateTimeFormat('en-IN', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata'
  }).format(dt)
}
export function timeOf(value) {
  if (!value) return ''
  const dt = new Date(value)
  return Number.isNaN(dt.getTime()) ? '' : new Intl.DateTimeFormat('en-IN', {
    hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata'
  }).format(dt)
}
export function dayIST() {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
  const get = t => parts.find(p => p.type === t)?.value
  return `${get('year')}-${get('month')}-${get('day')}`
}
export function formatSlot(value) {
  if (!value) return ''
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', hour12: true }).format(dt) + ' IST'
}
export function getInitials(value) { return (value || 'LP').split(/\s+/).slice(0, 2).map(s => s[0]).join('').toUpperCase() }
