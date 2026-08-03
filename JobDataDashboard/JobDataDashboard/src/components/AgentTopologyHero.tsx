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

type FlowStage = {
  title: string
  subtitle: string
}

const FLOW_STAGES: FlowStage[] = [
  { title: '1. Middleware', subtitle: 'Wraps and enforces guardrails' },
  { title: '2. Orchestrator', subtitle: 'Decides next action' },
  { title: '3. Tool Sequence', subtitle: 'Fetch -> Crawl -> Evaluate -> Record' },
  { title: '4. Scoring LLM', subtitle: 'evaluate_match renders prompt and scores' },
  { title: '5. Guardrails', subtitle: 'Injection, output, and tool-usage checks' },
]

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

  for (const item of distribute(middlewareNodes, 120, 150, 360)) {
    layout.set(item.node.id, item.point)
  }
  for (const item of distribute(agentNodes, 380, 230, 280)) {
    layout.set(item.node.id, item.point)
  }
  for (const item of distribute(toolNodes, 700, 120, 520)) {
    layout.set(item.node.id, item.point)
  }
  for (const item of distribute(promptNodes, 1010, 350, 390)) {
    layout.set(item.node.id, item.point)
  }
  for (const item of distribute(guardrailNodes, 600, 630, 630)) {
    const spread = 960 / Math.max(guardrailNodes.length - 1, 1)
    const index = guardrailNodes.findIndex((node) => node.id === item.node.id)
    layout.set(item.node.id, { x: 80 + spread * index, y: 630 })
  }

  return layout
}

function sourcePositionFor(kind: AgentTopologyNodeKind): Position {
  if (kind === 'agent' || kind === 'middleware') {
    return Position.Right
  }
  if (kind === 'tool' || kind === 'prompt') {
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
  const nodesById = useMemo(() => {
    const map = new Map<string, AgentTopologyNode>()
    for (const node of topology.nodes) {
      map.set(node.id, node)
    }
    return map
  }, [topology.nodes])

  const flowNodes = useMemo(
    () => topology.nodes.map((node) => {
      const point = layout.get(node.id) ?? { x: 0, y: 0 }
      return {
        id: node.id,
        position: point,
        data: { label: node.label },
        className: `${KIND_CLASS[node.kind]} agent-node-block${activeNodeId === node.id ? ' is-active' : ''}`,
        sourcePosition: sourcePositionFor(node.kind),
        targetPosition: targetPositionFor(node.kind),
      }
    }),
    [activeNodeId, layout, topology.nodes],
  )

  const primaryPathEdges = useMemo(() => {
    const getToolId = topology.nodes.find((node) => node.kind === 'tool' && node.label === 'get_jobs_to_process')?.id
    const crawlToolId = topology.nodes.find((node) => node.kind === 'tool' && node.label === 'crawl_job')?.id
    const evaluateToolId = topology.nodes.find((node) => node.kind === 'tool' && node.label === 'evaluate_match')?.id
    const recordToolId = topology.nodes.find((node) => node.kind === 'tool' && node.label === 'record_job_result')?.id
    const agentId = topology.nodes.find((node) => node.kind === 'agent')?.id

    const edges: Array<{ id: string; source: string; target: string; label: string }> = []
    if (agentId && getToolId) {
      edges.push({ id: 'primary-agent-start', source: agentId, target: getToolId, label: 'start' })
    }
    if (getToolId && crawlToolId) {
      edges.push({ id: 'primary-step-2', source: getToolId, target: crawlToolId, label: 'then' })
    }
    if (crawlToolId && evaluateToolId) {
      edges.push({ id: 'primary-step-3', source: crawlToolId, target: evaluateToolId, label: 'then' })
    }
    if (evaluateToolId && recordToolId) {
      edges.push({ id: 'primary-step-4', source: evaluateToolId, target: recordToolId, label: 'then' })
    }
    return edges
  }, [topology.nodes])

  const flowEdges = useMemo(
    () => {
      const baseEdges = topology.edges.map((edge, index) => {
        const sourceKind = nodesById.get(edge.source)?.kind
        const isEnforcement = edge.label === 'enforces' || sourceKind === 'middleware'
        const isGuardrailCheck = edge.label === 'checks'
        const shouldLabel = edge.label === 'middleware' || edge.label === 'calls' || edge.label === 'uses' || edge.label === 'renders'
        return {
          id: `${edge.source}-${edge.target}-${index}`,
          source: edge.source,
          target: edge.target,
          label: shouldLabel ? edge.label ?? undefined : undefined,
          type: 'smoothstep',
          markerEnd: { type: MarkerType.ArrowClosed, width: 13, height: 13 },
          className: `agent-flow-edge${isEnforcement ? ' edge-enforcement' : ''}${isGuardrailCheck ? ' edge-guardrail' : ''}`,
          labelStyle: { fill: '#4f6157', fontSize: 10, fontWeight: 600 },
        }
      })

      const sequenceEdges = primaryPathEdges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label,
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed, width: 15, height: 15 },
        className: 'agent-flow-edge edge-primary',
        labelStyle: { fill: '#0f4f30', fontSize: 10, fontWeight: 700 },
      }))
      return [...baseEdges, ...sequenceEdges]
    },
    [nodesById, primaryPathEdges, topology.edges],
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

      <div className="agent-flow-stages" aria-label="Flow stages">
        {FLOW_STAGES.map((stage) => (
          <article key={stage.title} className="agent-stage-chip">
            <strong>{stage.title}</strong>
            <span>{stage.subtitle}</span>
          </article>
        ))}
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
              panOnScroll
              minZoom={0.62}
              maxZoom={1.35}
              fitView
              fitViewOptions={{ padding: 0.12, minZoom: 0.62 }}
              defaultViewport={{ x: 0, y: 0, zoom: 0.75 }}
              onNodeMouseEnter={(_, node) => setHoveredNodeId(node.id)}
              onNodeMouseLeave={(_, node) => {
                setHoveredNodeId((current) => (current === node.id ? null : current))
              }}
              onNodeClick={(_, node) => {
                setPinnedNodeId((current) => (current === node.id ? null : node.id))
              }}
            >
              <Background color="rgba(16, 30, 20, 0.08)" gap={24} />
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
