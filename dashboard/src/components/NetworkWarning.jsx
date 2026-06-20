import React, { useState, useEffect, useCallback } from 'react'
import { Wifi, WifiOff, X } from 'lucide-react'

// ---------------------------------------------------------------------------
// IST helpers
// ---------------------------------------------------------------------------
function nowIST() {
  const now = new Date()
  const utc = now.getTime() + now.getTimezoneOffset() * 60000
  return new Date(utc + 5.5 * 60 * 60 * 1000)
}

function formatCountdown(ms) {
  if (ms <= 0) return 'Expiring…'
  const h = Math.floor(ms / 3600000)
  const m = Math.floor((ms % 3600000) / 60000)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function formatDate(isoStr) {
  try {
    const d = new Date(isoStr)
    return d.toLocaleDateString('en-IN', { month: 'long', day: 'numeric' })
  } catch {
    return isoStr
  }
}

// ---------------------------------------------------------------------------
// NetworkWarning component
// ---------------------------------------------------------------------------
export default function NetworkWarning({ streakStats, loading }) {
  const [activeMiss, setActiveMiss]       = useState(null)
  const [countdown,  setCountdown]        = useState('')
  const [dismissed,  setDismissed]        = useState(false)

  // Find the most recent non-expired network miss
  const findActiveMiss = useCallback(() => {
    if (!streakStats || loading) return null
    const misses = streakStats.network_misses
    if (!Array.isArray(misses) || misses.length === 0) return null

    const now = nowIST().getTime()
    // Walk in reverse (most recent first)
    for (let i = misses.length - 1; i >= 0; i--) {
      const miss = misses[i]
      try {
        const expires = new Date(miss.warning_expires).getTime()
        if (expires > now) return miss
      } catch {
        continue
      }
    }
    return null
  }, [streakStats, loading])

  // Re-evaluate whenever streakStats changes
  useEffect(() => {
    setDismissed(false) // Reset dismiss state when data refreshes
    const miss = findActiveMiss()
    setActiveMiss(miss)
  }, [findActiveMiss])

  // Countdown ticker (every minute)
  useEffect(() => {
    if (!activeMiss) return

    const tick = () => {
      try {
        const expires = new Date(activeMiss.warning_expires).getTime()
        const now     = nowIST().getTime()
        const ms      = expires - now
        if (ms <= 0) {
          setActiveMiss(null) // Auto-dismiss when expired
          return
        }
        setCountdown(formatCountdown(ms))
      } catch {
        setActiveMiss(null)
      }
    }

    tick() // Immediate first tick
    const interval = setInterval(tick, 60_000) // Update every minute
    return () => clearInterval(interval)
  }, [activeMiss])

  // Nothing to show
  if (!activeMiss || dismissed) return null

  const missDate   = formatDate(activeMiss.date)
  const attempts   = activeMiss.attempts ?? 4

  return (
    <div
      role="alert"
      aria-live="polite"
      className="flex-shrink-0 flex items-center gap-3 px-5 py-3 border-b"
      style={{
        background:   'rgba(158, 110, 0, 0.12)',
        borderColor:  'rgba(210, 153, 34, 0.30)',
      }}
    >
      {/* Icon */}
      <div
        className="flex-shrink-0 w-7 h-7 rounded-md flex items-center justify-center"
        style={{ background: 'rgba(210, 153, 34, 0.20)' }}
      >
        <WifiOff size={14} style={{ color: '#d29922' }} />
      </div>

      {/* Message */}
      <div className="flex-1 min-w-0">
        <span className="text-xs font-semibold" style={{ color: '#d29922' }}>
          ⚠ Network Miss Detected&nbsp;—&nbsp;
        </span>
        <span className="text-xs" style={{ color: '#b38a00' }}>
          GitHub was unreachable on {missDate} after {attempts} retry attempt{attempts !== 1 ? 's' : ''}.
          Commits were <strong>not</strong> made.
        </span>
        {countdown && (
          <span
            className="text-[10px] font-medium ml-2 px-1.5 py-0.5 rounded"
            style={{
              background: 'rgba(210, 153, 34, 0.15)',
              color:      '#a07800',
            }}
          >
            Auto-dismisses in {countdown}
          </span>
        )}
      </div>

      {/* Dismiss (visual only — will re-appear on next data refresh) */}
      <button
        onClick={() => setDismissed(true)}
        className="flex-shrink-0 p-1 rounded transition-colors hover:bg-attention-muted"
        style={{ color: '#a07800' }}
        aria-label="Dismiss network warning"
        title="Dismiss (re-appears on refresh if still active)"
      >
        <X size={13} />
      </button>
    </div>
  )
}
