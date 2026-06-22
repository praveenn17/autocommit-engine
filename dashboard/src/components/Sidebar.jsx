import React, { useState } from 'react'
import { Zap, BarChart2, Settings, List, Bell, Skull, CircleDot, ShieldCheck, Bot, LogOut } from 'lucide-react'

const NAV_ITEMS = [
  { id: 'dashboard',     label: 'Dashboard',     icon: Zap },
  { id: 'controls',      label: 'Controls',      icon: Settings },
  { id: 'analytics',     label: 'Analytics',     icon: BarChart2 },
  { id: 'commitlog',     label: 'Commit Log',    icon: List },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'shield',        label: '🛡️ Shield',        icon: ShieldCheck },
  { id: 'nlscheduler',   label: '🤖 AI Scheduler',  icon: Bot },
  { id: 'selfdestruct',  label: 'Self-Destruct',   icon: Skull, danger: true },
]

export default function Sidebar({ activePage, setActivePage, username, systemActive, isMobileOpen, setMobileOpen, onLogout }) {
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)

  return (
    <>
      {/* Mobile overlay */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-40 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={`
          fixed top-0 left-0 h-full z-50 flex flex-col
          w-[240px] bg-canvas border-r border-border
          transition-transform duration-300 ease-in-out
          ${isMobileOpen ? 'translate-x-0' : '-translate-x-full'}
          md:translate-x-0 md:static md:z-auto
        `}
        style={{ minHeight: '100vh' }}
      >
        {/* ── Logo area ───────────────────────────────────────────── */}
        <div className="flex flex-col gap-2 px-5 pt-6 pb-4 border-b border-border">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-success-muted flex items-center justify-center">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="#3fb950" strokeWidth="1.5" />
                <path d="M8 12l3 3 5-6" stroke="#3fb950" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <div>
              <div className="text-sm font-bold text-fg leading-none">AutoCommit</div>
              <div className="text-[10px] text-fg-muted mt-0.5 font-mono">Generator v1.0</div>
            </div>
          </div>

          {/* System status pill */}
          <div
            className={`
              inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
              ${systemActive
                ? 'bg-success-muted text-success-fg'
                : 'bg-border-muted text-fg-muted'}
            `}
          >
            {systemActive ? (
              <>
                <span className="pulse-dot" />
                System Active
              </>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full bg-fg-subtle inline-block" />
                System Paused
              </>
            )}
          </div>
        </div>

        {/* ── Navigation ──────────────────────────────────────────── */}
        <nav className="flex-1 px-3 py-4 overflow-y-auto no-scrollbar">
          <div className="text-[10px] font-semibold text-fg-subtle uppercase tracking-widest px-3 mb-2">
            Navigation
          </div>
          <ul className="space-y-0.5">
            {NAV_ITEMS.map(({ id, label, icon: Icon, danger }) => (
              <li key={id}>
                <button
                  id={`nav-${id}`}
                  onClick={() => {
                    setActivePage(id)
                    setMobileOpen(false)
                  }}
                  className={`
                    nav-item w-full text-left
                    ${activePage === id ? 'active' : ''}
                    ${danger ? 'danger' : ''}
                  `}
                >
                  <Icon size={16} className="flex-shrink-0" />
                  {label}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        {/* ── Status footer ────────────────────────────────────────── */}
        <div className="px-5 py-4 border-t border-border">
          {showLogoutConfirm ? (
            <div className="flex flex-col gap-2 animate-fade-in">
              <div className="text-xs text-fg-muted text-center font-medium">Are you sure?</div>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowLogoutConfirm(false)}
                  className="btn btn-ghost flex-1 text-xs justify-center py-1.5"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    setShowLogoutConfirm(false)
                    if (onLogout) onLogout()
                  }}
                  className="btn bg-danger-muted text-danger-fg hover:bg-danger-muted/80 flex-1 text-xs justify-center py-1.5 border border-danger-fg/20"
                >
                  Yes, Log Out
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3 animate-fade-in">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-canvas-subtle border border-border flex items-center justify-center">
                  <CircleDot size={14} className="text-fg-muted" />
                </div>
                <div>
                  <div className="text-xs font-medium text-fg truncate max-w-[140px]">
                    {username || 'Not configured'}
                  </div>
                  <div className="text-[10px] text-fg-subtle">GitHub account</div>
                </div>
              </div>
              <button
                onClick={() => setShowLogoutConfirm(true)}
                className="flex items-center justify-center gap-2 w-full py-1.5 text-xs font-medium text-fg-muted hover:text-danger-fg hover:bg-danger-muted/10 rounded-lg transition-colors border border-transparent hover:border-danger-fg/10"
              >
                <LogOut size={14} />
                Log Out
              </button>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
