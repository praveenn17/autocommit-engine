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

function SmartModeCard({ username, archiveRepo, pat, config }) {
  const [plan, setPlan] = useState(null);
  const [seed, setSeed] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchDetails = useCallback(async () => {
    setLoading(true);
    const [planRes, seedRes] = await Promise.all([
      getFile('commit_plan.json', username, archiveRepo, pat),
      getFile('smart_mode_seed.json', username, archiveRepo, pat)
    ]);
    setPlan(planRes.content);
    setSeed(seedRes.content);
    setLoading(false);
  }, [username, archiveRepo, pat]);

  useEffect(() => { fetchDetails(); }, [fetchDetails]);

  const launchDate = new Date(config?.launch_date || '2026-06-22');
  const today = new Date();
  const dayNumber = Math.floor((today - launchDate) / (1000 * 60 * 60 * 24)) + 1;
  const cycleDay = ((dayNumber - 1) % 60) + 1;

  const isTodayPlan = plan?.date === today.toISOString().split('T')[0];
  const count = isTodayPlan && Array.isArray(plan?.commits) ? plan.commits.length : 0;
  const plannedCommits = count;

  const formatTime = (timeStr) => {
    const [hStr, mStr] = timeStr.split(':');
    const h = parseInt(hStr, 10);
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 || 12;
    return `${h12}:${mStr} ${ampm}`;
  };

  const scheduledTimes = isTodayPlan && Array.isArray(plan?.commits) && plan.commits.length > 0
    ? plan.commits.map(c => formatTime(c.time)).join(', ')
    : 'None';

  const triggerRecalculate = async () => {
    try {
      const response = await fetch(`https://api.github.com/repos/${username}/autocommit-engine/actions/workflows/pattern_engine.yml/dispatches`, {
        method: 'POST',
        headers: {
          Authorization: `token ${pat}`,
          Accept: 'application/vnd.github.v3+json',
        },
        body: JSON.stringify({ ref: 'main' })
      });
      if (response.ok) {
        toast.success("Recalculating today's pattern...");
      } else {
        toast.error("Failed to trigger workflow");
      }
    } catch (e) {
      toast.error("Error triggering workflow");
    }
  };

  if (loading) return <div className="skeleton h-48 w-full rounded mb-4" />;

  return (
    <div className="card mb-4 border border-accent-emphasis/30 bg-canvas-subtle relative overflow-hidden">
      <div className="absolute top-0 right-0 p-3 flex items-center gap-2">
        <span className="text-[10px] font-bold text-accent-fg uppercase tracking-widest">ON</span>
        <div className="w-2 h-2 rounded-full bg-success-fg animate-pulse"></div>
      </div>
      
      <div className="flex items-center gap-2 mb-3">
        <div className="text-xl">🧠</div>
        <h3 className="text-sm font-bold text-fg">Smart Mode</h3>
      </div>
      
      <div className="text-xs text-fg-muted mb-4">Learning from your 60-day pattern</div>
      
      <div className="space-y-3 mb-4">
        <div className="flex justify-between items-center text-sm border-b border-border/50 pb-2">
          <span className="text-fg-subtle">Day {cycleDay} of cycle</span>
          <span className="font-mono text-fg">{dayNumber > 60 ? 'Extended' : 'Base Pattern'}</span>
        </div>
        
        <div className="bg-canvas p-3 rounded-lg border border-border">
          <div className="text-sm mb-1">
            <span className="text-fg-subtle">Today's planned commits: </span>
            <span className="font-bold text-success-fg text-base">{plannedCommits}</span>
          </div>
          <div className="text-xs text-fg-muted flex flex-wrap gap-1">
            {plannedCommits === 0 ? (
              <span className="text-fg-subtle italic">Rest day today 🛋️</span>
            ) : (
              <>
                <span>Scheduled times:</span>
                <span className="font-mono text-fg">{scheduledTimes}</span>
              </>
            )}
          </div>
        </div>
        
        {seed && seed.analyzed && (
          <div className="text-xs bg-canvas/50 p-3 rounded-lg border border-border/50">
            <div className="font-semibold text-fg mb-1">Pattern Stats:</div>
            <div className="grid grid-cols-2 gap-2 text-fg-subtle">
              <div>Avg/day: <span className="text-fg font-mono">{seed.analyzed.avg_commits}</span></div>
              <div>Rest days: <span className="text-fg font-mono">{(seed.analyzed.rest_day_ratio * 100).toFixed(1)}%</span></div>
              <div className="col-span-2">Last spike: Day <span className="text-fg font-mono">{seed.analyzed.spike_days[seed.analyzed.spike_days.length - 1]}</span></div>
            </div>
          </div>
        )}
      </div>

      <div className="text-[10px] text-fg-subtle mb-3 flex items-center gap-1.5">
        <Zap size={10} className="text-accent-fg" />
        After day 60: Gemini extends pattern
      </div>
      
      <button onClick={triggerRecalculate} className="btn btn-secondary w-full justify-center text-xs py-1.5">
        <RefreshCw size={13} /> Recalculate Today
      </button>
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
          <div className="mt-4 border-t border-border pt-4">
            <SmartModeCard username={owner} archiveRepo={archiveRepo} pat={pat} config={cfg} />
            <MonthlyExamDays username={owner} archiveRepo={archiveRepo} pat={pat} />
          </div>
        </div>
      )}
    </div>
    </>
  )
}
