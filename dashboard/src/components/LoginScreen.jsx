import React, { useState, useCallback } from 'react'
import { Zap, Eye, EyeOff, Loader2, Github, AlertCircle, Lock } from 'lucide-react'
import { verifyToken, initOctokit } from '../lib/github'
import { saveSettings, loadSettings } from '../lib/utils'

export default function LoginScreen({ onLogin }) {
  const saved = loadSettings()

  const [token,       setToken]       = useState(saved?.token ?? '')
  const [username,    setUsername]    = useState(saved?.username ?? '')
  const [archiveRepo, setArchiveRepo] = useState(saved?.archiveRepo ?? 'commit-archive')
  const [projectRepo, setProjectRepo] = useState(saved?.projectRepo ?? '')
  const [showToken,   setShowToken]   = useState(false)
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState('')

  const handleConnect = useCallback(async () => {
    if (!token || !username || !archiveRepo) {
      setError('GitHub Token, Username, and Archive Repo are required.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const result = await verifyToken(token)
      if (!result.valid) {
        setError(result.error || 'Invalid token — check PAT and try again.')
        return
      }
      initOctokit(token)
      const settings = { token, username, archiveRepo, projectRepo }
      saveSettings(settings)
      onLogin(settings)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [token, username, archiveRepo, projectRepo, onLogin])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleConnect()
  }

  return (
    <div className="min-h-screen bg-canvas flex items-center justify-center p-4 relative overflow-hidden">
      {/* Animated background grid */}
      <div
        className="absolute inset-0 opacity-20 pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(63,185,80,0.3) 1px, transparent 0)',
          backgroundSize: '32px 32px',
        }}
      />
      {/* Gradient orbs */}
      <div className="absolute top-1/4 left-1/4 w-64 h-64 bg-success-emphasis/10 rounded-full blur-3xl pointer-events-none animate-pulse-slow" />
      <div className="absolute bottom-1/3 right-1/4 w-48 h-48 bg-accent-emphasis/10 rounded-full blur-3xl pointer-events-none animate-pulse-slow" style={{ animationDelay: '1s' }} />

      <div className="w-full max-w-md relative z-10 animate-slide-up">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-success-muted border border-success-emphasis/30 mb-4 animate-glow">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="#3fb950" strokeWidth="1.5" />
              <path d="M8 12l3 3 5-6" stroke="#3fb950" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-fg">AutoCommit Generator</h1>
          <p className="text-sm text-fg-muted mt-1">Control Dashboard v1.0</p>
        </div>

        {/* Login card */}
        <div className="bg-canvas-subtle border border-border rounded-2xl p-6 shadow-2xl shadow-black/40">
          <div className="flex items-center gap-2 mb-5">
            <Github size={16} className="text-fg-muted" />
            <span className="text-sm font-semibold text-fg">Connect GitHub Account</span>
          </div>

          <div className="space-y-4">
            {/* GitHub Username */}
            <div>
              <label className="block text-xs font-medium text-fg-muted mb-1.5" htmlFor="login-username">
                GitHub Username
              </label>
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="yourusername"
                className="w-full bg-canvas border border-border rounded-lg px-3 py-2.5 text-sm text-fg font-mono placeholder:text-fg-subtle focus:outline-none focus:border-accent-fg transition-colors"
                autoComplete="username"
              />
            </div>

            {/* PAT */}
            <div>
              <label className="block text-xs font-medium text-fg-muted mb-1.5" htmlFor="login-token">
                Personal Access Token
              </label>
              <div className="relative">
                <input
                  id="login-token"
                  type={showToken ? 'text' : 'password'}
                  value={token}
                  onChange={e => setToken(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                  className="w-full bg-canvas border border-border rounded-lg px-3 py-2.5 pr-10 text-sm text-fg font-mono placeholder:text-fg-subtle focus:outline-none focus:border-accent-fg transition-colors"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowToken(p => !p)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-fg-subtle hover:text-fg transition-colors"
                  aria-label="Toggle token visibility"
                >
                  {showToken ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              <div className="text-[10px] text-fg-subtle mt-1 flex items-center gap-1">
                <Lock size={9} />
                Stored in localStorage only. Never sent to any external server.
              </div>
            </div>

            {/* Archive Repo */}
            <div>
              <label className="block text-xs font-medium text-fg-muted mb-1.5" htmlFor="login-archive-repo">
                Archive Repo Name
              </label>
              <input
                id="login-archive-repo"
                type="text"
                value={archiveRepo}
                onChange={e => setArchiveRepo(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="commit-archive"
                className="w-full bg-canvas border border-border rounded-lg px-3 py-2.5 text-sm text-fg font-mono placeholder:text-fg-subtle focus:outline-none focus:border-accent-fg transition-colors"
              />
              <div className="text-[10px] text-fg-subtle mt-1">The private repo where commits are stored.</div>
            </div>

            {/* Project Repo (optional) */}
            <div>
              <label className="block text-xs font-medium text-fg-muted mb-1.5" htmlFor="login-project-repo">
                Project Repo Name <span className="text-fg-subtle">(optional)</span>
              </label>
              <input
                id="login-project-repo"
                type="text"
                value={projectRepo}
                onChange={e => setProjectRepo(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="my-project"
                className="w-full bg-canvas border border-border rounded-lg px-3 py-2.5 text-sm text-fg font-mono placeholder:text-fg-subtle focus:outline-none focus:border-accent-fg transition-colors"
              />
              <div className="text-[10px] text-fg-subtle mt-1">Needed for manual workflow trigger and self-destruct.</div>
            </div>

            {/* Error */}
            {error && (
              <div className="flex items-start gap-2 px-3 py-2.5 bg-danger-muted border border-danger-fg/20 rounded-lg text-xs text-danger-fg">
                <AlertCircle size={13} className="flex-shrink-0 mt-0.5" />
                {error}
              </div>
            )}

            {/* Connect button */}
            <button
              id="btn-connect"
              onClick={handleConnect}
              disabled={loading || !token || !username}
              className="btn btn-primary w-full justify-center py-3 text-sm"
            >
              {loading ? (
                <><Loader2 size={15} className="animate-spin" /> Verifying…</>
              ) : (
                <><Zap size={15} /> Connect Dashboard</>
              )}
            </button>
          </div>
        </div>

        {/* PAT scope note */}
        <div className="mt-4 text-center text-[10px] text-fg-subtle space-y-1">
          <div>Required PAT scope: <span className="mono">repo</span> (full repository access)</div>
          <div>Settings → Developer Settings → Personal Access Tokens → Tokens (classic)</div>
        </div>
      </div>
    </div>
  )
}
