import React, { useState, useEffect, useRef } from 'react'
import { RefreshCw, ExternalLink } from 'lucide-react'
import { fetchContributionGraph } from '../lib/github'
import { format, parseISO } from 'date-fns'

// GitHub contribution graph colours (exact match)
const LEVEL_COLORS = ['#161b22', '#0e4429', '#006d32', '#26a641', '#39d353']

function getLevel(count) {
  if (count === 0) return 0
  if (count === 1) return 1
  if (count <= 3)  return 2
  if (count <= 6)  return 3
  return 4
}

function ContributionCell({ day, commitHistory }) {
  const [tooltip, setTooltip] = useState(null)
  const [pos, setPos] = useState({ x: 0, y: 0 })

  const count   = day?.contributionCount ?? 0
  const dateStr = day?.date ?? ''
  const level   = getLevel(count)
  const color   = LEVEL_COLORS[level]

  const localMsgs = commitHistory?.[dateStr]
  const isAutoCommit = Array.isArray(localMsgs) && localMsgs.length > 0

  const handleMouseEnter = (e) => {
    const rect = e.target.getBoundingClientRect()
    const formatted = dateStr ? format(parseISO(dateStr), 'MMM d, yyyy') : ''
    setTooltip({ date: formatted, count, isAutoCommit, msgs: localMsgs })
    setPos({ x: rect.left, y: rect.top })
  }

  return (
    <g>
      <rect
        width="11"
        height="11"
        rx="2"
        ry="2"
        fill={color}
        className="transition-opacity duration-150 hover:opacity-80 cursor-default"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={() => setTooltip(null)}
      />
      {tooltip && (
        <foreignObject x={0} y={-60} width={200} height={60} style={{ overflow: 'visible' }}>
          <div
            className="
              absolute z-50 bg-canvas border border-border rounded-lg p-2.5
              text-xs text-fg shadow-xl pointer-events-none whitespace-nowrap
            "
            style={{ transform: 'translate(-50%, -100%)' }}
          >
            <div className="font-semibold">{tooltip.date}</div>
            <div className="text-fg-muted">
              {tooltip.count === 0 ? 'No contributions' : `${tooltip.count} contribution${tooltip.count > 1 ? 's' : ''}`}
            </div>
            {tooltip.isAutoCommit && (
              <div className="text-success-fg mt-0.5">🤖 AutoCommit</div>
            )}
          </div>
        </foreignObject>
      )}
    </g>
  )
}

export default function ContributionGraph({ username, token, commitHistory, loading: externalLoading }) {
  const [graphData, setGraphData] = useState(null)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState(null)
  const [lastFetched, setLastFetched] = useState(null)

  const CELL_SIZE = 12
  const CELL_GAP  = 3
  const CELL_STEP = CELL_SIZE + CELL_GAP

  const fetchGraph = async () => {
    if (!username || !token) return
    setLoading(true)
    setError(null)
    try {
      const data = await fetchContributionGraph(username, token)
      setGraphData(data)
      setLastFetched(new Date())
    } catch (err) {
      if (err.message?.includes('401')) {
        setError('Token expired or lacks read:user scope.')
      } else if (err.message?.includes('429')) {
        setError('GitHub API rate limited — showing cached data')
      } else {
        setError(err.message)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchGraph()
  }, [username, token])

  // Build month labels from weeks data
  const monthLabels = []
  let prevMonth = null
  const weeks = graphData?.weeks || []
  weeks.forEach((week, wIdx) => {
    const firstDay = week.contributionDays?.[0]
    if (firstDay?.date) {
      const month = parseISO(firstDay.date).getMonth()
      if (month !== prevMonth) {
        monthLabels.push({ idx: wIdx, label: format(parseISO(firstDay.date), 'MMM') })
        prevMonth = month
      }
    }
  })

  const svgWidth  = weeks.length * CELL_STEP + 32
  const svgHeight = 7 * CELL_STEP + 28

  return (
    <div className="card">
      <div className="section-header">
        <div>
          <div className="section-title flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-success-fg animate-pulse" />
            GitHub Contribution Graph
          </div>
          <div className="section-subtitle flex items-center gap-2">
            Live · via GitHub API ·{' '}
            {username ? (
              <a
                href={`https://github.com/${username}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent-fg hover:underline inline-flex items-center gap-0.5"
              >
                {username}
                <ExternalLink size={10} />
              </a>
            ) : (
              'not configured'
            )}
          </div>
        </div>

        <button
          id="btn-refresh-graph"
          onClick={fetchGraph}
          disabled={loading}
          className="btn btn-ghost text-xs px-2.5 py-1.5"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-attention-muted border border-attention-fg/20 text-xs text-attention-fg">
          ⚠ {error}
        </div>
      )}

      {loading || externalLoading ? (
        /* Grey placeholder grid */
        <div className="overflow-x-auto no-scrollbar">
          <svg
            width={52 * CELL_STEP + 32}
            height={svgHeight}
            className="min-w-max"
          >
            {Array.from({ length: 52 }).map((_, wIdx) =>
              Array.from({ length: 7 }).map((_, dIdx) => (
                <rect
                  key={`${wIdx}-${dIdx}`}
                  x={32 + wIdx * CELL_STEP}
                  y={20 + dIdx * CELL_STEP}
                  width={CELL_SIZE}
                  height={CELL_SIZE}
                  rx="2"
                  fill={LEVEL_COLORS[0]}
                  className="animate-pulse"
                  style={{ animationDelay: `${(wIdx * 7 + dIdx) * 5}ms` }}
                />
              ))
            )}
          </svg>
        </div>
      ) : !graphData ? (
        <div className="text-center py-8 text-fg-muted text-sm">
          {!username ? (
            <span>Configure your GitHub username to see the contribution graph.</span>
          ) : (
            <span>Failed to load contribution graph.</span>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto no-scrollbar">
          <svg
            width={svgWidth}
            height={svgHeight}
            className="min-w-max"
            role="img"
            aria-label="GitHub contribution graph"
          >
            {/* Month labels */}
            {monthLabels.map(({ idx, label }) => (
              <text
                key={`${idx}-${label}`}
                x={32 + idx * CELL_STEP}
                y={12}
                fill="#8b949e"
                fontSize="10"
                fontFamily="Inter, sans-serif"
              >
                {label}
              </text>
            ))}

            {/* Day labels (Mon, Wed, Fri) */}
            {['', 'Mon', '', 'Wed', '', 'Fri', ''].map((label, i) => (
              label && (
                <text
                  key={`day-${i}`}
                  x={0}
                  y={20 + i * CELL_STEP + 9}
                  fill="#8b949e"
                  fontSize="10"
                  fontFamily="Inter, sans-serif"
                >
                  {label}
                </text>
              )
            ))}

            {/* Contribution cells */}
            {weeks.map((week, wIdx) =>
              week.contributionDays?.map((day, dIdx) => (
                <g
                  key={`${wIdx}-${dIdx}`}
                  transform={`translate(${32 + wIdx * CELL_STEP}, ${20 + dIdx * CELL_STEP})`}
                >
                  <ContributionCell day={day} commitHistory={commitHistory} />
                </g>
              ))
            )}
          </svg>

          {/* Legend */}
          <div className="flex items-center justify-end gap-1.5 mt-2 text-[10px] text-fg-muted">
            <span>Less</span>
            {LEVEL_COLORS.map((c, i) => (
              <div
                key={i}
                className="w-3 h-3 rounded-sm"
                style={{ backgroundColor: c }}
                title={`Level ${i}`}
              />
            ))}
            <span>More</span>
          </div>
        </div>
      )}

      {lastFetched && (
        <div className="mt-2 text-[10px] text-fg-subtle text-right">
          Last fetched: {format(lastFetched, 'HH:mm:ss')}
        </div>
      )}
    </div>
  )
}
