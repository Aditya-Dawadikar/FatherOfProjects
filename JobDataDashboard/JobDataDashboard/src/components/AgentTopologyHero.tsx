import { useMemo, useState } from 'react'
import type { AgentTopology, AgentTopologyNode, AgentTopologyNodeKind } from '../types'

type Point = {
  x: number
  y: number
}

type NodeLayout = {
  node: AgentTopologyNode
  point: Point
}

type Props = {
  topology: AgentTopology
}

const KIND_CLASS: Record<AgentTopologyNodeKind, string> = {
  agent: 'agent-node-agent',
  tool: 'agent-node-tool',
  middleware: 'agent-node-middleware',
  guardrail: 'agent-node-guardrail',
  prompt: 'agent-node-prompt',
}

function distribute(nodes: AgentTopologyNode[], x: number, minY: number, maxY: number): NodeLayout[] {
  if (nodes.length === 0) {
    return []
  }
  if (nodes.length === 1) {
    return [{ node: nodes[0], point: { x, y: (minY + maxY) / 2 } }]
  }
  const step = (maxY - minY) / (nodes.length - 1)
  return nodes.map((node, index) => ({
    node,
    point: { x, y: minY + step * index },
  }))
}

function buildLayout(nodes: AgentTopologyNode[]): Map<string, Point> {
  const agentNodes = nodes.filter((node) => node.kind === 'agent')
  const middlewareNodes = nodes.filter((node) => node.kind === 'middleware')
  const toolNodes = nodes.filter((node) => node.kind === 'tool')
  const promptNodes = nodes.filter((node) => node.kind === 'prompt')
  const guardrailNodes = nodes.filter((node) => node.kind === 'guardrail')

  const layout = new Map<string, Point>()

  for (const item of distribute(middlewareNodes, 160, 90, 360)) {
    layout.set(item.node.id, item.point)
  }
  for (const item of distribute(agentNodes, 420, 150, 300)) {
    layout.set(item.node.id, item.point)
  }
  for (const item of distribute(toolNodes, 700, 80, 370)) {
    layout.set(item.node.id, item.point)
  }
  for (const item of distribute(promptNodes, 520, 380, 440)) {
    layout.set(item.node.id, item.point)
  }
  for (const item of distribute(guardrailNodes, 430, 440, 440)) {
    const spread = 700 / Math.max(guardrailNodes.length - 1, 1)
    const index = guardrailNodes.findIndex((node) => node.id === item.node.id)
    layout.set(item.node.id, { x: 80 + spread * index, y: 440 })
  }

  return layout
}

export default function AgentTopologyHero({ topology }: Props) {
  const [pinnedNodeId, setPinnedNodeId] = useState<string | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)

  const layout = useMemo(() => buildLayout(topology.nodes), [topology.nodes])
  const fallbackNodeId = topology.nodes.find((node) => node.kind === 'agent')?.id ?? topology.nodes[0]?.id ?? null
  const activeNodeId = pinnedNodeId ?? hoveredNodeId ?? fallbackNodeId
  const activeNode = topology.nodes.find((node) => node.id === activeNodeId) ?? null

  return (
    <section className="agent-hero" aria-label="Live agent topology">
      <div className="agent-hero-header">
        <p className="eyebrow">Live Agent Blueprint</p>
        <h2>Interactive JobManagerAgent graph</h2>
        <p className="agent-hero-subtitle">
          Hover or click nodes to inspect exact runtime prompt text, tool descriptions, middleware, and guardrails.
        </p>
      </div>

      <div className="agent-hero-kpis">
        <article className="agent-hero-chip">
          <span>Agent</span>
          <strong>{topology.agent_name}</strong>
        </article>
        <article className="agent-hero-chip">
          <span>Match Threshold</span>
          <strong>{topology.threshold}</strong>
        </article>
        <article className="agent-hero-chip">
          <span>Max Jobs/Cycle</span>
          <strong>{topology.max_jobs_per_cycle}</strong>
        </article>
        <article className="agent-hero-chip">
          <span>Tool Call Limit</span>
          <strong>{topology.tool_call_limit}</strong>
        </article>
      </div>

      <div className="agent-hero-body">
        <div className="agent-graph-wrap">
          <svg className="agent-graph-lines" viewBox="0 0 860 500" aria-hidden="true">
            {topology.edges.map((edge, index) => {
              const source = layout.get(edge.source)
              const target = layout.get(edge.target)
              if (!source || !target) {
                return null
              }
              return (
                <g key={`${edge.source}-${edge.target}-${index}`}>
                  <path
                    d={`M ${source.x} ${source.y} C ${(source.x + target.x) / 2} ${source.y}, ${(source.x + target.x) / 2} ${target.y}, ${target.x} ${target.y}`}
                    className="agent-edge"
                  />
                </g>
              )
            })}
          </svg>

          {topology.nodes.map((node) => {
            const point = layout.get(node.id)
            if (!point) {
              return null
            }
            const isActive = activeNodeId === node.id
            return (
              <button
                key={node.id}
                type="button"
                className={`agent-node ${KIND_CLASS[node.kind]}${isActive ? ' is-active' : ''}`}
                style={{ left: `${(point.x / 860) * 100}%`, top: `${(point.y / 500) * 100}%` }}
                onMouseEnter={() => setHoveredNodeId(node.id)}
                onMouseLeave={() => setHoveredNodeId((current) => (current === node.id ? null : current))}
                onClick={() => setPinnedNodeId((current) => (current === node.id ? null : node.id))}
                aria-pressed={pinnedNodeId === node.id}
                aria-label={`${node.label} ${node.kind}`}
              >
                <span>{node.label}</span>
              </button>
            )
          })}
        </div>

        <aside className="agent-detail-panel">
          <div className="agent-detail-heading">
            <span className={`agent-kind-pill ${activeNode ? KIND_CLASS[activeNode.kind] : ''}`}>
              {activeNode?.kind ?? 'node'}
            </span>
            <strong>{activeNode?.label ?? 'No node selected'}</strong>
          </div>
          <p className="agent-detail-source">Source: {activeNode?.source ?? 'n/a'}</p>
          <pre className="agent-detail-content">{activeNode?.detail ?? ''}</pre>
          <p className="agent-detail-footer">Generated at {new Date(topology.generated_at).toLocaleString()}</p>
        </aside>
      </div>
    </section>
  )
}
