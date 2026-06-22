import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  Bot, Search, CheckCircle, XCircle, Loader2,
  ChevronDown, ChevronUp, Clock, AlertTriangle, Sparkles,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { loadSettings } from '../lib/utils'

// ---------------------------------------------------------------------------
// GitHub API helpers
// ---------------------------------------------------------------------------
const GH_API = 'https://api.github.com'

async function getFile(filename, username, repo, pat) {
  try {
    const r = await fetch(
      `${GH_API}/repos/${username}/${repo}/contents/${filename}`,
      { headers: { Authorization: `token ${pat}`, Accept: 'application/vnd.github.v3+json' } }
    )
    if (!r.ok) {
      if (r.status === 404) return { content: null, sha: null }
      throw new Error(`HTTP ${r.status}`)
    }
    const data = await r.json()
    const raw = atob(data.content.replace(/\n/g, ''))
    return { content: JSON.parse(raw), sha: data.sha }
  } catch (e) {
    console.error(`[NLScheduler] getFile ${filename}:`, e)
    return { content: null, sha: null }
  }
}

async function putFile(filename, content, sha, username, repo, pat, message) {
  const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(content, null, 2))))
  const body = { message: message ?? `nlscheduler: update ${filename}`, content: encoded }
  if (sha) body.sha = sha
  const r = await fetch(
    `${GH_API}/repos/${username}/${repo}/contents/${filename}`,
    {
      method: 'PUT',
      headers: {
        Authorization: `token ${pat}`,
        Accept: 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    }
  )
  if (!r.ok) throw new Error(`PUT ${filename} failed: HTTP ${r.status}`)
  return r.json()
}

// ---------------------------------------------------------------------------
// IST date helpers
// ---------------------------------------------------------------------------
function todayIST() {
  const now = new Date()
  const utc = now.getTime() + now.getTimezoneOffset() * 60000
  const ist = new Date(utc + 5.5 * 3600000)
  return ist.toISOString().split('T')[0]
}

function formatHistoryDate(isoStr) {
  try {
    const [y, m, d] = isoStr.split('-')
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    return `${months[parseInt(m) - 1]} ${parseInt(d)}`
  } catch { return isoStr }
}

// ---------------------------------------------------------------------------
// Gemini AI call
// ---------------------------------------------------------------------------
const GEMINI_API = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent'

function buildFullPrompt(userText, configs) {
  const today = todayIST()
  const systemBlock = `You are a configuration parser for a GitHub commit scheduling system.
The user will describe their schedule in plain English.
You must extract scheduling intents and return a JSON object with proposed config changes.

Current date: ${today}
Current configs:
config.json: ${JSON.stringify(configs.config ?? {}, null, 2)}
monthly_config.json: ${JSON.stringify(configs.monthly ?? {}, null, 2)}
user_preferences.json: ${JSON.stringify(configs.prefs ?? {}, null, 2)}
interviews.json: ${JSON.stringify(configs.interviews ?? {}, null, 2)}

Extract these intent types:
- INTERVIEW: company name + date → add to interviews.json
- VACATION/PAUSE: date range → set config.json scheduled_pause
- EXAM/STUDY: month + optional count → update monthly_config.json exam_days
- INTENSITY_UP: "increase", "more commits", "burst" → user_preferences HIGH
- INTENSITY_DOWN: "reduce", "fewer", "1 commit/day", "quiet" → user_preferences LOW
- INTENSITY_NORMAL: "normal", "resume", "regular" → user_preferences MEDIUM
- MOOD_OVERRIDE: explicit mood set → config.json mood_override

Rules:
- If user says "placements in September" → treat as interview, company="Placement Drive", date=Sep 1 of nearest future year
- If user says "exams in November" → set monthly_config for November, exam_days=15 (default if no count given)
- If user says "vacation July 1-10" → add scheduled_pause to config.json: {"start": "YYYY-07-01", "end": "YYYY-07-10"}
- Infer year as current or next year, whichever is in the future
- For interviews: destroy_on = interview date - 2 days, restore_on = interview date + 2 days
- For exam_dates: spread evenly across the month (weekdays only, no Sundays)
- If intent is unclear → include in "unrecognized" array
- Generate UUID-like ids using timestamp: "nl-" + Date.now()

Return ONLY valid JSON, no markdown, no explanation:
{
  "changes": {
    "config.json": { "field": "new_value" } or null,
    "monthly_config.json": { "month": "YYYY-MM", "exam_days": 15, "exam_dates": ["YYYY-MM-DD", ...] } or null,
    "user_preferences.json": { "intensity": "HIGH" } or null,
    "interviews.json": {
      "add": [{ "id": "nl-123", "company": "Google", "date": "YYYY-MM-DD", "destroy_on": "YYYY-MM-DD", "restore_on": "YYYY-MM-DD", "status": "scheduled", "created_at": "${today}T00:00:00+05:30" }],
      "remove_ids": []
    } or null
  },
  "summary": ["Human-readable summary of each change"],
  "unrecognized": ["Could not understand: 'vague phrase'"],
  "scheduled_changes": [{ "effective_date": "YYYY-MM-DD", "file": "user_preferences.json", "change": {"intensity": "HIGH"} }]
}`

  // Combine system context + user instruction into one prompt text
  // (Gemini doesn't have a separate system role in the free API)
  return `${systemBlock}

User instruction:
${userText}`
}

async function callGemini(userText, configs, geminiKey) {
  const fullPrompt = buildFullPrompt(userText, configs)

  const response = await fetch(
    `${GEMINI_API}?key=${geminiKey}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: fullPrompt }] }],
        generationConfig: {
          temperature: 0.2,   // Low temp for deterministic JSON output
          maxOutputTokens: 1024,
        },
      }),
    }
  )

  if (!response.ok) {
    const errText = await response.text().catch(() => '')
    throw new Error(`Gemini API error ${response.status}: ${errText.slice(0, 200)}`)
  }

  const data = await response.json()
  const raw = data.candidates?.[0]?.content?.parts?.[0]?.text ?? ''

  // Strip markdown fences the model might wrap around JSON
  const clean = raw.replace(/```json\s*|```\s*/g, '').trim()

  try {
    return JSON.parse(clean)
  } catch {
    // Second attempt: find first {...} block in response
    const match = clean.match(/\{[\s\S]*\}/)
    if (match) return JSON.parse(match[0])
    throw new Error('Could not parse Gemini response as JSON')
  }
}

// ---------------------------------------------------------------------------
// Preview diff renderer
// ---------------------------------------------------------------------------
function renderDiff(label, oldVal, newVal) {
  const oldStr = oldVal === undefined || oldVal === null ? '(none)' : JSON.stringify(oldVal)
  const newStr = newVal === undefined || newVal === null ? '(none)' : JSON.stringify(newVal)
  return (
    <div key={label} className="flex items-start gap-1 text-xs">
      <span className="text-fg-muted min-w-[4px]">•</span>
      <span>
        <span className="font-mono text-fg-muted">{label}</span>
        {': '}
        <span className="font-mono line-through text-danger-fg opacity-70">{oldStr}</span>
        {' → '}
        <span className="font-mono text-success-fg">{newStr}</span>
      </span>
    </div>
  )
}

function PreviewSection({ title, children }) {
  if (!children) return null
  return (
    <div className="space-y-1.5">
      <div className="text-[10px] font-semibold text-fg-muted uppercase tracking-wider">{title}</div>
      <div className="space-y-1 pl-1">{children}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// History item
// ---------------------------------------------------------------------------
function HistoryItem({ entry }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(p => !p)}
        className="flex items-center justify-between w-full px-3 py-2 text-left hover:bg-canvas-subtle transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          <Clock size={11} className="text-fg-subtle flex-shrink-0" />
          <span className="text-[11px] text-fg-muted flex-shrink-0">{formatHistoryDate(entry.date)}</span>
          <span className="text-xs text-fg truncate">{entry.summary?.[0] ?? entry.input?.slice(0, 60)}</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0 ml-2">
          <span className="badge badge-gray text-[10px]">{entry.changes_count} change{entry.changes_count !== 1 ? 's' : ''}</span>
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </div>
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-1 border-t border-border bg-canvas-subtle">
          {entry.summary?.map((s, i) => (
            <div key={i} className="text-xs text-fg-muted flex gap-1">
              <span className="text-success-fg">✓</span> {s}
            </div>
          ))}
          {entry.unrecognized?.length > 0 && entry.unrecognized.map((u, i) => (
            <div key={i} className="text-xs text-attention-fg flex gap-1">
              <span>⚠</span> {u}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// State machine constants
// ---------------------------------------------------------------------------
const STATE = {
  IDLE:     'idle',
  PARSING:  'parsing',
  PREVIEW:  'preview',
  APPLYING: 'applying',
  SUCCESS:  'success',
  ERROR:    'error',
}

const MAX_CHARS = 500
const HISTORY_KEY = 'nl_scheduler_history'

// ---------------------------------------------------------------------------
// Main NLScheduler component
// ---------------------------------------------------------------------------
export default function NLScheduler() {
  const settings = loadSettings()
  const { token: pat, username, archiveRepo = 'commit-archive' } = settings || {}

  // Component state
  const [uiState,       setUiState]       = useState(STATE.IDLE)
  const [inputText,     setInputText]      = useState('')
  const [errorMsg,      setErrorMsg]       = useState('')
  const [successMsg,    setSuccessMsg]     = useState('')
  const [parsed,        setParsed]         = useState(null)
  const [history,       setHistory]        = useState([])

  // Gemini API key (stored only in localStorage, never in files)
  const [geminiKey,     setGeminiKey]      = useState(() => localStorage.getItem('gemini_key') || '')
  const [keyInput,      setKeyInput]       = useState('')
  const [showKeyPanel,  setShowKeyPanel]   = useState(false)
  const [keySaved,      setKeySaved]       = useState(false)

  // Config data from archive
  const [configs,       setConfigs]        = useState({})
  const [shas,          setShas]           = useState({})
  const [configsLoaded, setConfigsLoaded]  = useState(false)

  // Applied changes count
  const [appliedCount,  setAppliedCount]   = useState(0)
  const [totalCount,    setTotalCount]     = useState(0)

  const textareaRef = useRef(null)

  // ── Load history from localStorage ───────────────────────────────────────
  useEffect(() => {
    try {
      const stored = localStorage.getItem(HISTORY_KEY)
      if (stored) setHistory(JSON.parse(stored))
    } catch {}
  }, [])

  // ── Load all 4 configs in parallel ───────────────────────────────────────
  const loadConfigs = useCallback(async () => {
    if (!pat || !username) return
    setConfigsLoaded(false)

    const FILES = [
      'config.json',
      'monthly_config.json',
      'user_preferences.json',
      'interviews.json',
    ]
    const results = await Promise.all(FILES.map(f => getFile(f, username, archiveRepo, pat)))

    setConfigs({
      config:     results[0].content ?? {},
      monthly:    results[1].content ?? {},
      prefs:      results[2].content ?? {},
      interviews: results[3].content ?? { interviews: [], system_status: 'active' },
    })
    setShas({
      config:     results[0].sha,
      monthly:    results[1].sha,
      prefs:      results[2].sha,
      interviews: results[3].sha,
    })
    setConfigsLoaded(true)
  }, [pat, username, archiveRepo])

  useEffect(() => { loadConfigs() }, [loadConfigs])

  // ── Parse (call Gemini) ───────────────────────────────────────────────────
  const handleParse = async () => {
    if (!inputText.trim()) {
      setErrorMsg('Please describe your schedule first.')
      return
    }
    if (!geminiKey) {
      setShowKeyPanel(true)
      setErrorMsg('⚠️ Add your Gemini API key first. Get a free key at aistudio.google.com')
      setUiState(STATE.ERROR)
      return
    }
    setUiState(STATE.PARSING)
    setErrorMsg('')
    setParsed(null)

    try {
      const result = await callGemini(inputText.trim(), configs, geminiKey)
      setParsed(result)
      setUiState(STATE.PREVIEW)
    } catch (e) {
      console.error('[NLScheduler] parse error:', e)
      if (e.message.includes('403') || e.message.includes('API_KEY')) {
        setErrorMsg(`❌ Invalid Gemini API key. Check your key and try again.`)
        setShowKeyPanel(true)
      } else if (e.message.includes('fetch') || e.message.includes('network') || e.message.includes('Failed')) {
        setErrorMsg('❌ Connection failed. Check your internet.')
      } else {
        setErrorMsg("❌ AI couldn't parse this. Try: 'Interview at [Company] on [Date]' or 'Exams in [Month]'")
      }
      setUiState(STATE.ERROR)
    }
  }

  // ── Apply changes ─────────────────────────────────────────────────────────
  const handleApply = async () => {
    if (!parsed) return
    setUiState(STATE.APPLYING)
    const changes    = parsed.changes ?? {}
    const scheduled  = parsed.scheduled_changes ?? []
    let applied = 0
    let total   = 0
    const failed = []

    // ── config.json ──────────────────────────────────────────────────────
    const cfgChanges = changes['config.json']
    const hasCfgScheduled = scheduled.some(s => s.file === 'config.json')
    if (cfgChanges || hasCfgScheduled) {
      total++
      try {
        const updated = { ...configs.config, ...cfgChanges }
        // Merge scheduled_changes for config
        scheduled.filter(s => s.file === 'config.json').forEach(s => {
          Object.assign(updated, s.change)
        })
        const res = await putFile('config.json', updated, shas.config, username, archiveRepo, pat, 'nlscheduler: update config.json [skip ci]')
        setShas(p => ({ ...p, config: res.content?.sha ?? p.config }))
        setConfigs(p => ({ ...p, config: updated }))
        applied++
      } catch (e) { failed.push('config.json'); console.error(e) }
    }

    // ── monthly_config.json ──────────────────────────────────────────────
    const monthlyChanges = changes['monthly_config.json']
    if (monthlyChanges) {
      total++
      try {
        const today = todayIST()
        const currentMonth = today.slice(0, 7)
        const targetMonth  = monthlyChanges.month ?? currentMonth

        if (targetMonth <= currentMonth) {
          // Current or past month — update directly
          const updated = { ...configs.monthly, ...monthlyChanges }
          const res = await putFile('monthly_config.json', updated, shas.monthly, username, archiveRepo, pat, 'nlscheduler: update monthly_config.json [skip ci]')
          setShas(p => ({ ...p, monthly: res.content?.sha ?? p.monthly }))
          setConfigs(p => ({ ...p, monthly: updated }))
        } else {
          // Future month — store in config.json as future_exam_configs
          const existing = configs.config?.future_exam_configs ?? []
          const others   = existing.filter(e => e.month !== targetMonth)
          const updated  = { ...configs.config, future_exam_configs: [...others, monthlyChanges] }
          const res = await putFile('config.json', updated, shas.config, username, archiveRepo, pat, 'nlscheduler: store future exam config [skip ci]')
          setShas(p => ({ ...p, config: res.content?.sha ?? p.config }))
          setConfigs(p => ({ ...p, config: updated }))
        }
        applied++
      } catch (e) { failed.push('monthly_config.json'); console.error(e) }
    }

    // ── user_preferences.json ────────────────────────────────────────────
    const prefsChanges = changes['user_preferences.json']
    const hasPrefsScheduled = scheduled.some(s => s.file === 'user_preferences.json')
    if (prefsChanges) {
      total++
      try {
        const updated = { ...configs.prefs, ...prefsChanges }
        const res = await putFile('user_preferences.json', updated, shas.prefs, username, archiveRepo, pat, 'nlscheduler: update user_preferences.json [skip ci]')
        setShas(p => ({ ...p, prefs: res.content?.sha ?? p.prefs }))
        setConfigs(p => ({ ...p, prefs: updated }))
        applied++
      } catch (e) { failed.push('user_preferences.json'); console.error(e) }
    }
    if (hasPrefsScheduled && !prefsChanges) {
      // Store scheduled intensity change in config
      total++
      try {
        const sc = scheduled.find(s => s.file === 'user_preferences.json')
        const updated = {
          ...configs.config,
          scheduled_intensity: { date: sc.effective_date, intensity: sc.change.intensity },
        }
        const res = await putFile('config.json', updated, shas.config, username, archiveRepo, pat, 'nlscheduler: store scheduled intensity [skip ci]')
        setShas(p => ({ ...p, config: res.content?.sha ?? p.config }))
        setConfigs(p => ({ ...p, config: updated }))
        applied++
      } catch (e) { failed.push('scheduled_intensity'); console.error(e) }
    }

    // ── interviews.json ──────────────────────────────────────────────────
    const ivChanges = changes['interviews.json']
    if (ivChanges) {
      total++
      try {
        const current = configs.interviews ?? { interviews: [], system_status: 'active' }
        let ivList = [...(current.interviews ?? [])]
        // Remove
        const removeSet = new Set(ivChanges.remove_ids ?? [])
        if (removeSet.size) ivList = ivList.filter(iv => !removeSet.has(iv.id))
        // Add
        for (const newIv of (ivChanges.add ?? [])) {
          ivList.push({ ...newIv, created_at: new Date().toISOString() })
        }
        const updated = { ...current, interviews: ivList }
        const res = await putFile('interviews.json', updated, shas.interviews, username, archiveRepo, pat, 'nlscheduler: update interviews.json [skip ci]')
        setShas(p => ({ ...p, interviews: res.content?.sha ?? p.interviews }))
        setConfigs(p => ({ ...p, interviews: updated }))
        applied++
      } catch (e) { failed.push('interviews.json'); console.error(e) }
    }

    // ── Persist history in localStorage ─────────────────────────────────
    const entry = {
      date:          todayIST(),
      input:         inputText.trim().slice(0, 120),
      summary:       parsed.summary ?? [],
      unrecognized:  parsed.unrecognized ?? [],
      changes_count: applied,
    }
    const newHistory = [entry, ...history].slice(0, 10)
    setHistory(newHistory)
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(newHistory)) } catch {}

    setAppliedCount(applied)
    setTotalCount(total)

    if (failed.length === 0) {
      setSuccessMsg(`✅ ${applied} change${applied !== 1 ? 's' : ''} applied successfully.`)
      setUiState(STATE.SUCCESS)
      toast.success(`AI Scheduler: ${applied} change${applied !== 1 ? 's' : ''} applied!`)
    } else if (applied > 0) {
      setSuccessMsg(`⚠️ ${applied} of ${total} changes applied. Failed: ${failed.join(', ')}`)
      setUiState(STATE.ERROR)
      setErrorMsg(`⚠️ ${applied} of ${total} changes applied. ${failed.join(', ')} failed.`)
    } else {
      setErrorMsg('❌ All changes failed to apply. Check your connection.')
      setUiState(STATE.ERROR)
    }
  }

  const handleCancel = () => {
    setParsed(null)
    setUiState(STATE.IDLE)
    setErrorMsg('')
  }

  const handleReset = () => {
    setParsed(null)
    setInputText('')
    setUiState(STATE.IDLE)
    setErrorMsg('')
    setSuccessMsg('')
  }

  const isParsing  = uiState === STATE.PARSING
  const isApplying = uiState === STATE.APPLYING
  const isBusy     = isParsing || isApplying
  const showPreview = uiState === STATE.PREVIEW || uiState === STATE.APPLYING

  // ── Build preview from parsed result ─────────────────────────────────────
  function renderPreview() {
    if (!parsed) return null
    const changes = parsed.changes ?? {}
    const sections = []

    const cfg = changes['config.json']
    if (cfg) {
      sections.push(
        <PreviewSection key="cfg" title="config.json">
          {Object.entries(cfg).map(([k, v]) =>
            renderDiff(k, configs.config?.[k], v)
          )}
        </PreviewSection>
      )
    }

    const monthly = changes['monthly_config.json']
    if (monthly) {
      sections.push(
        <PreviewSection key="monthly" title="monthly_config.json">
          {monthly.exam_days !== undefined && renderDiff('exam_days', configs.monthly?.exam_days, monthly.exam_days)}
          {monthly.month     !== undefined && renderDiff('month', configs.monthly?.month, monthly.month)}
          {monthly.exam_dates && (
            <div className="text-xs text-fg-muted pl-1">
              <span>• </span>
              <span className="font-mono">exam_dates: </span>
              <span className="text-success-fg">{monthly.exam_dates.slice(0, 3).join(', ')}{monthly.exam_dates.length > 3 ? ` +${monthly.exam_dates.length - 3} more` : ''}</span>
            </div>
          )}
        </PreviewSection>
      )
    }

    const prefs = changes['user_preferences.json']
    if (prefs) {
      sections.push(
        <PreviewSection key="prefs" title="user_preferences.json">
          {Object.entries(prefs).map(([k, v]) =>
            renderDiff(k, configs.prefs?.[k], v)
          )}
        </PreviewSection>
      )
    }

    const iv = changes['interviews.json']
    if (iv?.add?.length) {
      sections.push(
        <PreviewSection key="iv" title="interviews.json">
          {iv.add.map((entry, i) => (
            <div key={i} className="text-xs space-y-0.5 pl-1">
              <div className="text-success-fg">+ Adding: <span className="font-semibold text-fg">{entry.company}</span> — {entry.date}</div>
              <div className="text-fg-muted pl-2">Destroy: {entry.destroy_on} | Restore: {entry.restore_on}</div>
            </div>
          ))}
          {iv.remove_ids?.length > 0 && (
            <div className="text-xs text-danger-fg pl-1">− Removing {iv.remove_ids.length} interview(s)</div>
          )}
        </PreviewSection>
      )
    }

    const scheduled = parsed.scheduled_changes ?? []
    if (scheduled.length > 0) {
      sections.push(
        <PreviewSection key="sched" title="Scheduled (future-dated)">
          {scheduled.map((s, i) => (
            <div key={i} className="text-xs text-fg-muted pl-1">
              <span className="text-accent-fg">⏰ {s.effective_date}</span>
              {' — '}
              <span className="font-mono">{s.file}</span>
              {' → '}
              <span className="text-fg">{JSON.stringify(s.change)}</span>
            </div>
          ))}
        </PreviewSection>
      )
    }

    if (sections.length === 0) {
      sections.push(
        <div key="none" className="text-xs text-fg-muted">No config changes detected.</div>
      )
    }

    return (
      <div className="space-y-4">
        {sections}
        {parsed.unrecognized?.length > 0 && (
          <div className="p-3 bg-attention-muted/20 border border-attention-fg/20 rounded-lg space-y-1">
            <div className="text-[10px] font-semibold text-attention-fg uppercase tracking-wider flex items-center gap-1">
              <AlertTriangle size={10} /> Unrecognized
            </div>
            {parsed.unrecognized.map((u, i) => (
              <div key={i} className="text-xs text-attention-fg">{u}</div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-2xl space-y-4 animate-fade-in">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="card">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-accent-muted flex items-center justify-center">
            <Bot size={20} className="text-accent-fg" />
          </div>
          <div>
            <h2 className="text-base font-bold text-fg">AI Scheduler</h2>
            <p className="text-xs text-fg-muted">
              Describe your schedule in plain English — AI handles the config.
            </p>
          </div>
        </div>

        {/* ── Text input ─────────────────────────────────────────────── */}
        <div className="space-y-2">
          <label className="block text-xs font-medium text-fg-muted">
            Tell the system what you need:
          </label>
          <div className="relative">
            <textarea
              id="nl-scheduler-input"
              ref={textareaRef}
              value={inputText}
              onChange={e => {
                if (e.target.value.length <= MAX_CHARS) setInputText(e.target.value)
              }}
              disabled={isBusy || showPreview}
              placeholder={"e.g. I have an interview at Google on August 3. Exams in November. Going on vacation July 1-10, pause commits."}
              rows={5}
              className={`
                w-full resize-y bg-canvas border border-border rounded-xl px-4 py-3
                text-sm text-fg placeholder:text-fg-subtle
                focus:outline-none focus:border-accent-fg transition-colors
                min-h-[120px] leading-relaxed
                ${(isBusy || showPreview) ? 'opacity-50 cursor-not-allowed' : ''}
              `}
            />
            <div className={`
              absolute bottom-2.5 right-3 text-[10px] font-mono
              ${inputText.length > MAX_CHARS * 0.9 ? 'text-danger-fg' : 'text-fg-subtle'}
            `}>
              {inputText.length}/{MAX_CHARS}
            </div>
          </div>
        </div>

        {/* ── API Key section (collapsible) ──────────────────────────── */}
        <div className="mt-4 border border-border rounded-xl overflow-hidden">
          <button
            onClick={() => { setShowKeyPanel(p => !p); setKeySaved(false) }}
            className="flex items-center justify-between w-full px-4 py-2.5 text-left hover:bg-canvas-subtle transition-colors"
          >
            <span className="flex items-center gap-2 text-xs font-medium text-fg-muted">
              <span>⚙️</span>
              API Key
              {geminiKey && <span className="badge badge-green text-[9px]">Saved</span>}
            </span>
            {showKeyPanel ? <ChevronUp size={13} className="text-fg-subtle" /> : <ChevronDown size={13} className="text-fg-subtle" />}
          </button>

          {showKeyPanel && (
            <div className="px-4 pb-4 pt-2 border-t border-border space-y-3 bg-canvas-subtle">
              <p className="text-xs text-fg-muted">
                Your Gemini API key is stored only in this browser — never in any file or repo.{' '}
                <a
                  href="https://aistudio.google.com/app/apikey"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent-fg underline hover:no-underline"
                >
                  Get a free key at aistudio.google.com
                </a>
              </p>
              <div className="flex gap-2">
                <input
                  id="nl-gemini-key-input"
                  type="password"
                  value={keyInput}
                  onChange={e => { setKeyInput(e.target.value); setKeySaved(false) }}
                  placeholder={geminiKey ? '••••••••••••••••••••••' : 'Paste your Gemini API key here'}
                  className="flex-1 bg-canvas border border-border rounded-lg px-3 py-2 text-xs text-fg
                             placeholder:text-fg-subtle focus:outline-none focus:border-accent-fg transition-colors"
                />
                <button
                  id="nl-save-key-btn"
                  onClick={() => {
                    const k = keyInput.trim()
                    if (!k) return
                    localStorage.setItem('gemini_key', k)
                    setGeminiKey(k)
                    setKeyInput('')
                    setKeySaved(true)
                    // Clear any missing-key error
                    if (errorMsg.includes('API key')) {
                      setErrorMsg('')
                      setUiState(STATE.IDLE)
                    }
                  }}
                  disabled={!keyInput.trim()}
                  className="btn btn-primary text-xs px-3 whitespace-nowrap"
                >
                  Save to Browser
                </button>
              </div>
              {keySaved && (
                <p className="text-xs text-success-fg flex items-center gap-1">
                  <CheckCircle size={11} /> Key saved. You can now use the AI Scheduler.
                </p>
              )}
              {geminiKey && !keySaved && (
                <p className="text-[10px] text-fg-subtle">
                  Key is set. Paste a new key above to update it.
                </p>
              )}
            </div>
          )}
        </div>

        {/* ── Parse button + error ────────────────────────────────────── */}
        <div className="mt-4 space-y-3">
          {!showPreview && uiState !== STATE.SUCCESS && (
            <div className="flex items-center gap-3">
              <button
                id="nl-parse-btn"
                onClick={handleParse}
                disabled={isBusy || !inputText.trim() || !configsLoaded}
                className="btn btn-primary gap-2"
              >
                {isParsing ? (
                  <><Loader2 size={14} className="animate-spin" /> AI is reading your instructions…</>
                ) : (
                  <><Search size={14} /> Parse &amp; Preview</>
                )}
              </button>
              {!configsLoaded && (
                <span className="text-xs text-fg-muted">Loading configs…</span>
              )}
            </div>
          )}

          {(uiState === STATE.ERROR) && errorMsg && (
            <div className="flex items-start gap-2 p-3 bg-danger-muted/20 border border-danger-fg/20 rounded-lg">
              <XCircle size={14} className="text-danger-fg flex-shrink-0 mt-0.5" />
              <div className="space-y-2">
                <p className="text-xs text-danger-fg">{errorMsg}</p>
                <button onClick={handleReset} className="btn btn-ghost text-xs">Try again</button>
              </div>
            </div>
          )}

          {uiState === STATE.SUCCESS && (
            <div className="flex items-start gap-2 p-3 bg-success-muted/20 border border-success-fg/20 rounded-lg">
              <CheckCircle size={14} className="text-success-fg flex-shrink-0 mt-0.5" />
              <div className="space-y-2">
                <p className="text-xs text-success-fg">{successMsg}</p>
                <button onClick={handleReset} className="btn btn-ghost text-xs">Schedule something else</button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Preview card ─────────────────────────────────────────────────── */}
      {showPreview && (
        <div className="card animate-fade-in">
          <div className="section-header mb-4">
            <div className="section-title flex items-center gap-2">
              <Sparkles size={14} className="text-accent-fg" />
              Preview of Changes
            </div>
          </div>

          <div className="space-y-4 mb-5">
            {renderPreview()}
          </div>

          {/* Summary pills */}
          {parsed?.summary?.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-5">
              {parsed.summary.map((s, i) => (
                <span key={i} className="badge badge-green text-[10px]">✓ {s}</span>
              ))}
            </div>
          )}

          {/* Apply / Cancel */}
          <div className="flex gap-3">
            <button
              id="nl-cancel-btn"
              onClick={handleCancel}
              disabled={isApplying}
              className="btn btn-ghost flex-1 justify-center"
            >
              <XCircle size={14} /> Cancel
            </button>
            <button
              id="nl-apply-btn"
              onClick={handleApply}
              disabled={isApplying}
              className="btn btn-primary flex-1 justify-center"
            >
              {isApplying ? (
                <><Loader2 size={14} className="animate-spin" /> Updating config files…</>
              ) : (
                <><CheckCircle size={14} /> Apply All Changes</>
              )}
            </button>
          </div>
        </div>
      )}

      {/* ── History ──────────────────────────────────────────────────────── */}
      {history.length > 0 && (
        <div className="card">
          <div className="section-title flex items-center gap-2 mb-3">
            <Clock size={14} className="text-fg-muted" />
            History
          </div>
          <div className="space-y-2">
            {history.slice(0, 5).map((entry, i) => (
              <HistoryItem key={i} entry={entry} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
