import React, { useState, useEffect, useCallback } from 'react'
import {
  Shield, Plus, Trash2, Edit2, Calendar, RefreshCw,
  Loader2, Save, X, AlertTriangle, ChevronDown, ChevronUp, Zap
} from 'lucide-react'
import toast from 'react-hot-toast'
import { loadSettings } from '../lib/utils'

// ---------------------------------------------------------------------------
// GitHub API helpers (same pattern as ControlsPanel)
// ---------------------------------------------------------------------------
const getFile = async (filename, username, repo, pat) => {
  try {
    const r = await fetch(
      `https://api.github.com/repos/${username}/${repo}/contents/${filename}`,
      { headers: { Authorization: `token ${pat}`, Accept: 'application/vnd.github.v3+json' } }
    )
    if (!r.ok) {
      if (r.status === 404) return { content: null, sha: null }
      throw new Error(`HTTP ${r.status}`)
    }
    const data = await r.json()
    const content = JSON.parse(decodeURIComponent(escape(atob(data.content))))
    return { content, sha: data.sha }
  } catch (e) {
    console.error('[Shield]', e)
    return { content: null, sha: null }
  }
}

const putFile = async (filename, content, sha, username, repo, pat) => {
  const r = await fetch(
    `https://api.github.com/repos/${username}/${repo}/contents/${filename}`,
    {
      method: 'PUT',
      headers: {
        Authorization: `token ${pat}`,
        Accept: 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: `dashboard: update ${filename}`,
        content: btoa(unescape(encodeURIComponent(JSON.stringify(content, null, 2)))),
        sha: sha,
      }),
    }
  )
  if (!r.ok) throw new Error(`PUT failed: HTTP ${r.status}`)
}

// ---------------------------------------------------------------------------
// Date + countdown helpers (IST)
// ---------------------------------------------------------------------------
function nowIST() {
  const now = new Date()
  const utc = now.getTime() + now.getTimezoneOffset() * 60000
  return new Date(utc + 5.5 * 60 * 60 * 1000)
}

function addDays(dateStr, n) {
  const d = new Date(dateStr + 'T00:00:00+05:30')
  d.setDate(d.getDate() + n)
  return d.toISOString().split('T')[0]
}

function formatDate(isoStr) {
  if (!isoStr) return '—'
  try {
    const [y, m, d] = isoStr.split('-')
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    return `${months[parseInt(m, 10) - 1]} ${parseInt(d, 10)}, ${y}`
  } catch { return isoStr }
}

function formatCountdown(targetDateStr) {
  try {
    const target = new Date(targetDateStr + 'T00:00:00+05:30').getTime()
    const now    = nowIST().getTime()
    const ms     = target - now
    if (ms <= 0) return 'Today'
    const d = Math.floor(ms / 86400000)
    const h = Math.floor((ms % 86400000) / 3600000)
    const m = Math.floor((ms % 3600000) / 60000)
    if (d > 0) return `${d}d ${h}h ${m}m`
    if (h > 0) return `${h}h ${m}m`
    return `${m}m`
  } catch { return '—' }
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------
const STATUS_STYLES = {
  scheduled:      { pill: 'badge-gray',   icon: '⚪', label: 'Scheduled' },
  destroying_soon:{ pill: 'badge-amber',  icon: '🟡', label: 'Destroying Soon' },
  destroyed:      { pill: 'badge-red',    icon: '🔴', label: 'Hidden' },
  restoring:      { pill: 'badge-blue',   icon: '🔵', label: 'Restoring' },
  active:         { pill: 'badge-green',  icon: '🟢', label: 'Restored' },
}

function StatusBadge({ status }) {
  const s = STATUS_STYLES[status] || STATUS_STYLES.scheduled
  return (
    <span className={`badge ${s.pill} text-[10px] font-semibold uppercase tracking-wider`}>
      {s.icon} {s.label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Add / Edit modal
// ---------------------------------------------------------------------------
function InterviewModal({ initial, onSave, onCancel, saving }) {
  const todayIST = nowIST().toISOString().split('T')[0]
  const [company,       setCompany]       = useState(initial?.company       ?? '')
  const [interviewDate, setInterviewDate] = useState(initial?.date          ?? '')

  const destroyOn  = interviewDate ? addDays(interviewDate, -2) : null
  const restoreOn  = interviewDate ? addDays(interviewDate, +2) : null

  const valid = company.trim() && interviewDate && interviewDate > todayIST

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-sm bg-canvas-subtle border border-border rounded-2xl shadow-2xl animate-slide-up">
        <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Shield size={16} className="text-accent-fg" />
            <span className="text-sm font-semibold text-fg">
              {initial ? 'Edit Interview' : 'Add Interview'}
            </span>
          </div>
          <button onClick={onCancel} className="text-fg-muted hover:text-fg transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-fg-muted mb-1.5">Company / Role</label>
            <input
              id="shield-company"
              type="text"
              value={company}
              onChange={e => setCompany(e.target.value)}
              placeholder="TCS Digital, Infosys SP..."
              className="w-full bg-canvas border border-border rounded-lg px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:outline-none focus:border-accent-fg transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-fg-muted mb-1.5">Interview Date</label>
            <input
              id="shield-date"
              type="date"
              value={interviewDate}
              min={todayIST}
              onChange={e => setInterviewDate(e.target.value)}
              className="w-full bg-canvas border border-border rounded-lg px-3 py-2 text-sm text-fg focus:outline-none focus:border-accent-fg transition-colors"
            />
          </div>

          {interviewDate && (
            <div className="p-3 bg-canvas rounded-lg border border-border/60 space-y-1 text-xs text-fg-muted">
              <div className="flex justify-between">
                <span>🔴 System hides on</span>
                <span className="font-medium text-fg">{formatDate(destroyOn)}</span>
              </div>
              <div className="flex justify-between">
                <span>🟢 Auto-restore on</span>
                <span className="font-medium text-fg">{formatDate(restoreOn)}</span>
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-2 px-5 pb-5">
          <button
            onClick={onCancel}
            className="btn btn-ghost flex-1 justify-center text-sm"
          >
            Cancel
          </button>
          <button
            id="shield-save-btn"
            disabled={!valid || saving}
            onClick={() => onSave({ company: company.trim(), date: interviewDate, destroyOn, restoreOn })}
            className="btn btn-primary flex-1 justify-center text-sm"
          >
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            Save
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Countdown pill (live, 1-min interval)
// ---------------------------------------------------------------------------
function LiveCountdown({ targetDateStr, label }) {
  const [text, setText] = useState('')

  useEffect(() => {
    const tick = () => setText(formatCountdown(targetDateStr))
    tick()
    const id = setInterval(tick, 60_000)
    return () => clearInterval(id)
  }, [targetDateStr])

  if (!text || text === 'Today') return null
  return (
    <span className="text-[10px] text-fg-subtle">
      {label} <span className="font-mono text-fg-muted">{text}</span>
    </span>
  )
}

// ---------------------------------------------------------------------------
// Interview row
// ---------------------------------------------------------------------------
function InterviewRow({ iv, onEdit, onDelete, deleting }) {
  const today = nowIST().toISOString().split('T')[0]
  const isDestroyFuture = iv.destroy_on > today
  const actionDate = iv.status === 'destroyed' ? iv.restore_on : iv.destroy_on
  const actionLabel = iv.status === 'destroyed' ? 'Restore in' : 'Destroy in'

  return (
    <div className="p-4 bg-canvas-subtle rounded-xl border border-border space-y-2 hover:border-border-muted transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-fg">{iv.company}</div>
          <div className="text-xs text-fg-muted">{formatDate(iv.date)}</div>
        </div>
        <StatusBadge status={iv.status} />
      </div>

      <div className="flex items-center gap-3 text-[10px] text-fg-muted">
        <span>🔴 Destroy: <span className="text-fg">{formatDate(iv.destroy_on)}</span></span>
        <span className="text-border">|</span>
        <span>🟢 Restore: <span className="text-fg">{formatDate(iv.restore_on)}</span></span>
      </div>

      {['scheduled', 'destroying_soon', 'destroyed'].includes(iv.status) && actionDate && (
        <LiveCountdown targetDateStr={actionDate} label={`${actionLabel}:`} />
      )}

      <div className="flex gap-2 pt-1">
        <button
          onClick={() => onEdit(iv)}
          className="btn btn-ghost text-xs px-2 py-1"
          title="Edit interview"
        >
          <Edit2 size={12} /> Edit
        </button>
        <button
          onClick={() => onDelete(iv.id)}
          disabled={deleting === iv.id}
          className="btn btn-ghost text-xs px-2 py-1 hover:text-danger-fg"
          title="Delete interview"
        >
          {deleting === iv.id
            ? <Loader2 size={12} className="animate-spin" />
            : <Trash2 size={12} />}
          Delete
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main InterviewShield component
// ---------------------------------------------------------------------------
export default function InterviewShield() {
  const settings = loadSettings()
  const { token: pat, username, archiveRepo = 'commit-archive', projectRepo } = settings || {}

  const [interviews,   setInterviews]   = useState([])
  const [systemStatus, setSystemStatus] = useState('active')
  const [sha,          setSha]          = useState(null)
  const [loading,      setLoading]      = useState(true)
  const [saving,       setSaving]       = useState(false)
  const [deleting,     setDeleting]     = useState(null)
  const [showModal,    setShowModal]    = useState(false)
  const [editTarget,   setEditTarget]   = useState(null)
  const [showOverride, setShowOverride] = useState(false)
  const [overriding,   setOverriding]   = useState(null)

  // ── Load interviews.json ──────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true)
    const { content, sha: fileSha } = await getFile('interviews.json', username, archiveRepo, pat)
    if (content) {
      setInterviews(content.interviews ?? [])
      setSystemStatus(content.system_status ?? 'active')
      setSha(fileSha)
    }
    setLoading(false)
  }, [username, archiveRepo, pat])

  useEffect(() => { load() }, [load])

  // ── Helpers ───────────────────────────────────────────────────────────
  const persistInterviews = useCallback(async (newList, newStatus, currentSha) => {
    const data = { interviews: newList, system_status: newStatus ?? systemStatus }
    await putFile('interviews.json', data, currentSha, username, archiveRepo, pat)
    // Refetch SHA for next write
    const { sha: fresh } = await getFile('interviews.json', username, archiveRepo, pat)
    setSha(fresh)
  }, [username, archiveRepo, pat, systemStatus])

  // ── Add / Edit save ───────────────────────────────────────────────────
  const handleSave = async ({ company, date, destroyOn, restoreOn }) => {
    setSaving(true)
    try {
      let newList
      if (editTarget) {
        // Update existing
        newList = interviews.map(iv =>
          iv.id === editTarget.id
            ? { ...iv, company, date, destroy_on: destroyOn, restore_on: restoreOn }
            : iv
        )
      } else {
        // Create new
        const newEntry = {
          id:         crypto.randomUUID(),
          company,
          date,
          destroy_on: destroyOn,
          restore_on: restoreOn,
          status:     'scheduled',
          created_at: nowIST().toISOString(),
        }
        newList = [...interviews, newEntry]
      }
      await persistInterviews(newList, systemStatus, sha)
      setInterviews(newList)
      setShowModal(false)
      setEditTarget(null)
      toast.success(
        editTarget
          ? `✅ ${company} updated.`
          : `✅ ${company} added. System hides on ${formatDate(destroyOn)}.`
      )
    } catch (e) {
      toast.error(`❌ Save failed: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  // ── Delete ─────────────────────────────────────────────────────────────
  const handleDelete = async (id) => {
    setDeleting(id)
    try {
      const newList = interviews.filter(iv => iv.id !== id)
      await persistInterviews(newList, systemStatus, sha)
      setInterviews(newList)
      toast.success('🗑️ Interview removed.')
    } catch (e) {
      toast.error(`❌ Delete failed: ${e.message}`)
    } finally {
      setDeleting(null)
    }
  }

  // ── Force override via workflow_dispatch ───────────────────────────────
  const handleForce = async (type) => {
    if (!projectRepo) {
      toast.error('Set your project repo name in settings first.')
      return
    }
    const confirmed = window.confirm(
      type === 'destroy'
        ? '⚠️ Force destroy will delete all workflow files immediately. Are you sure?'
        : '🟢 Force restore will re-upload all backed-up files immediately. Proceed?'
    )
    if (!confirmed) return

    setOverriding(type)
    try {
      const workflowId = type === 'destroy' ? 'autocommit.yml' : 'restore_shield.yml'
      const targetRepo = type === 'destroy' ? projectRepo : archiveRepo
      const resp = await fetch(
        `https://api.github.com/repos/${username}/${targetRepo}/actions/workflows/${workflowId}/dispatches`,
        {
          method: 'POST',
          headers: {
            Authorization: `token ${pat}`,
            Accept: 'application/vnd.github.v3+json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            ref: 'main',
            inputs: type === 'restore' ? { force_restore: 'true' } : {},
          }),
        }
      )
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      toast.success(
        type === 'destroy'
          ? '💥 Destroy workflow triggered! Check GitHub Actions.'
          : '🟢 Restore workflow triggered! Check GitHub Actions.'
      )
    } catch (e) {
      toast.error(`Failed to trigger workflow: ${e.message}`)
    } finally {
      setOverriding(null)
    }
  }

  // ── Upcoming system action ─────────────────────────────────────────────
  const nextAction = interviews
    .filter(iv => ['scheduled', 'destroying_soon', 'destroyed'].includes(iv.status))
    .map(iv => ({
      iv,
      actionDate: iv.status === 'destroyed' ? iv.restore_on : iv.destroy_on,
      label: iv.status === 'destroyed' ? 'Restore' : 'Destroy',
    }))
    .sort((a, b) => a.actionDate.localeCompare(b.actionDate))[0]

  const systemStatusConfig = {
    active:    { label: '🟢 ACTIVE',    color: 'text-success-fg' },
    destroyed: { label: '🔴 HIDDEN',    color: 'text-danger-fg' },
    restoring: { label: '🔵 RESTORING', color: 'text-accent-fg' },
  }
  const sysDisplay = systemStatusConfig[systemStatus] || systemStatusConfig.active

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <>
      {showModal && (
        <InterviewModal
          initial={editTarget}
          onSave={handleSave}
          onCancel={() => { setShowModal(false); setEditTarget(null) }}
          saving={saving}
        />
      )}

      <div className="max-w-2xl space-y-4 animate-fade-in">
        {/* ── Header card ──────────────────────────────────────────── */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-lg bg-accent-muted flex items-center justify-center">
                <Shield size={18} className="text-accent-fg" />
              </div>
              <div>
                <h2 className="text-base font-bold text-fg">Interview Shield</h2>
                <p className="text-xs text-fg-muted">Auto-hides your commit engine before interviews</p>
              </div>
            </div>
            <button
              onClick={load}
              disabled={loading}
              className="p-1.5 text-fg-muted hover:text-fg rounded-md transition-colors"
              title="Refresh"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 bg-canvas-subtle rounded-lg border border-border">
              <div className="text-[10px] text-fg-subtle uppercase tracking-wider mb-1">System Status</div>
              <div className={`text-sm font-bold ${sysDisplay.color}`}>{sysDisplay.label}</div>
            </div>
            <div className="p-3 bg-canvas-subtle rounded-lg border border-border">
              <div className="text-[10px] text-fg-subtle uppercase tracking-wider mb-1">Next Action</div>
              {nextAction ? (
                <>
                  <div className="text-xs font-medium text-fg">{nextAction.label}: {formatDate(nextAction.actionDate)}</div>
                  <LiveCountdown targetDateStr={nextAction.actionDate} label="In" />
                </>
              ) : (
                <div className="text-xs text-fg-subtle">No upcoming actions</div>
              )}
            </div>
          </div>
        </div>

        {/* ── Interviews list ───────────────────────────────────────── */}
        <div className="card">
          <div className="section-header mb-4">
            <div className="section-title flex items-center gap-2">
              <Calendar size={15} className="text-fg-muted" />
              Scheduled Interviews
            </div>
            <button
              id="shield-add-btn"
              onClick={() => { setEditTarget(null); setShowModal(true) }}
              className="btn btn-primary text-xs"
            >
              <Plus size={13} /> Add Interview
            </button>
          </div>

          {loading ? (
            <div className="space-y-3">
              {[1, 2].map(i => <div key={i} className="skeleton h-28 rounded-xl" />)}
            </div>
          ) : interviews.length === 0 ? (
            <div className="text-center py-10 text-fg-subtle text-sm">
              <Shield size={32} className="mx-auto mb-3 opacity-20" />
              No interviews scheduled yet.<br />
              <span className="text-xs">Add one to activate the shield.</span>
            </div>
          ) : (
            <div className="space-y-3">
              {interviews.map(iv => (
                <InterviewRow
                  key={iv.id}
                  iv={iv}
                  onEdit={target => { setEditTarget(target); setShowModal(true) }}
                  onDelete={handleDelete}
                  deleting={deleting}
                />
              ))}
            </div>
          )}
        </div>

        {/* ── Manual overrides (collapsed) ─────────────────────────── */}
        <div className="card">
          <button
            onClick={() => setShowOverride(p => !p)}
            className="flex items-center justify-between w-full text-sm font-medium text-fg"
          >
            <span className="flex items-center gap-2">
              <Zap size={14} className="text-attention-fg" /> Manual Overrides
            </span>
            {showOverride ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {showOverride && (
            <div className="mt-4 space-y-3 border-t border-border pt-4">
              <p className="text-xs text-fg-muted">
                ⚠️ These actions run immediately regardless of scheduled dates.
                Use with care.
              </p>
              <div className="flex gap-3">
                <button
                  id="shield-force-destroy"
                  onClick={() => handleForce('destroy')}
                  disabled={!!overriding}
                  className="btn btn-ghost text-xs border border-danger-fg/30 text-danger-fg hover:bg-danger-muted flex-1 justify-center"
                >
                  {overriding === 'destroy'
                    ? <Loader2 size={13} className="animate-spin" />
                    : '🔴'}
                  Force Destroy Now
                </button>
                <button
                  id="shield-force-restore"
                  onClick={() => handleForce('restore')}
                  disabled={!!overriding}
                  className="btn btn-ghost text-xs border border-success-fg/30 text-success-fg hover:bg-success-muted flex-1 justify-center"
                >
                  {overriding === 'restore'
                    ? <Loader2 size={13} className="animate-spin" />
                    : '🟢'}
                  Force Restore Now
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
