import React, { useState, useCallback, useEffect } from 'react'
import { Settings, Save, Loader2, Calendar, Zap, Activity, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { writeArchiveFile } from '../lib/github'
import { loadSettings } from '../lib/utils'

// ---------------------------------------------------------------------------
// GitHub API Helpers (per user request)
// ---------------------------------------------------------------------------
const getFile = async (filename, username, archiveRepo, pat) => {
  try {
    const response = await fetch(
      `https://api.github.com/repos/${username}/${archiveRepo}/contents/${filename}`,
      {
        headers: {
          Authorization: `token ${pat}`,
          Accept: 'application/vnd.github.v3+json'
        }
      }
    );
    if (!response.ok) {
      if (response.status === 404) return { content: null, sha: null };
      throw new Error(`Failed to fetch ${filename}`);
    }
    const data = await response.json();
    // decode base64 correctly handling unicode
    const content = JSON.parse(decodeURIComponent(escape(atob(data.content))));
    return { content, sha: data.sha };
  } catch (err) {
    console.error(err);
    return { content: null, sha: null };
  }
};

const putFile = async (filename, content, sha, username, archiveRepo, pat) => {
  const response = await fetch(
    `https://api.github.com/repos/${username}/${archiveRepo}/contents/${filename}`,
    {
      method: 'PUT',
      headers: {
        Authorization: `token ${pat}`,
        Accept: 'application/vnd.github.v3+json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        message: `dashboard: update ${filename}`,
        content: btoa(unescape(encodeURIComponent(JSON.stringify(content, null, 2)))),
        sha: sha
      })
    }
  );
  if (!response.ok) throw new Error(`Failed to save ${filename}`);
};

const generateExamDates = (year, month, count) => {
  const dates = [];
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const today = new Date();
  
  const candidates = [];
  for (let d = 1; d <= daysInMonth; d++) {
    const date = new Date(year, month, d);
    const isPast = date < today;
    const isSunday = date.getDay() === 0;
    const isMidMonth = d >= 8 && d <= 25;
    if (!isPast && !isSunday) {
      candidates.push({ day: d, weight: isMidMonth ? 3 : 1 });
    }
  }
  
  const selected = [];
  const pool = [...candidates];
  for (let i = 0; i < Math.min(count, pool.length); i++) {
    const totalWeight = pool.reduce((sum, c) => sum + c.weight, 0);
    let rand = Math.random() * totalWeight;
    for (let j = 0; j < pool.length; j++) {
      rand -= pool[j].weight;
      if (rand <= 0) {
        selected.push(pool[j].day);
        pool.splice(j, 1);
        break;
      }
    }
  }
  
  selected.sort((a, b) => a - b);
  return selected.map(d => 
    `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
  );
};


function Toggle({ id, label, description, checked, onChange, color = 'green', disabled }) {
  const colorClasses = {
    green: checked ? 'bg-success-emphasis' : 'bg-border',
    teal:  checked ? 'bg-cyan-600'         : 'bg-border',
    amber: checked ? 'bg-attention-emphasis': 'bg-border',
  }

  return (
    <div className="flex items-center justify-between py-3 border-b border-border last:border-0">
      <div>
        <div className="text-sm font-medium text-fg">{label}</div>
        <div className="text-xs text-fg-muted mt-0.5">{description}</div>
      </div>
      <button
        id={id}
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`
          toggle-track w-11 h-6 flex-shrink-0
          ${colorClasses[color]}
          disabled:opacity-40 disabled:cursor-not-allowed
        `}
      >
        <span
          className={`
            toggle-thumb
            ${checked ? 'translate-x-5' : 'translate-x-0'}
          `}
        />
      </button>
    </div>
  )
}

function CommitsSlider({ value, onChange, disabled }) {
  const percent = ((value - 1) / 6) * 100

  return (
    <div className="py-3">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-sm font-medium text-fg">Commits per day</div>
          <div className="text-xs text-fg-muted mt-0.5">Sets target for active days</div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-2xl font-bold text-success-fg">{value}</span>
          <span className="text-sm text-fg-muted">× /day</span>
        </div>
      </div>

      {/* Slider with 7 stops */}
      <div className="relative">
        <input
          id="commits-slider"
          type="range"
          min={1}
          max={7}
          step={1}
          value={value}
          onChange={e => onChange(Number(e.target.value))}
          disabled={disabled}
          style={{ '--val': `${percent}%` }}
          className="w-full h-2 rounded-full cursor-pointer disabled:opacity-40"
        />
        {/* Stop markers */}
        <div className="flex justify-between mt-1.5 px-0.5">
          {[1, 2, 3, 4, 5, 6, 7].map(n => (
            <span
              key={n}
              className={`text-[10px] font-mono ${n === value ? 'text-success-fg font-bold' : 'text-fg-subtle'}`}
            >
              {n}
            </span>
          ))}
        </div>
      </div>

      {/* Mode indicator */}
      <div className="mt-2 text-xs text-fg-muted">
        Mode:{' '}
        <span className={
          value === 1 ? 'text-fg-muted' :
          value <= 3 ? 'text-accent-fg' :
          'text-attention-fg'
        }>
          {value === 1 ? 'Quiet' : value <= 3 ? 'Normal' : 'Burst territory'}
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// NEW CONTROL 3: Today's Mood
// ---------------------------------------------------------------------------
function TodaysMood({ username, archiveRepo, pat }) {
  const [moodData, setMoodData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchMood = useCallback(async () => {
    setLoading(true);
    const { content } = await getFile('commit_plan.json', username, archiveRepo, pat);
    setMoodData(content);
    setLoading(false);
  }, [username, archiveRepo, pat]);

  useEffect(() => { fetchMood(); }, [fetchMood]);

  const getMoodColor = (mood) => {
    switch (mood) {
      case 'festival_major':
      case 'festival_minor': return 'badge-amber'; // orange-ish
      case 'exam_season': return 'badge-red';
      case 'exam_week': return 'badge-amber';
      case 'college_holiday': return 'badge-green';
      case 'monday_motivation': return 'badge-purple';
      case 'friday_winddown': return 'badge-blue';
      case 'weekend_light': return 'badge-gray';
      case 'normal': return 'badge-teal';
      default: return 'badge-gray';
    }
  };

  const isToday = (dateStr) => {
    if (!dateStr) return false;
    const today = new Date().toISOString().split('T')[0];
    return dateStr === today;
  };

  const isPlanValid = moodData && isToday(moodData.date);

  return (
    <div className="card mb-4 animate-fade-in relative overflow-hidden">
      <div className="flex items-center justify-between mb-4 relative z-10">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-accent-muted flex items-center justify-center text-accent-fg">
            <Activity size={16} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-fg">Today's Mood</h3>
            <div className="text-xs text-fg-muted">Live status from Indian Calendar Engine</div>
          </div>
        </div>
        <button onClick={fetchMood} disabled={loading} className="p-1.5 text-fg-muted hover:text-fg rounded-md transition-colors">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="relative z-10">
        {loading ? (
          <div className="skeleton h-12 w-full rounded" />
        ) : !isPlanValid ? (
          <div className="text-sm text-fg-subtle flex items-center gap-2">
            ⏳ Plan not generated yet
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`badge ${getMoodColor(moodData.mood)} text-xs px-2.5 py-1 uppercase tracking-wider font-semibold`}>
                {moodData.mood.replace('_', ' ')}
              </span>
              {moodData.occasion && (
                <span className="text-xs font-medium text-fg-muted bg-canvas-subtle px-2 py-1 rounded-md border border-border">
                  {moodData.occasion}
                </span>
              )}
            </div>
            <div className="text-sm text-fg mt-1">
              {moodData.mode === 'Rest' || moodData.commits?.length === 0 
                ? '🛋️ Rest day today' 
                : `🚀 ${moodData.commits?.length || 0} commits planned`}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// NEW CONTROL 2: Commit Intensity
// ---------------------------------------------------------------------------
function CommitIntensity({ username, archiveRepo, pat }) {
  const [intensity, setIntensity] = useState(null);
  const [sha, setSha] = useState(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchIt = async () => {
      setLoading(true);
      const { content, sha: fileSha } = await getFile('user_preferences.json', username, archiveRepo, pat);
      if (!content || !content.intensity) {
        // Auto-setup silent
        const randomInt = ['LOW', 'MEDIUM', 'HIGH'][Math.floor(Math.random() * 3)];
        setIntensity(randomInt);
        await saveIntensity(randomInt, null, true);
      } else {
        setIntensity(content.intensity);
        setSha(fileSha);
      }
      setLoading(false);
    };
    fetchIt();
  }, [username, archiveRepo, pat]);

  const saveIntensity = async (val, fileSha, silent = false) => {
    setSaving(true);
    const data = {
      intensity: val,
      set_at: new Date().toISOString(),
      daily_targets: {
        HIGH: { min: 3, max: 6, burst_chance: 0.3 },
        MEDIUM: { min: 1, max: 3, burst_chance: 0.15 },
        LOW: { min: 0, max: 2, burst_chance: 0.05 }
      }
    };
    try {
      await putFile('user_preferences.json', data, fileSha, username, archiveRepo, pat);
      // refetch sha
      const res = await getFile('user_preferences.json', username, archiveRepo, pat);
      setSha(res.sha);
      if (!silent) toast.success(`Intensity set to ${val}`);
    } catch (e) {
      if (!silent) toast.error(`Failed to save: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="skeleton h-24 w-full rounded mb-4" />;

  const options = [
    { id: 'LOW', label: 'LOW', tooltip: '0–2 commits/day', color: 'bg-fg-muted/20 text-fg-muted hover:bg-fg-muted/30', active: 'bg-fg-muted text-canvas' },
    { id: 'MEDIUM', label: 'MEDIUM', tooltip: '1–3 commits/day', color: 'bg-accent-muted text-accent-fg hover:bg-accent-muted/80', active: 'bg-accent-emphasis text-white' },
    { id: 'HIGH', label: 'HIGH', tooltip: '3–6 commits/day', color: 'bg-success-muted text-success-fg hover:bg-success-muted/80', active: 'bg-success-emphasis text-white' }
  ];

  return (
    <div className="py-4 border-b border-border">
      <div className="flex items-center gap-2 mb-3">
        <Zap size={16} className="text-attention-fg" />
        <div className="text-sm font-semibold text-fg">Commit Intensity</div>
      </div>
      
      <div className="flex p-1 bg-canvas-subtle rounded-lg border border-border w-full mb-3">
        {options.map(opt => {
          const isActive = intensity === opt.id;
          return (
            <button
              key={opt.id}
              onClick={() => setIntensity(opt.id)}
              className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all ${isActive ? opt.active + ' shadow-sm' : 'text-fg-muted hover:text-fg hover:bg-canvas'}`}
              title={opt.tooltip}
            >
              {opt.label}
            </button>
          );
        })}
      </div>

      <button
        onClick={() => saveIntensity(intensity, sha)}
        disabled={saving}
        className="btn btn-secondary w-full justify-center text-xs py-1.5"
      >
        {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save Intensity
      </button>
      <div className="text-[10px] text-fg-subtle text-center mt-2">Can be changed anytime. Takes effect from next workflow run.</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// NEW CONTROL 1: Monthly Exam Days
// ---------------------------------------------------------------------------
function MonthlyExamDays({ username, archiveRepo, pat }) {
  const [days, setDays] = useState(0);
  const [savedConfig, setSavedConfig] = useState(null);
  const [sha, setSha] = useState(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  const now = new Date();
  const currentMonthStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const monthName = now.toLocaleString('default', { month: 'long', year: 'numeric' });

  useEffect(() => {
    const fetchIt = async () => {
      setLoading(true);
      const { content, sha: fileSha } = await getFile('monthly_config.json', username, archiveRepo, pat);
      if (content && content.month === currentMonthStr) {
        setSavedConfig(content);
        setDays(content.exam_days || 0);
        setSha(fileSha);
      }
      setLoading(false);
    };
    fetchIt();
  }, [username, archiveRepo, pat, currentMonthStr]);

  const handleSave = async () => {
    setSaving(true);
    const numDays = Math.max(0, Math.min(25, Number(days) || 0));
    setDays(numDays);
    
    const exam_dates = generateExamDates(now.getFullYear(), now.getMonth(), numDays);
    
    const data = {
      month: currentMonthStr,
      exam_days: numDays,
      exam_dates: exam_dates,
      set_at: new Date().toISOString()
    };

    try {
      await putFile('monthly_config.json', data, sha, username, archiveRepo, pat);
      // update state
      setSavedConfig(data);
      const res = await getFile('monthly_config.json', username, archiveRepo, pat);
      setSha(res.sha);
      toast.success(`${numDays} exam days set for ${monthName.split(' ')[0]}`);
    } catch (e) {
      toast.error(`Failed to save. Check your PAT permissions.`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="skeleton h-24 w-full rounded" />;

  const savedDays = savedConfig ? savedConfig.exam_days : 0;
  const savedDates = savedConfig ? savedConfig.exam_dates : [];

  return (
    <div className="py-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Calendar size={16} className="text-accent-fg" />
          <div className="text-sm font-semibold text-fg">Exam Days This Month</div>
        </div>
        <div className="text-[10px] font-medium text-accent-fg bg-accent-muted px-2 py-0.5 rounded-full uppercase tracking-wider">
          {monthName}
        </div>
      </div>

      <div className="flex gap-2 items-center mb-1.5">
        <input
          type="number"
          min="0"
          max="25"
          value={days}
          onChange={(e) => setDays(e.target.value)}
          className="w-20 bg-canvas border border-border rounded-lg px-2 py-1.5 text-sm text-fg font-mono focus:outline-none focus:border-accent-fg transition-colors"
          placeholder="0"
        />
        <div className="text-xs text-fg-muted flex-1">How many exam/study days?</div>
      </div>
      <div className="text-[10px] text-fg-subtle mb-3 px-1">Currently set: {savedDays} days</div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="btn btn-primary w-full justify-center text-xs py-1.5 mb-3"
      >
        {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Set for This Month
      </button>

      {savedDates.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2 p-2 bg-canvas-subtle rounded-lg border border-border/50">
          {savedDates.map(d => {
            const dateObj = new Date(d);
            const shortDate = `${dateObj.toLocaleString('default', { month: 'short' })} ${dateObj.getDate()}`;
            return (
              <span key={d} className="text-[10px] bg-canvas border border-border px-1.5 py-0.5 rounded-full text-fg-muted font-medium">
                {shortDate}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function ControlsPanel({ config, configSha, owner, archiveRepo, onConfigUpdate, loading }) {
  const [localConfig, setLocalConfig] = useState(null)
  const [saving, setSaving] = useState(false)
  const settings = loadSettings();
  const pat = settings?.token;

  // Use local override or fall back to prop
  const cfg = localConfig || config || {}
  const active      = cfg.active ?? true
  const weekdayOnly = cfg.weekday_only ?? false
  const burstMode   = cfg.burst_mode ?? true
  const commitsDay  = cfg.commits_per_day ?? 3

  const updateLocal = useCallback((key, value) => {
    setLocalConfig(prev => ({ ...(prev || config || {}), [key]: value }))
  }, [config])

  const handleSave = useCallback(async () => {
    if (!owner || !archiveRepo || !localConfig) return
    setSaving(true)
    try {
      await writeArchiveFile(
        owner, archiveRepo, 'config.json',
        { ...(config || {}), ...localConfig },
        configSha,
        'feat: update autocommit config via dashboard'
      )
      onConfigUpdate?.({ ...(config || {}), ...localConfig })
      setLocalConfig(null)
      toast.success('Config saved to archive repo')
    } catch (err) {
      toast.error(`Save failed: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }, [owner, archiveRepo, localConfig, config, configSha, onConfigUpdate])

  const hasChanges = localConfig !== null

  return (
    <>
    <TodaysMood username={owner} archiveRepo={archiveRepo} pat={pat} />
    
    <div className="card">
      <div className="section-header">
        <div>
          <div className="section-title flex items-center gap-2">
            <Settings size={16} className="text-fg-muted" />
            Controls
          </div>
          <div className="section-subtitle">Manage automation settings</div>
        </div>
        {hasChanges && (
          <button
            id="btn-save-config"
            onClick={handleSave}
            disabled={saving || loading}
            className="btn btn-primary text-xs"
          >
            {saving ? (
              <><Loader2 size={13} className="animate-spin" /> Saving…</>
            ) : (
              <><Save size={13} /> Save Changes</>
            )}
          </button>
        )}
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="skeleton h-12 rounded" />
          ))}
        </div>
      ) : (
        <div>
          <Toggle
            id="toggle-autocommit"
            label="Auto-Commit"
            description="Master on/off switch for the entire system"
            checked={active}
            onChange={v => updateLocal('active', v)}
            color="green"
          />
          <Toggle
            id="toggle-weekday-only"
            label="Weekday Only"
            description="Skip Saturdays and Sundays entirely"
            checked={weekdayOnly}
            onChange={v => updateLocal('weekday_only', v)}
            color="teal"
          />
          <Toggle
            id="toggle-burst-mode"
            label="Burst Mode"
            description="Allow high-activity days with 4-7 commits"
            checked={burstMode}
            onChange={v => updateLocal('burst_mode', v)}
            color="amber"
          />
          <CommitsSlider
            value={commitsDay}
            onChange={v => updateLocal('commits_per_day', v)}
          />

          {/* Sick days preview */}
          {Array.isArray(cfg.sick_days_this_month) && cfg.sick_days_this_month.length > 0 && (
            <div className="mt-3 pt-3 border-t border-border">
              <div className="text-xs text-fg-muted mb-2">This month's rest days</div>
              <div className="flex flex-wrap gap-1.5">
                {cfg.sick_days_this_month.map(d => (
                  <span key={d} className="badge badge-gray font-mono text-[10px]">{d}</span>
                ))}
              </div>
            </div>
          )}
          {/* NEW CONTROLS (Hybrid Mood Model) */}
          <div className="mt-4 border-t border-border pt-2">
            <CommitIntensity username={owner} archiveRepo={archiveRepo} pat={pat} />
            <MonthlyExamDays username={owner} archiveRepo={archiveRepo} pat={pat} />
          </div>
        </div>
      )}
    </div>
    </>
  )
}
