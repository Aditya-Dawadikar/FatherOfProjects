import { useState } from 'react'
import type { SystemDag, SystemNode, SystemEdge, NodeStatus } from '../types'

const NODE_W  = 148
const NODE_H  = 52
const NODE_HH = NODE_H / 2   // 26

const CANVAS_W = 920
const CANVAS_H = 510

const CATEGORY_LABEL: Record<string, string> = {
  scraper:   'Cron Job',
  storage:   'Postgres',
  backend:   'API Server',
  stream:    'Redis',
  worker:    'Worker',
  dashboard: 'Frontend',
}

const CLUSTERS = [
  { label: 'Scraper Flow',        x: 16,  y: 44, w: 348, h: 388 },
  { label: 'Observability Module', x: 400, y: 182, w: 224, h: 290 },
  { label: 'Observer Dashboard',  x: 686, y: 82,  w: 178, h: 290 },
]

function nodeHW(n: SystemNode) { return (n.width ?? NODE_W) / 2 }

function getEdgePath(src: SystemNode, tgt: SystemNode): string {
  const shw = nodeHW(src)
  const thw = nodeHW(tgt)
  const dx  = tgt.cx - src.cx

  if (dx !== 0) {
    const x1 = dx > 0 ? src.cx + shw : src.cx - shw
    const x2 = dx > 0 ? tgt.cx - thw : tgt.cx + thw
    const y1 = src.cy, y2 = tgt.cy
    const mx = (x1 + x2) / 2
    return `M ${x1} ${y1} C ${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`
  }
  // Same x — vertical
  const y1 = tgt.cy > src.cy ? src.cy + NODE_HH : src.cy - NODE_HH
  const y2 = tgt.cy > src.cy ? tgt.cy - NODE_HH : tgt.cy + NODE_HH
  const my = (y1 + y2) / 2
  return `M ${src.cx} ${y1} C ${src.cx} ${my} ${tgt.cx} ${my} ${tgt.cx} ${y2}`
}

function edgeMidpoint(src: SystemNode, tgt: SystemNode): [number, number] {
  const shw = nodeHW(src)
  const thw = nodeHW(tgt)
  const dx  = tgt.cx - src.cx
  if (dx !== 0) {
    const x1 = dx > 0 ? src.cx + shw : src.cx - shw
    const x2 = dx > 0 ? tgt.cx - thw : tgt.cx + thw
    return [(x1 + x2) / 2, (src.cy + tgt.cy) / 2]
  }
  const y1 = tgt.cy > src.cy ? src.cy + NODE_HH : src.cy - NODE_HH
  const y2 = tgt.cy > src.cy ? tgt.cy - NODE_HH : tgt.cy + NODE_HH
  return [(src.cx + tgt.cx) / 2, (y1 + y2) / 2]
}

function edgeStroke(status: NodeStatus): string {
  switch (status) {
    case 'warning': return 'var(--warn)'
    case 'error':   return 'var(--error)'
    case 'idle':    return 'var(--muted)'
    default:        return 'var(--line)'
  }
}

function statusDotColor(status: NodeStatus): string {
  switch (status) {
    case 'healthy': return 'var(--accent)'
    case 'warning': return 'var(--warn)'
    case 'error':   return 'var(--error)'
    case 'idle':    return 'var(--muted)'
  }
}

interface GraphNodeProps {
  node: SystemNode
  selected: boolean
  onClick: () => void
}

function GraphNode({ node, selected, onClick }: GraphNodeProps) {
  const w = node.width ?? NODE_W
  const left = node.cx - w / 2
  const top  = node.cy - NODE_HH

  return (
    <div
      className={[
        'gnode',
        `gnode-${node.status}`,
        selected ? 'gnode-selected' : '',
      ].join(' ')}
      style={{ left, top, width: w, height: NODE_H }}
      onClick={onClick}
      title={node.shortDescription}
    >
      <span className="gnode-dot" style={{ background: statusDotColor(node.status) }} />
      <div className="gnode-body">
        <span className="gnode-name">{node.name}</span>
        <span className="gnode-cat">{CATEGORY_LABEL[node.category]}</span>
      </div>
      <span className="gnode-score">{node.healthScore}</span>
    </div>
  )
}

interface EdgeGroupProps {
  edge: SystemEdge
  src: SystemNode
  tgt: SystemNode
  hovered: boolean
  onHover: (id: string | null) => void
}

function EdgeGroup({ edge, src, tgt, hovered, onHover }: EdgeGroupProps) {
  const d      = getEdgePath(src, tgt)
  const [mx, my] = edgeMidpoint(src, tgt)
  const stroke = edgeStroke(edge.status)
  const opacity = edge.status === 'idle' ? 0.3 : hovered ? 1 : 0.5

  return (
    <g
      className="edge-group"
      onMouseEnter={() => onHover(edge.id)}
      onMouseLeave={() => onHover(null)}
    >
      {/* Wide transparent hitbox for easier hovering */}
      <path d={d} stroke="transparent" strokeWidth={14} fill="none" style={{ cursor: 'default' }} />
      {/* Visible edge */}
      <path
        d={d}
        stroke={stroke}
        strokeWidth={hovered ? 2 : 1}
        fill="none"
        strokeDasharray={edge.status === 'idle' ? '5 4' : undefined}
        style={{ transition: 'stroke-width 0.15s, opacity 0.15s', opacity }}
        markerEnd={`url(#arrow-${edge.status})`}
      />
      {/* Tooltip on hover */}
      {hovered && (
        <g>
          <rect
            x={mx - 70} y={my - 20}
            width={140} height={36}
            rx={5}
            fill="var(--panel)"
            stroke="var(--line)"
            strokeWidth={1}
          />
          <text x={mx} y={my - 7} textAnchor="middle" fill="var(--text)" fontSize={10} fontWeight={600}>
            {edge.label}
          </text>
          <text x={mx} y={my + 8} textAnchor="middle" fill="var(--muted)" fontSize={9}>
            {edge.lastEventAt ? `Last: ${edge.lastEventAt}` : 'No recent events'}
            {edge.throughput ? ` · ${edge.throughput}` : ''}
          </text>
        </g>
      )}
    </g>
  )
}

interface NodeGraphProps {
  dag: SystemDag
  selectedNodeId: string | null
  onSelectNode: (id: string) => void
}

export default function NodeGraph({ dag, selectedNodeId, onSelectNode }: NodeGraphProps) {
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null)

  const nodeMap = new Map(dag.nodes.map(n => [n.id, n]))

  return (
    <div className="graph-canvas-wrap">
      <div className="graph-canvas" style={{ width: CANVAS_W, height: CANVAS_H }}>

        {/* SVG layer: cluster backgrounds + edges */}
        <svg
          className="graph-svg"
          width={CANVAS_W}
          height={CANVAS_H}
          style={{ position: 'absolute', inset: 0, overflow: 'visible' }}
        >
          <defs>
            {(['healthy', 'warning', 'error', 'idle'] as NodeStatus[]).map(s => (
              <marker
                key={s}
                id={`arrow-${s}`}
                markerWidth={7}
                markerHeight={7}
                refX={6}
                refY={3}
                orient="auto"
              >
                <path
                  d="M 0 0 L 7 3 L 0 6 Z"
                  fill={edgeStroke(s)}
                  opacity={s === 'idle' ? 0.4 : 0.8}
                />
              </marker>
            ))}
          </defs>

          {/* Cluster backgrounds */}
          {CLUSTERS.map(c => (
            <g key={c.label}>
              <rect
                x={c.x} y={c.y} width={c.w} height={c.h}
                rx={10}
                fill="rgba(36, 43, 40, 0.45)"
                stroke="var(--line)"
                strokeWidth={1}
              />
              <text
                x={c.x + 10} y={c.y - 7}
                fill="var(--muted)"
                fontSize={9}
                fontWeight={700}
                letterSpacing={1}
                style={{ textTransform: 'uppercase' }}
              >
                {c.label}
              </text>
            </g>
          ))}

          {/* Edges */}
          {dag.edges.map(edge => {
            const src = nodeMap.get(edge.source)
            const tgt = nodeMap.get(edge.target)
            if (!src || !tgt) return null
            return (
              <EdgeGroup
                key={edge.id}
                edge={edge}
                src={src}
                tgt={tgt}
                hovered={hoveredEdgeId === edge.id}
                onHover={setHoveredEdgeId}
              />
            )
          })}
        </svg>

        {/* Node divs — sit on top of SVG */}
        {dag.nodes.map(node => (
          <GraphNode
            key={node.id}
            node={node}
            selected={selectedNodeId === node.id}
            onClick={() => onSelectNode(node.id)}
          />
        ))}
      </div>
    </div>
  )
}
