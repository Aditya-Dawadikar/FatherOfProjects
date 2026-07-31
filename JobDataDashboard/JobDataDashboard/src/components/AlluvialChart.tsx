import { useMemo, useState } from 'react'
import type { PipelineFunnel } from '../types'

type AlluvialChartProps = {
  funnel: PipelineFunnel
}

type FlowNode = {
  id: string
  label: string
  value: number
  column: number
  fill: string
  textColor: 'light' | 'dark'
}

type FlowLink = {
  id: string
  source: string
  target: string
  value: number
}

type LaidOutNode = FlowNode & { x: number; y0: number; y1: number }
type LaidOutLink = FlowLink & { sx: number; sy0: number; sy1: number; tx: number; ty0: number; ty1: number; fill: string }

type HoverTarget =
  | { kind: 'node'; node: LaidOutNode }
  | { kind: 'link'; link: LaidOutLink; sourceLabel: string; targetLabel: string }

const VIEW_WIDTH = 980
const VIEW_HEIGHT = 420
const NODE_WIDTH = 20
const CHART_TOP = 28
const CHART_BOTTOM = 396
const NODE_GAP = 26
const COL_X = [24, 460, 896]

const FLOW_TOTAL = 'var(--flow-total)'
const FLOW_PENDING = 'var(--flow-pending)'
const FLOW_GOOD = 'var(--accent)'
const FLOW_MODERATE = 'var(--warn)'
const FLOW_BAD = 'var(--error)'

function formatCount(value: number) {
  return value.toLocaleString()
}

function formatPercent(value: number, total: number) {
  if (!total) {
    return '0%'
  }
  return `${Math.round((value / total) * 100)}%`
}

function ribbonPath(sx: number, sy0: number, sy1: number, tx: number, ty0: number, ty1: number) {
  const xm = (sx + tx) / 2
  return `M${sx},${sy0} C${xm},${sy0} ${xm},${ty0} ${tx},${ty0} L${tx},${ty1} C${xm},${ty1} ${xm},${sy1} ${sx},${sy1} Z`
}

export default function AlluvialChart({ funnel }: AlluvialChartProps) {
  const [hover, setHover] = useState<HoverTarget | null>(null)

  const { nodes, links, total } = useMemo(() => {
    const notProcessed = Math.max(0, funnel.total_scraped - funnel.total_processed)

    const rawNodes: FlowNode[] = [
      { id: 'scraped', label: 'Scraped jobs', value: funnel.total_scraped, column: 0, fill: FLOW_TOTAL, textColor: 'light' },
      { id: 'processed', label: 'Processed by agent', value: funnel.total_processed, column: 1, fill: FLOW_TOTAL, textColor: 'light' },
      { id: 'pending-1', label: 'Not yet processed', value: notProcessed, column: 1, fill: FLOW_PENDING, textColor: 'dark' },
      { id: 'good', label: 'Good match', value: funnel.good_matches, column: 2, fill: FLOW_GOOD, textColor: 'light' },
      { id: 'moderate', label: 'Moderate match', value: funnel.moderate_matches, column: 2, fill: FLOW_MODERATE, textColor: 'light' },
      { id: 'bad', label: 'Bad match', value: funnel.bad_matches, column: 2, fill: FLOW_BAD, textColor: 'light' },
      { id: 'pending-2', label: 'Not yet processed', value: notProcessed, column: 2, fill: FLOW_PENDING, textColor: 'dark' },
    ]

    const rawLinks: FlowLink[] = [
      { id: 'scraped-processed', source: 'scraped', target: 'processed', value: funnel.total_processed },
      { id: 'scraped-pending', source: 'scraped', target: 'pending-1', value: notProcessed },
      { id: 'processed-good', source: 'processed', target: 'good', value: funnel.good_matches },
      { id: 'processed-moderate', source: 'processed', target: 'moderate', value: funnel.moderate_matches },
      { id: 'processed-bad', source: 'processed', target: 'bad', value: funnel.bad_matches },
      { id: 'pending-pending', source: 'pending-1', target: 'pending-2', value: notProcessed },
    ]

    const total = funnel.total_scraped
    const columnCounts = [1, 2, 4]
    const maxGaps = Math.max(...columnCounts) - 1
    const availableHeight = CHART_BOTTOM - CHART_TOP - maxGaps * NODE_GAP
    const scale = total > 0 ? availableHeight / total : 0
    const minHeight = 3

    const laidOutNodes: LaidOutNode[] = []
    for (const col of [0, 1, 2]) {
      let y = CHART_TOP
      for (const node of rawNodes.filter((n) => n.column === col)) {
        const height = node.value > 0 ? Math.max(node.value * scale, minHeight) : 0
        laidOutNodes.push({ ...node, x: COL_X[col], y0: y, y1: y + height })
        y += height + NODE_GAP
      }
    }
    const nodeById = new Map(laidOutNodes.map((n) => [n.id, n]))

    const sourceCursor = new Map<string, number>()
    const laidOutLinks: LaidOutLink[] = rawLinks
      .filter((link) => link.value > 0)
      .map((link) => {
        const source = nodeById.get(link.source)!
        const target = nodeById.get(link.target)!
        const used = sourceCursor.get(link.source) ?? 0
        const height = Math.max(link.value * scale, minHeight)
        const sy0 = source.y0 + used
        const sy1 = sy0 + height
        sourceCursor.set(link.source, used + height)
        return {
          ...link,
          sx: source.x + NODE_WIDTH,
          sy0,
          sy1,
          tx: target.x,
          ty0: target.y0,
          ty1: target.y1,
          fill: target.fill,
        }
      })

    return { nodes: laidOutNodes, links: laidOutLinks, total }
  }, [funnel])

  if (total === 0) {
    return (
      <div className="empty-state">
        <h2>No scraped jobs yet</h2>
        <p>The pipeline chart will fill in once WebScraper has written job_listings rows.</p>
      </div>
    )
  }

  const nodeById = new Map(nodes.map((n) => [n.id, n]))

  return (
    <div className="alluvial-wrap">
      <svg
        className="alluvial-chart"
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        role="img"
        aria-label="Pipeline funnel from scraped jobs through agent processing to match quality"
        onMouseLeave={() => setHover(null)}
      >
        {links.map((link) => {
          const touchesHoveredNode =
            hover?.kind === 'node' && (hover.node.id === link.source || hover.node.id === link.target)
          const isHighlighted = (hover?.kind === 'link' && hover.link.id === link.id) || touchesHoveredNode
          const isDimmed = hover !== null && !isHighlighted
          return (
            <path
              key={link.id}
              d={ribbonPath(link.sx, link.sy0, link.sy1, link.tx, link.ty0, link.ty1)}
              style={{ fill: link.fill, fillOpacity: isHighlighted ? 0.7 : isDimmed ? 0.2 : 0.45 }}
              onMouseEnter={() =>
                setHover({
                  kind: 'link',
                  link,
                  sourceLabel: nodeById.get(link.source)?.label ?? link.source,
                  targetLabel: nodeById.get(link.target)?.label ?? link.target,
                })
              }
            />
          )
        })}

        {nodes
          .filter((node) => node.value > 0)
          .map((node) => {
            const touchesHoveredLink =
              hover?.kind === 'link' && (hover.link.source === node.id || hover.link.target === node.id)
            const isHighlighted = (hover?.kind === 'node' && hover.node.id === node.id) || touchesHoveredLink
            const isDimmed = hover !== null && !isHighlighted
            return (
              <g key={`${node.id}-${node.column}`}>
                <rect
                  x={node.x}
                  y={node.y0}
                  width={NODE_WIDTH}
                  height={Math.max(node.y1 - node.y0, 1)}
                  rx={4}
                  style={{
                    fill: node.fill,
                    stroke: 'var(--panel)',
                    strokeWidth: 2,
                    opacity: isDimmed ? 0.45 : 1,
                  }}
                  onMouseEnter={() => setHover({ kind: 'node', node })}
                />
                <text
                  x={node.x}
                  y={node.y0 - 8}
                  className="alluvial-label"
                >
                  {node.label} &middot; {formatCount(node.value)}
                </text>
              </g>
            )
          })}
      </svg>

      <div className="alluvial-tooltip">
        {hover ? (
          hover.kind === 'node' ? (
            <>
              <strong>{formatCount(hover.node.value)}</strong> jobs &middot; {hover.node.label}
              <span className="alluvial-tooltip-sub">{formatPercent(hover.node.value, total)} of scraped jobs</span>
            </>
          ) : (
            <>
              <strong>{formatCount(hover.link.value)}</strong> jobs
              <span className="alluvial-tooltip-sub">
                {hover.sourceLabel} &rarr; {hover.targetLabel} ({formatPercent(hover.link.value, total)})
              </span>
            </>
          )
        ) : (
          <span className="alluvial-tooltip-placeholder">Hover a node or flow for details</span>
        )}
      </div>
    </div>
  )
}
