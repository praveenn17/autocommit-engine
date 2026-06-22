import React, { useMemo } from 'react'
import { BarChart2, Activity } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, RadialBarChart, RadialBar, PieChart, Pie, Legend,
} from 'recharts'
import { getLastNDays, getQualityStatus, formatDateDisplay } from '../lib/utils'

// 12-week heatmap
function WeeklyHeatmap({ commitHistory }) {
  const days = getLastNDays(84) // 12 weeks
  const weeks = []
  for (let w = 0; w < 12; w++) {
    weeks.push(days.slice(w * 7, w * 7 + 7))
  }

  const getColor = (count) => {
    if (count === 0) return '#161b22'
    if (count === 1) return '#0e4429'
    if (count <= 3)  return '#006d32'
    if (count <= 6)  return '#26a641'
    return '#39d353'
  }

  return (
    <div>
      <div className="text-xs font-semibold text-fg-muted mb-2 uppercase tracking-wider">
        Last 12 Weeks
      </div>
      <div className="flex gap-1">
        {weeks.map((week, wIdx) => (
          <div key={wIdx} className="flex flex-col gap-1">
            {week.map((date, dIdx) => {
              const msgs = commitHistory[date]
              const count = Array.isArray(msgs) ? msgs.length : 0
              return (
                <div
                  key={dIdx}
                  title={`${formatDateDisplay(date)}: ${count} commits`}
                  className="w-3 h-3 rounded-sm cursor-default transition-opacity hover:opacity-75"
                  style={{ backgroundColor: getColor(count) }}
                />
              )
            })}
          </div>
        ))}
      </div>
      <div className="flex items-center gap-1.5 mt-2 text-[10px] text-fg-muted">
        <span>Less</span>
        {['#161b22', '#0e4429', '#006d32', '#26a641', '#39d353'].map((c, i) => (
          <div key={i} className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: c }} />
        ))}
        <span>More</span>
      </div>
    </div>
  )
}

// Quality score radial gauge
function QualityGauge({ score }) {
  const { label, color } = getQualityStatus(score)
  const data = [{ name: 'score', value: score, fill: '#39d353' }]
  const gaugeColor = score >= 75 ? '#3fb950' : score >= 60 ? '#d29922' : '#f85149'

  return (
    <div className="flex flex-col items-center">
      <div className="text-xs font-semibold text-fg-muted mb-1 uppercase tracking-wider">
        Quality Gauge
      </div>
      <div className="relative w-32 h-32">
        <RadialBarChart
          width={128}
          height={128}
          cx={64}
          cy={64}
          innerRadius={45}
          outerRadius={60}
          startAngle={90}
          endAngle={-270}
          data={[{ value: score }]}
        >
          <RadialBar
            dataKey="value"
            cornerRadius={6}
            fill={gaugeColor}
            background={{ fill: '#21262d' }}
          />
        </RadialBarChart>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-2xl font-bold" style={{ color: gaugeColor }}>{score}</div>
          <div className="text-[10px] text-fg-muted">/100</div>
        </div>
      </div>
      <div className={`badge mt-1 ${score >= 75 ? 'badge-green' : score >= 60 ? 'badge-amber' : 'badge-red'}`}>
        {label}
      </div>
    </div>
  )
}

// Daily bar chart for last 30 days
function DailyBarChart({ commitHistory }) {
  const days = getLastNDays(30)
  const data = days.map(date => {
    const msgs = commitHistory[date]
    return {
      date: formatDateDisplay(date),
      commits: Array.isArray(msgs) ? msgs.length : 0,
    }
  })

  return (
    <div>
      <div className="text-xs font-semibold text-fg-muted mb-2 uppercase tracking-wider">
        Last 30 Days — Daily Commits
      </div>
      <ResponsiveContainer width="100%" height={120}>
        <BarChart data={data} margin={{ top: 4, right: 4, left: -28, bottom: 0 }}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: '#6e7681' }}
            interval={4}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 9, fill: '#6e7681' }}
            axisLine={false}
            tickLine={false}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0d1117',
              border: '1px solid #30363d',
              borderRadius: '8px',
              fontSize: '11px',
              color: '#e6edf3',
            }}
            cursor={{ fill: 'rgba(255,255,255,0.04)' }}
          />
          <Bar dataKey="commits" radius={[3, 3, 0, 0]}>
            {data.map((entry, index) => (
              <Cell
                key={index}
                fill={
                  entry.commits === 0 ? '#21262d' :
                  entry.commits <= 3 ? '#26a641' : '#39d353'
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// Signal breakdown table
function SignalBreakdown({ signals }) {
  if (!signals || Object.keys(signals).length === 0) return null

  return (
    <div>
      <div className="text-xs font-semibold text-fg-muted mb-2 uppercase tracking-wider">
        Quality Signal Breakdown
      </div>
      <div className="space-y-2">
        {Object.entries(signals).map(([name, data]) => {
          const pct = (data.score / data.max) * 100
          return (
            <div key={name}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-fg capitalize">
                  {name.replace(/_/g, ' ')}
                </span>
                <span className={`text-xs font-mono ${data.passed ? 'text-success-fg' : 'text-danger-fg'}`}>
                  {data.score}/{data.max}
                </span>
              </div>
              <div className="h-1.5 bg-canvas-inset rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${pct}%`,
                    backgroundColor: data.passed ? '#3fb950' : '#f85149',
                  }}
                />
              </div>
              <div className="text-[10px] text-fg-subtle mt-0.5">{data.note}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function AnalyticsPage({ commitHistory, qualityScore, streakStats, loading }) {
  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map(i => <div key={i} className="card skeleton h-40" />)}
      </div>
    )
  }

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-2 pb-1">
        <BarChart2 size={20} className="text-fg-muted" />
        <div>
          <h2 className="text-lg font-semibold text-fg">Analytics</h2>
          <p className="text-xs text-fg-muted">Commit pattern analysis and quality metrics</p>
        </div>
      </div>

      {/* Quality gauge + signal breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card flex items-center justify-center">
          <QualityGauge score={qualityScore?.score ?? 0} />
        </div>
        <div className="card">
          <SignalBreakdown signals={qualityScore?.signals} />
        </div>
      </div>

      {/* Daily bar chart */}
      <div className="card">
        <DailyBarChart commitHistory={commitHistory} />
      </div>

      {/* 12-week heatmap */}
      <div className="card">
        <WeeklyHeatmap commitHistory={commitHistory} />
      </div>

      {/* Stats summary */}
      <div className="card">
        <div className="text-xs font-semibold text-fg-muted mb-3 uppercase tracking-wider">
          System Statistics
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          {[
            { label: 'Current Streak', value: `${streakStats?.current_streak ?? 0} days` },
            { label: 'Longest Streak', value: `${streakStats?.longest_streak ?? 0} days` },
            { label: 'Total Commits', value: (streakStats?.total_commits ?? 0).toLocaleString() },
            { label: 'Quality Score', value: `${qualityScore?.score ?? 0}/100` },
            { label: 'Quality Status', value: qualityScore?.status_label ?? '—' },
            { label: 'Analysis Days', value: `${qualityScore?.analysis_days ?? 30}d` },
          ].map(({ label, value }) => (
            <div key={label}>
              <div className="text-[10px] text-fg-subtle uppercase tracking-wider">{label}</div>
              <div className="text-sm font-semibold text-fg mt-0.5">{value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
