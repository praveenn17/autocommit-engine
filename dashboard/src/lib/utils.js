import { format, formatDistanceToNow, parseISO, isToday, isYesterday } from 'date-fns'

// IST timezone offset in milliseconds
const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000

// ---------------------------------------------------------------------------
// Date formatting utilities
// ---------------------------------------------------------------------------

export function formatDateIST(dateStr) {
  if (!dateStr) return '—'
  try {
    const d = parseISO(dateStr)
    return format(d, 'MMM dd')
  } catch {
    return dateStr
  }
}

export function formatTimeIST(timeStr) {
  // timeStr is HH:MM:SS
  if (!timeStr) return '—'
  return timeStr
}

export function formatDateDisplay(dateStr) {
  if (!dateStr) return '—'
  try {
    const d = parseISO(dateStr)
    if (isToday(d)) return 'Today'
    if (isYesterday(d)) return 'Yesterday'
    return format(d, 'MMM dd')
  } catch {
    return dateStr
  }
}

export function formatRelative(dateStr) {
  if (!dateStr) return '—'
  try {
    return formatDistanceToNow(parseISO(dateStr), { addSuffix: true })
  } catch {
    return dateStr
  }
}

export function nowIST() {
  const now = new Date()
  const utc = now.getTime() + now.getTimezoneOffset() * 60000
  return new Date(utc + IST_OFFSET_MS)
}

export function todayISOString() {
  return nowIST().toISOString().split('T')[0]
}

export function getLastNDays(n) {
  const days = []
  const today = nowIST()
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    days.push(d.toISOString().split('T')[0])
  }
  return days
}

// ---------------------------------------------------------------------------
// Streak calculation from commit history
// ---------------------------------------------------------------------------

export function calculateCurrentStreak(commitHistory) {
  let streak = 0
  const today = todayISOString()
  const d = new Date(nowIST())

  while (true) {
    const dateStr = d.toISOString().split('T')[0]
    const msgs = commitHistory[dateStr]
    const hasCommit = Array.isArray(msgs) && msgs.length > 0

    // Today counts if we expect commits (can be 0 so far)
    if (dateStr === today && !hasCommit) {
      d.setDate(d.getDate() - 1)
      continue
    }

    if (!hasCommit) break
    streak++
    d.setDate(d.getDate() - 1)
  }
  return streak
}

// ---------------------------------------------------------------------------
// Commit history helpers
// ---------------------------------------------------------------------------

export function getCommitMode(count) {
  if (count === 0) return 'Rest'
  if (count === 1) return 'Quiet'
  if (count <= 3)  return 'Normal'
  return 'Burst'
}

export function getModeColor(mode) {
  switch (mode) {
    case 'Burst':  return 'text-attention-fg bg-attention-muted'
    case 'Normal': return 'text-accent-fg bg-accent-muted'
    case 'Quiet':  return 'text-fg-muted bg-border-muted'
    case 'Rest':   return 'text-fg-subtle bg-canvas-subtle'
    default:       return 'text-fg-muted'
  }
}

export function getStatusColor(status) {
  switch (status?.toLowerCase()) {
    case 'pushed':  return 'text-success-fg'
    case 'failed':  return 'text-danger-fg'
    case 'skipped': return 'text-fg-subtle'
    default:        return 'text-fg-muted'
  }
}

// ---------------------------------------------------------------------------
// Build flat commit log from history object
// ---------------------------------------------------------------------------

export function buildCommitLog(commitHistory, commitPlan = null, limit = 30) {
  const entries = []

  Object.entries(commitHistory)
    .sort(([a], [b]) => b.localeCompare(a))
    .forEach(([date, msgs]) => {
      if (!Array.isArray(msgs) || msgs.length === 0) {
        entries.push({ date, time: null, message: '— Rest Day —', mode: 'Rest', status: 'Skipped' })
      } else {
        msgs.forEach((msg, i) => {
          const isObj = typeof msg === 'object' && msg !== null;
          const messageText = isObj ? msg.message : msg;
          let time = isObj ? msg.time : null;
          let mode = (isObj && msg.mode) ? msg.mode : getCommitMode(msgs.length);

          // Fallback: look up time in commit_plan.json if missing
          if (!time && commitPlan && commitPlan.date === date && Array.isArray(commitPlan.commits)) {
            const planCommit = commitPlan.commits.find(c => c.message === messageText);
            if (planCommit && planCommit.time) {
              time = planCommit.time;
            }
          }

          entries.push({
            date,
            time: time,
            message: messageText,
            mode: mode,
            status: 'Pushed',
          })
        })
      }
    })

  return entries.slice(0, limit)
}

// ---------------------------------------------------------------------------
// Quality score helpers
// ---------------------------------------------------------------------------

export function getQualityStatus(score) {
  if (score >= 75) return { label: 'Safe', color: 'text-success-fg', bg: 'bg-success-muted' }
  if (score >= 60) return { label: 'Warning', color: 'text-attention-fg', bg: 'bg-attention-muted' }
  return { label: 'Danger', color: 'text-danger-fg', bg: 'bg-danger-muted' }
}

export function getScoreGradient(score) {
  if (score >= 75) return 'from-success-l2 to-success-l4'
  if (score >= 60) return 'from-amber-800 to-amber-500'
  return 'from-red-900 to-red-500'
}

// ---------------------------------------------------------------------------
// Local storage helpers (persist PAT + settings locally)
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'autocommit_settings'

export function saveSettings(settings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch {}
}

export function loadSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function clearSettings() {
  localStorage.removeItem(STORAGE_KEY)
}

// ---------------------------------------------------------------------------
// Number formatting
// ---------------------------------------------------------------------------

export function formatNumber(n) {
  if (n === null || n === undefined) return '—'
  return new Intl.NumberFormat().format(n)
}

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}
