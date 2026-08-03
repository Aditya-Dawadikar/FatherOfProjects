import { useMemo, useState } from 'react'
import { Background, Controls, MarkerType, Position, ReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
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

  for (const item of distribute(middlewareNodes, 120, 120, 360)) {
    layout.set(item.node.id, item.point)
  }
  for (const item of distribute(agentNodes, 360, 190, 300)) {
    layout.set(item.node.id, item.point)
  }
  for (const item of distribute(toolNodes, 640, 100, 400)) {
    layout.set(item.node.id, item.point)
  }
  for (const item of distribute(promptNodes, 500, 450, 450)) {
    layout.set(item.node.id, item.point)
  }
  for (const item of distribute(guardrailNodes, 430, 520, 520)) {
    const spread = 760 / Math.max(guardrailNodes.length - 1, 1)
    const index = guardrailNodes.findIndex((node) => node.id === item.node.id)
    layout.set(item.node.id, { x: 40 + spread * index, y: 520 })
  }

  return layout
}

function sourcePositionFor(kind: AgentTopologyNodeKind): Position {
  if (kind === 'agent' || kind === 'middleware') {
    return Position.Right
  }
  if (kind === 'tool') {
    return Position.Bottom
  }
  return Position.Top
}

function targetPositionFor(kind: AgentTopologyNodeKind): Position {
  if (kind === 'agent') {
    return Position.Left
  }
  if (kind === 'tool') {
    return Position.Left
  }
  if (kind === 'prompt' || kind === 'guardrail') {
    return Position.Top
  }
  return Position.Right
}

export default function AgentTopologyHero({ topology }: Props) {
  const [pinnedNodeId, setPinnedNodeId] = useState<string | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)

  const layout = useMemo(() => buildLayout(topology.nodes), [topology.nodes])
  const fallbackNodeId = topology.nodes.find((node) => node.kind === 'agent')?.id ?? topology.nodes[0]?.id ?? null
  const activeNodeId = pinnedNodeId ?? hoveredNodeId ?? fallbackNodeId
  const activeNode = topology.nodes.find((node) => node.id === activeNodeId) ?? null

  const flowNodes = useMemo(
    () => topology.nodes.map((node) => {
      const point = layout.get(node.id) ?? { x: 0, y: 0 }
      return {
        id: node.id,
        position: point,
        data: { label: node.label },
        className: `${KIND_CLASS[node.kind]}${activeNodeId === node.id ? ' is-active' : ''}`,
        sourcePosition: sourcePositionFor(node.kind),
        targetPosition: targetPositionFor(node.kind),
      }
    }),
    [activeNodeId, layout, topology.nodes],
  )

  const flowEdges = useMemo(
    () => topology.edges.map((edge, index) => ({
      id: `${edge.source}-${edge.target}-${index}`,
      source: edge.source,
      target: edge.target,
      label: edge.label ?? undefined,
      type: 'smoothstep',
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
      className: 'agent-flow-edge',
      labelStyle: { fill: '#55665c', fontSize: 10, fontWeight: 600 },
    })),
    [topology.edges],
  )

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
          <div className="agent-flow">
            <ReactFlow
              nodes={flowNodes}
              edges={flowEdges}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable={false}
              zoomOnDoubleClick={false}
              fitView
              fitViewOptions={{ padding: 0.15 }}
              onNodeMouseEnter={(_, node) => setHoveredNodeId(node.id)}
              onNodeMouseLeave={(_, node) => {
                setHoveredNodeId((current) => (current === node.id ? null : current))
              }}
              onNodeClick={(_, node) => {
                setPinnedNodeId((current) => (current === node.id ? null : node.id))
              }}
            >
              <Background color="rgba(16, 30, 20, 0.08)" gap={22} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
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
