import React from 'react'
import { Flame, Trophy, GitCommit, Shield, TrendingUp, ArrowUpRight } from 'lucide-react'
import { formatNumber } from '../lib/utils'

function StatCard({ title, value, subtitle, badge, badgeColor, icon: Icon, iconBg, iconColor, loading, trend }) {
  return (
    <div className="card group cursor-default animate-fade-in">
      <div className="flex items-start justify-between mb-3">
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${iconBg}`}>
          <Icon size={18} className={iconColor} />
        </div>
        {trend !== undefined && (
          <div className="flex items-center gap-1 text-xs text-success-fg">
            <ArrowUpRight size={12} />
            <span>+{trend} today</span>
          </div>
        )}
      </div>

      {loading ? (
        <div className="space-y-2">
          <div className="skeleton h-8 w-24 rounded" />
          <div className="skeleton h-3.5 w-32 rounded" />
        </div>
      ) : (
        <>
          <div className="text-3xl font-bold text-fg tracking-tight mb-1 group-hover:scale-105 transition-transform origin-left">
            {value ?? '—'}
          </div>
          <div className="text-xs text-fg-muted mb-2">{subtitle}</div>
          {badge && (
            <div className={`badge ${badgeColor || 'badge-gray'}`}>
              {badge}
            </div>
          )}
        </>
      )}

      <div className="text-[10px] font-semibold uppercase tracking-widest text-fg-subtle mt-3">
        {title}
      </div>
    </div>
  )
}

export default function StatsCards({ streakStats, qualityScore, commitHistory, loading }) {
  const currentStreak = streakStats?.current_streak ?? 0
  const longestStreak = streakStats?.longest_streak ?? 0
  const totalCommits  = streakStats?.total_commits ?? 0
  const score         = qualityScore?.score ?? 0
  const scoreLabel    = qualityScore?.status_label ?? 'Unknown'

  // Count today's commits
  const today = new Date().toISOString().split('T')[0]
  const todayCommits = Array.isArray(commitHistory?.[today])
    ? commitHistory[today].length
    : 0

  const scoreColor = score >= 75 ? 'badge-green' : score >= 60 ? 'badge-amber' : 'badge-red'
  const scoreIcon  = score >= 75 ? '🟢' : score >= 60 ? '🟡' : '🔴'

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard
        title="Current Streak"
        value={`${currentStreak} days`}
        subtitle="consecutive days"
        badge="+1 today"
        badgeColor="badge-green"
        icon={Flame}
        iconBg="bg-success-muted"
        iconColor="text-success-fg"
        loading={loading}
        trend={todayCommits > 0 ? 1 : undefined}
      />
      <StatCard
        title="Longest Streak"
        value={`${longestStreak} days`}
        subtitle="personal record"
        badge="All time"
        badgeColor="badge-blue"
        icon={Trophy}
        iconBg="bg-accent-muted"
        iconColor="text-accent-fg"
        loading={loading}
      />
      <StatCard
        title="Total Commits"
        value={formatNumber(totalCommits)}
        subtitle="auto-commits fired"
        badge="Since launch"
        badgeColor="badge-amber"
        icon={GitCommit}
        iconBg="bg-attention-muted"
        iconColor="text-attention-fg"
        loading={loading}
      />
      <StatCard
        title="Quality Score"
        value={`${score} / 100`}
        subtitle="naturalness score"
        badge={`${scoreIcon} ${scoreLabel}`}
        badgeColor={scoreColor}
        icon={Shield}
        iconBg="bg-done-muted"
        iconColor="text-done-fg"
        loading={loading}
      />
    </div>
  )
}
