import React, { useState, useMemo } from 'react'
import { List, ChevronUp, ChevronDown, CheckCircle, XCircle, MinusCircle } from 'lucide-react'
import { buildCommitLog, getCommitMode, getModeColor, formatDateDisplay } from '../lib/utils'

const MODE_FILTERS = ['All', 'Burst', 'Normal', 'Quiet', 'Rest']

const PAGE_SIZE = 10

function StatusIcon({ status }) {
  if (status === 'Pushed')  return <CheckCircle size={14} className="text-success-fg" />
  if (status === 'Failed')  return <XCircle     size={14} className="text-danger-fg" />
  return <MinusCircle size={14} className="text-fg-subtle" />
}

const formatTime = (timeStr) => {
  if (!timeStr) return '—';
  const [h, m] = timeStr.split(':');
  const hour = parseInt(h);
  const period = hour >= 12 ? 'PM' : 'AM';
  const hour12 = hour % 12 || 12;
  return `${hour12}:${m} ${period}`;
};

export default function CommitLogTable({ commitHistory, commitPlan, loading }) {
  const [filter, setFilter] = useState('All')
  const [sortAsc, setSortAsc] = useState(false)
  const [page, setPage] = useState(0)
  const [expandedRow, setExpandedRow] = useState(null)

  const allEntries = useMemo(() => buildCommitLog(commitHistory, commitPlan, 200), [commitHistory, commitPlan])

  const filtered = useMemo(() => {
    let entries = filter === 'All' ? allEntries : allEntries.filter(e => e.mode === filter)
    if (sortAsc) entries = [...entries].reverse()
    return entries
  }, [allEntries, filter, sortAsc])

  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)

  if (loading) {
    return (
      <div className="card">
        <div className="section-header">
          <div className="section-title flex items-center gap-2">
            <List size={16} className="text-fg-muted" />
            Commit Log
          </div>
        </div>
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="skeleton h-12 rounded" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="card">
      {/* Header + filters */}
      <div className="section-header flex-wrap gap-3">
        <div>
          <div className="section-title flex items-center gap-2">
            <List size={16} className="text-fg-muted" />
            Commit Log
          </div>
          <div className="section-subtitle">{filtered.length} entries</div>
        </div>

        {/* Mode filter chips */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {MODE_FILTERS.map(m => (
            <button
              key={m}
              id={`filter-${m.toLowerCase()}`}
              onClick={() => { setFilter(m); setPage(0) }}
              className={`
                px-2.5 py-1 rounded-full text-xs font-medium transition-all
                ${filter === m
                  ? 'bg-success-emphasis text-white'
                  : 'bg-canvas-subtle text-fg-muted hover:text-fg border border-border'}
              `}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto -mx-1">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: '15%' }}>
                <button
                  className="flex items-center gap-1 hover:text-fg transition-colors"
                  onClick={() => { setSortAsc(p => !p); setPage(0) }}
                >
                  DATE
                  {sortAsc ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
                </button>
              </th>
              <th style={{ width: '14%' }} className="hidden md:table-cell">TIME (IST)</th>
              <th style={{ width: '45%' }}>COMMIT MESSAGE</th>
              <th style={{ width: '12%' }} className="hidden md:table-cell">MODE</th>
              <th style={{ width: '14%' }}>STATUS</th>
            </tr>
          </thead>
          <tbody>
            {paged.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center text-fg-muted py-8 text-sm">
                  No commits match this filter.
                </td>
              </tr>
            ) : (
              paged.map((entry, i) => {
                const isRest = entry.mode === 'Rest'
                const key = `${entry.date}-${i}`
                return (
                  <tr
                    key={key}
                    className={`cursor-pointer ${isRest ? 'opacity-50' : ''}`}
                    onClick={() => setExpandedRow(expandedRow === key ? null : key)}
                  >
                    <td className="text-xs font-mono text-fg-muted">
                      {formatDateDisplay(entry.date)}
                    </td>
                    <td className="text-xs font-mono text-fg-subtle hidden md:table-cell">
                      {formatTime(entry.time)}
                    </td>
                    <td className="font-mono text-xs text-fg max-w-0">
                      <div
                        className={`
                          truncate transition-all
                          ${expandedRow === key ? 'whitespace-normal' : 'max-w-[300px]'}
                        `}
                        title={entry.message}
                      >
                        {isRest ? (
                          <span className="text-fg-subtle italic">REST DAY — no commits</span>
                        ) : (
                          entry.message
                        )}
                      </div>
                    </td>
                    <td className="hidden md:table-cell">
                      <span className={`badge text-[10px] font-semibold ${getModeColor(entry.mode)}`}>
                        {entry.mode}
                      </span>
                    </td>
                    <td>
                      <div className="flex items-center gap-1.5">
                        <StatusIcon status={entry.status} />
                        <span className="text-xs hidden sm:inline">{entry.status}</span>
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
          <button
            id="btn-prev-page"
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
            className="btn btn-ghost text-xs px-3 py-1.5"
          >
            ← Prev
          </button>
          <span className="text-xs text-fg-muted">
            Page {page + 1} of {totalPages}
          </span>
          <button
            id="btn-next-page"
            onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="btn btn-ghost text-xs px-3 py-1.5"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}
