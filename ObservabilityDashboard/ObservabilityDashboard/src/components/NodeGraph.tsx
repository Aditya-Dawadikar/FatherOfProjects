import { useEffect, useRef, useState } from 'react'
import type { LivePullState, LiveSourceState, SystemDag, SystemNode, SystemEdge, NodeStatus } from '../types'

const NODE_W = 148
const NODE_H = 100
const NODE_HH = NODE_H / 2   // 26

const CANVAS_W = 920
const CANVAS_H = 510
const DRAG_THRESHOLD = 4

const CATEGORY_LABEL: Record<string, string> = {
  scraper: 'Cron Job',
  storage: 'Postgres',
  backend: 'API Server',
  stream: 'Redis',
  worker: 'Worker',
  dashboard: 'Frontend',
}

function nodeHW(n: SystemNode) { return (n.width ?? NODE_W) / 2 }

function getEdgePath(src: SystemNode, tgt: SystemNode): string {
  const shw = nodeHW(src)
  const thw = nodeHW(tgt)
  const dx = tgt.cx - src.cx

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
  const dx = tgt.cx - src.cx
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
    case 'error': return 'var(--error)'
    case 'idle': return 'var(--muted)'
    default: return 'var(--line)'
  }
}

function statusDotColor(status: NodeStatus): string {
  switch (status) {
    case 'healthy': return 'var(--accent)'
    case 'warning': return 'var(--warn)'
    case 'error': return 'var(--error)'
    case 'idle': return 'var(--muted)'
  }
}

function livePullLabel(livePullState: LivePullState | undefined): string | null {
  switch (livePullState) {
    case 'active':
      return 'LIVE'
    case 'inactive':
      return 'NO FEED'
    default:
      return null
  }
}

function liveSourceLabel(liveSourceState: LiveSourceState | undefined): string | null {
  switch (liveSourceState) {
    case 'active':
      return 'SOURCE'
    case 'inactive':
      return 'SOURCE IDLE'
    default:
      return null
  }
}

function clampNodePosition(node: SystemNode, cx: number, cy: number) {
  const halfWidth = nodeHW(node)

  return {
    cx: Math.min(Math.max(cx, halfWidth), CANVAS_W - halfWidth),
    cy: Math.min(Math.max(cy, NODE_HH), CANVAS_H - NODE_HH),
  }
}

interface GraphNodeProps {
  node: SystemNode
  selected: boolean
  dragging: boolean
  onClick: () => void
  onPointerDown: (event: React.PointerEvent<HTMLDivElement>) => void
}

function GraphNode({ node, selected, dragging, onClick, onPointerDown }: GraphNodeProps) {
  const w = node.width ?? NODE_W
  const left = node.cx - w / 2
  const top = node.cy - NODE_HH
  const liveBadge = livePullLabel(node.livePullState)
  const sourceBadge = liveSourceLabel(node.liveSourceState)

  return (
    <div
      className={[
        'gnode',
        `gnode-${node.status}`,
        dragging ? 'gnode-dragging' : '',
        selected ? 'gnode-selected' : '',
      ].join(' ')}
      style={{ left, top, width: w, height: NODE_H }}
      onClick={onClick}
      onPointerDown={onPointerDown}
      title={node.shortDescription}
    >
      <span className="gnode-dot" style={{ background: statusDotColor(node.status) }} />
      <div className="gnode-body">
        <span className="gnode-name">{node.name}</span>
        <span className="gnode-cat">{CATEGORY_LABEL[node.category]}</span>
        <br/>
        {sourceBadge && (
          <span className={`gnode-live-pill gnode-live-pill-source gnode-live-pill-source-${node.liveSourceState}`}>{sourceBadge}</span>
        )}
        {liveBadge && (
          <span className={`gnode-live-pill gnode-live-pill-${node.livePullState}`}>{liveBadge}</span>
        )}

      </div>

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
  const d = getEdgePath(src, tgt)
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
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null)
  const [positionOverrides, setPositionOverrides] = useState<Record<string, { cx: number, cy: number }>>({})
  const canvasRef = useRef<HTMLDivElement | null>(null)
  const dragStateRef = useRef<{ id: string, offsetX: number, offsetY: number, moved: boolean } | null>(null)
  const suppressClickRef = useRef(false)

  useEffect(() => {
    setPositionOverrides(current => {
      const next: Record<string, { cx: number, cy: number }> = {}
      let changed = false

      for (const node of dag.nodes) {
        const existing = current[node.id]
        if (existing) {
          next[node.id] = existing
        }
      }

      if (Object.keys(current).length !== Object.keys(next).length) {
        changed = true
      }

      return changed ? next : current
    })
  }, [dag.nodes])

  const renderedNodes = dag.nodes.map(node => {
    const override = positionOverrides[node.id]
    return override ? { ...node, ...override } : node
  })

  const updateDraggedNodePosition = (clientX: number, clientY: number) => {
    const dragState = dragStateRef.current
    const canvas = canvasRef.current
    if (!dragState || !canvas) {
      return
    }

    const node = renderedNodes.find(candidate => candidate.id === dragState.id)
    if (!node) {
      return
    }

    const rect = canvas.getBoundingClientRect()
    const nextPosition = clampNodePosition(
      node,
      clientX - rect.left - dragState.offsetX,
      clientY - rect.top - dragState.offsetY,
    )

    const movedEnough =
      Math.abs(nextPosition.cx - node.cx) > DRAG_THRESHOLD ||
      Math.abs(nextPosition.cy - node.cy) > DRAG_THRESHOLD

    if (movedEnough) {
      dragState.moved = true
    }

    setPositionOverrides(current => {
      const existing = current[node.id]
      if (existing?.cx === nextPosition.cx && existing?.cy === nextPosition.cy) {
        return current
      }

      return {
        ...current,
        [node.id]: nextPosition,
      }
    })
  }

  useEffect(() => {
    if (!draggingNodeId) {
      return
    }

    const handlePointerMove = (event: PointerEvent) => {
      updateDraggedNodePosition(event.clientX, event.clientY)
    }

    const handlePointerUp = () => {
      suppressClickRef.current = dragStateRef.current?.moved ?? false
      dragStateRef.current = null
      setDraggingNodeId(null)
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)

    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
    }
  }, [draggingNodeId, renderedNodes])

  const handleNodePointerDown = (node: SystemNode) => (event: React.PointerEvent<HTMLDivElement>) => {
    const canvas = canvasRef.current
    if (!canvas) {
      return
    }

    const rect = canvas.getBoundingClientRect()
    dragStateRef.current = {
      id: node.id,
      offsetX: event.clientX - rect.left - node.cx,
      offsetY: event.clientY - rect.top - node.cy,
      moved: false,
    }
    suppressClickRef.current = false
    setDraggingNodeId(node.id)
  }

  const handleNodeClick = (nodeId: string) => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false
      return
    }

    onSelectNode(nodeId)
  }

  const nodeMap = new Map(renderedNodes.map(n => [n.id, n]))

  return (
    <div className="graph-canvas-wrap">
      <div ref={canvasRef} className="graph-canvas" style={{ width: CANVAS_W, height: CANVAS_H }}>

        {/* SVG layer: edges */}
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
        {renderedNodes.map(node => (
          <GraphNode
            key={node.id}
            node={node}
            dragging={draggingNodeId === node.id}
            selected={selectedNodeId === node.id}
            onClick={() => handleNodeClick(node.id)}
            onPointerDown={handleNodePointerDown(node)}
          />
        ))}
      </div>
    </div>
  )
}
