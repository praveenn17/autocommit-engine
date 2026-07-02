import React, { useState, useEffect, useCallback } from 'react'
import { Toaster } from 'react-hot-toast'
import { Menu, X, RefreshCw, LogOut, GitCommit, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'

import LoginScreen    from './components/LoginScreen'
import Sidebar        from './components/Sidebar'
import StatsCards     from './components/StatsCards'
import ControlsPanel  from './components/ControlsPanel'
import CommitLogTable from './components/CommitLogTable'
import ContributionGraph from './components/ContributionGraph'
import AnalyticsPage  from './components/AnalyticsPage'
import NotificationsPage from './components/NotificationsPage'
import SelfDestructPanel from './components/SelfDestructPanel'
import NetworkWarning from './components/NetworkWarning'
import InterviewShield from './components/InterviewShield'
import NLScheduler from './components/NLScheduler'

import { loadDashboardData, triggerManualCommit, initOctokit } from './lib/github'
import { clearSettings, loadSettings } from './lib/utils'

// ---------------------------------------------------------------------------
// Error Banner
// ---------------------------------------------------------------------------
function ErrorBanner({ message, onDismiss }) {
  if (!message) return null
  return (
    <div className="px-4 py-2.5 bg-danger-muted border-b border-danger-fg/20 flex items-center justify-between text-xs text-danger-fg">
      <span>⚠ {message}</span>
      {onDismiss && (
        <button onClick={onDismiss} className="ml-3 text-danger-fg/60 hover:text-danger-fg">
          <X size={12} />
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main App
// ---------------------------------------------------------------------------
export default function App() {
  const [settings, setSettings]         = useState(null)
  const [activePage, setActivePage]     = useState('dashboard')
  const [isMobileOpen, setMobileOpen]   = useState(false)
  const [loading, setLoading]           = useState(false)
  const [refreshing, setRefreshing]     = useState(false)
  const [manualFiring, setManualFiring] = useState(false)
  const [banner, setBanner]             = useState('')

  // Dashboard data
  const [commitHistory, setCommitHistory] = useState({})
  const [streakStats,   setStreakStats]   = useState({})
  const [qualityScore,  setQualityScore]  = useState({})
  const [config,        setConfig]        = useState({})
  const [configSha,     setConfigSha]     = useState(null)
  const [commitPlan,    setCommitPlan]    = useState(null)

  // ---------------------------------------------------------------------------
  // Load settings from localStorage on mount (auto-login)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const saved = loadSettings()
    if (saved?.token && saved?.username) {
      initOctokit(saved.token)
      setSettings(saved)
    }
  }, [])

  // ---------------------------------------------------------------------------
  // Fetch data from archive repo
  // ---------------------------------------------------------------------------
  const fetchData = useCallback(async (settingsOverride) => {
    const s = settingsOverride || settings
    if (!s) return
    setLoading(true)
    setBanner('')
    try {
      const data = await loadDashboardData(s.username, s.archiveRepo)
      setCommitHistory(data.commitHistory || {})
      setStreakStats(data.streakStats     || {})
      setQualityScore(data.qualityScore   || {})
      setConfig(data.config               || {})
      setConfigSha(data.configSha)
      setCommitPlan(data.commitPlan       || null)
    } catch (err) {
      if (err.status === 401 || err.message?.includes('401')) {
        setBanner('Token expired. Click here to update your PAT.')
      } else if (err.status === 404) {
        setBanner('Archive repo not found. Check setup guide.')
      } else if (err.status === 403) {
        setBanner('GitHub API rate limited — showing cached data')
      } else {
        setBanner(`Data load error: ${err.message}`)
      }
    } finally {
      setLoading(false)
    }
  }, [settings])

  useEffect(() => {
    if (settings) fetchData()
  }, [settings])

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------
  const handleLogin = useCallback((s) => {
    setSettings(s)
    initOctokit(s.token)
  }, [])

  const handleLogout = useCallback(() => {
    clearSettings()
    localStorage.removeItem('nl_scheduler_history')
    setSettings(null)
    setCommitHistory({})
    setStreakStats({})
    setQualityScore({})
    setConfig({})
    setConfigSha(null)
    setCommitPlan(null)
    setBanner('')
    setActivePage('dashboard')
  }, [])

  const handleRefresh = useCallback(async () => {
    setRefreshing(true)
    await fetchData()
    setRefreshing(false)
    toast.success('Dashboard refreshed')
  }, [fetchData])

  const handleManualCommit = useCallback(async () => {
    if (!settings?.projectRepo) {
      toast.error('Set your project repo name in settings to trigger commits.')
      return
    }
    setManualFiring(true)
    try {
      await triggerManualCommit(settings.username, settings.projectRepo)
      toast.success('Manual commit triggered! Check GitHub Actions.')
    } catch (err) {
      toast.error(`Failed: ${err.message}`)
    } finally {
      setManualFiring(false)
    }
  }, [settings])

  // ---------------------------------------------------------------------------
  // Not logged in
  // ---------------------------------------------------------------------------
  if (!settings) {
    return (
      <>
        <Toaster position="top-right" toastOptions={{ style: { background: '#161b22', color: '#e6edf3', border: '1px solid #30363d' } }} />
        <LoginScreen onLogin={handleLogin} />
      </>
    )
  }

  // ---------------------------------------------------------------------------
  // Main layout
  // ---------------------------------------------------------------------------
  const systemActive = config?.active !== false

  const renderPage = () => {
    switch (activePage) {
      case 'dashboard':
        return (
          <div className="space-y-5 animate-fade-in">
            {/* Stats row */}
            <StatsCards
              streakStats={streakStats}
              qualityScore={qualityScore}
              commitHistory={commitHistory}
              loading={loading}
            />

            {/* Controls + action buttons row */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2">
                <ControlsPanel
                  config={config}
                  configSha={configSha}
                  owner={settings.username}
                  archiveRepo={settings.archiveRepo}
                  onConfigUpdate={(newCfg) => setConfig(newCfg)}
                  loading={loading}
                />
              </div>
              <div className="space-y-3">
                {/* Archive repo status */}
                <div className="card">
                  <div className="section-title mb-2 text-sm">Archive Status</div>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between">
                      <span className="text-fg-muted">Repo</span>
                      <span className="font-mono text-fg">{settings.username}/{settings.archiveRepo}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-fg-muted">Total commits</span>
                      <span className="text-fg">{(streakStats?.total_commits ?? 0).toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-fg-muted">Quality</span>
                      <span className={qualityScore?.score >= 75 ? 'text-success-fg' : qualityScore?.score >= 60 ? 'text-attention-fg' : 'text-danger-fg'}>
                        {qualityScore?.score ?? '—'}/100
                      </span>
                    </div>
                  </div>
                </div>

                {/* Manual commit button */}
                <button
                  id="btn-manual-commit"
                  onClick={handleManualCommit}
                  disabled={manualFiring || !settings.projectRepo}
                  className="btn btn-primary w-full justify-center text-sm"
                  title={!settings.projectRepo ? 'Add project repo name in settings' : ''}
                >
                  {manualFiring ? (
                    <><Loader2 size={14} className="animate-spin" /> Firing…</>
                  ) : (
                    <><GitCommit size={14} /> Manual Commit</>
                  )}
                </button>
              </div>
            </div>

            {/* Recent commits (last 10) */}
            <CommitLogTable
              commitHistory={commitHistory}
              commitPlan={commitPlan}
              loading={loading}
            />

            {/* Contribution graph — always last */}
            <ContributionGraph
              username={settings.username}
              token={settings.token}
              commitHistory={commitHistory}
              loading={loading}
            />
          </div>
        )

      case 'controls':
        return (
          <div className="max-w-2xl animate-fade-in">
            <ControlsPanel
              config={config}
              configSha={configSha}
              owner={settings.username}
              archiveRepo={settings.archiveRepo}
              onConfigUpdate={(newCfg) => setConfig(newCfg)}
              loading={loading}
            />
          </div>
        )

      case 'analytics':
        return (
          <AnalyticsPage
            commitHistory={commitHistory}
            qualityScore={qualityScore}
            streakStats={streakStats}
            loading={loading}
          />
        )

      case 'commitlog':
        return (
          <CommitLogTable
            commitHistory={commitHistory}
            commitPlan={commitPlan}
            loading={loading}
          />
        )

      case 'notifications':
        return (
          <NotificationsPage config={config} />
        )

      case 'shield':
        return (
          <InterviewShield />
        )

      case 'nlscheduler':
        return (
          <NLScheduler />
        )

      case 'selfdestruct':
        return (
          <SelfDestructPanel username={settings.username} />
        )

      default:
        return null
    }
  }

  const PAGE_TITLES = {
    dashboard:     'Live Dashboard',
    controls:      'Controls',
    analytics:     'Analytics',
    commitlog:     'Commit Log',
    notifications: 'Notifications',
    shield:        '🛡️ Interview Shield',
    nlscheduler:   '🤖 AI Scheduler',
    selfdestruct:  'Self-Destruct',
  }

  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#161b22',
            color: '#e6edf3',
            border: '1px solid #30363d',
            fontSize: '13px',
          },
          success: { iconTheme: { primary: '#3fb950', secondary: '#0d1117' } },
          error:   { iconTheme: { primary: '#f85149', secondary: '#0d1117' } },
        }}
      />

      {/* Sidebar */}
      <Sidebar
        activePage={activePage}
        setActivePage={setActivePage}
        username={settings.username}
        systemActive={systemActive}
        isMobileOpen={isMobileOpen}
        setMobileOpen={setMobileOpen}
        onLogout={handleLogout}
      />

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Network miss warning — always visible above error banner */}
        <NetworkWarning streakStats={streakStats} loading={loading} />

        {/* Error banner */}
        <ErrorBanner message={banner} onDismiss={() => setBanner('')} />

        {/* Top bar */}
        <header className="flex-shrink-0 flex items-center justify-between px-5 py-3.5 border-b border-border bg-canvas-subtle">
          {/* Mobile hamburger */}
          <button
            id="btn-mobile-menu"
            className="md:hidden text-fg-muted hover:text-fg transition-colors mr-3"
            onClick={() => setMobileOpen(p => !p)}
            aria-label="Toggle navigation"
          >
            {isMobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>

          <div>
            <h1 className="text-base font-semibold text-fg">{PAGE_TITLES[activePage]}</h1>
            <div className="text-xs text-fg-muted hidden sm:block">
              {systemActive
                ? <span className="text-success-fg">● System Running</span>
                : <span className="text-fg-subtle">● System Paused</span>
              }
              {' · '}
              <span className="font-mono">{settings.username}/{settings.archiveRepo}</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Refresh */}
            <button
              id="btn-refresh"
              onClick={handleRefresh}
              disabled={refreshing}
              className="btn btn-ghost text-xs px-2.5 py-1.5"
              title="Refresh dashboard data"
            >
              <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
              <span className="hidden sm:inline">Refresh</span>
            </button>

            {/* Logout */}
            <button
              id="btn-logout"
              onClick={handleLogout}
              className="btn btn-ghost text-xs px-2.5 py-1.5 text-fg-muted hover:text-danger-fg"
              title="Disconnect"
            >
              <LogOut size={13} />
              <span className="hidden sm:inline">Disconnect</span>
            </button>
          </div>
        </header>

        {/* Page content */}
        <main
          id="main-content"
          className="flex-1 overflow-y-auto p-5"
        >
          {renderPage()}
        </main>
      </div>
    </div>
  )
}
