import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { NodeProps } from '@xyflow/react'
import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, useNodesState } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { IconType } from 'react-icons'
import { FiLayers, FiShield, FiTool } from 'react-icons/fi'
import { SiGooglegemini, SiLangchain } from 'react-icons/si'
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

type DetailNodeData = {
  label: string
  kind: AgentTopologyNodeKind
  summary: string
  source: string
  stage: string
  incoming: number
  outgoing: number
  sourcePosition: Position
  targetPosition: Position
  ruleLabels: string[] | null
}

const ActiveNodeContext = createContext<string | null>(null)

type FlowStage = {
  title: string
  subtitle: string
}

const FLOW_STAGES: FlowStage[] = [
  { title: 'Stage 1. Middleware', subtitle: 'Wraps and enforces guardrails' },
  { title: 'Stage 2. Orchestrator', subtitle: 'Decides next action' },
  { title: 'Stage 3. Tool Sequence', subtitle: 'Fetch -> Crawl -> Evaluate -> Record' },
  { title: 'Stage 4. Scoring LLM', subtitle: 'evaluate_match renders prompt and scores' },
  { title: 'Stage 5. Guardrails', subtitle: 'Injection, output, and tool-usage checks' },
]

const KIND_CLASS: Record<AgentTopologyNodeKind, string> = {
  agent: 'agent-node-agent',
  tool: 'agent-node-tool',
  middleware: 'agent-node-middleware',
  guardrail: 'agent-node-guardrail',
  prompt: 'agent-node-prompt',
}

const KIND_SUMMARY: Record<AgentTopologyNodeKind, string> = {
  middleware: 'Execution wrapper',
  agent: 'Decision engine',
  tool: 'Executable action',
  prompt: 'LLM prompt template',
  guardrail: 'Safety gate',
}

// A brand logo for the two nodes with an actual named underlying tech (the ReAct orchestrator is
// built on LangChain; the scoring prompt is rendered and sent to Gemini). Keyed by node id, not
// kind, since it's specifically these two nodes, not "every agent-kind node" / "every prompt-kind
// node" -- every other node (tools, middleware, guardrails) is our own code with no single vendor
// to badge, so those fall back to a generic icon per kind instead (KIND_FALLBACK_ICON below).
const NODE_ICON: Record<string, IconType> = {
  'agent:react': SiLangchain,
  'prompt:scoring': SiGooglegemini,
}

const KIND_FALLBACK_ICON: Record<AgentTopologyNodeKind, IconType> = {
  middleware: FiLayers,
  agent: SiLangchain,
  tool: FiTool,
  prompt: SiGooglegemini,
  guardrail: FiShield,
}

const MINIMAP_COLOR: Record<AgentTopologyNodeKind, string> = {
  middleware: '#d9a441',
  agent: '#1f8a57',
  tool: '#2f8fc4',
  prompt: '#7a5fd1',
  guardrail: '#c8534a',
}

// Guardrail rules are stacked inside per-middleware nodes (see agent_topology.py's guardrail:checks
// and guardrail:tool-call-limit) rather than one card per rule -- one guardrail node per middleware
// that actually enforces its rules, never shared. Sits upstream of the middleware column (x=120),
// using the same y-range so each guardrail node lines up with the one middleware it feeds into:
// rules -> middleware -> agent, left to right, top-to-bottom pairing preserved.
const GUARDRAIL_X = -160

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
  for (const item of distribute(guardrailNodes, GUARDRAIL_X, 150, 360)) {
    layout.set(item.node.id, item.point)
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
  if (kind === 'guardrail') {
    // Sits upstream of the middleware column (see GUARDRAIL_X above) and feeds into it left-to-right.
    return Position.Right
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
  if (kind === 'middleware') {
    // The only edges that ever target middleware are the two guardrail nodes, each arriving from the left.
    return Position.Left
  }
  if (kind === 'prompt' || kind === 'guardrail') {
    return Position.Top
  }
  return Position.Right
}

function stageLabelFor(kind: AgentTopologyNodeKind): string {
  if (kind === 'middleware') return 'Stage 1'
  if (kind === 'agent') return 'Stage 2'
  if (kind === 'tool') return 'Stage 3'
  if (kind === 'prompt') return 'Stage 4'
  return 'Stage 5'
}

function shortSourcePath(source: string): string {
  if (!source) return 'n/a'
  const normalized = source.replace(/\\/g, '/')
  const parts = normalized.split('/')
  if (parts.length <= 2) return normalized
  return `${parts[parts.length - 2]}/${parts[parts.length - 1]}`
}

function DetailNode({ id, data, selected }: NodeProps) {
  const nodeData = data as unknown as DetailNodeData
  const activeNodeId = useContext(ActiveNodeContext)
  const isActive = activeNodeId === id
  const TechIcon = NODE_ICON[id] ?? KIND_FALLBACK_ICON[nodeData.kind]
  return (
    <div className={`agent-card-node ${KIND_CLASS[nodeData.kind]}${isActive ? ' is-active' : ''}${selected ? ' is-selected' : ''}`}>
      <Handle type="target" position={nodeData.targetPosition} className="agent-handle" />
      <Handle type="source" position={nodeData.sourcePosition} className="agent-handle" />

      <div className="node-card-layout">
        <div className="node-card-logo-rail">
          <TechIcon aria-hidden="true" />
        </div>

        <div className="node-card-content">
          <div className="node-card-head">
            <strong className="agent-card-title">{nodeData.label}</strong>
            <span className="agent-card-status">{isActive ? 'FOCUS' : 'LIVE'}</span>
          </div>

          <div className="agent-card-body">
            <p className="agent-card-summary">{nodeData.summary}</p>
            <div className="agent-card-meta-row">
              <span>{nodeData.stage}</span>
              <span>{nodeData.incoming} in</span>
              <span>{nodeData.outgoing} out</span>
            </div>
            {nodeData.ruleLabels && nodeData.ruleLabels.length > 0 && (
              <div className="agent-card-rule-stack">
                {nodeData.ruleLabels.map((rule) => (
                  <span key={rule} className="agent-card-rule-chip">
                    {rule}
                  </span>
                ))}
              </div>
            )}
            <p className="agent-card-source">{shortSourcePath(nodeData.source)}</p>
          </div>
        </div>
      </div>
    </div>
  )
}

function buildFlowNode(
  node: AgentTopologyNode,
  point: Point,
  edgeCounts: { incoming: Map<string, number>; outgoing: Map<string, number> },
) {
  const sourcePosition = sourcePositionFor(node.kind)
  const targetPosition = targetPositionFor(node.kind)
  return {
    id: node.id,
    type: 'detailNode',
    position: point,
    data: {
      label: node.label,
      kind: node.kind,
      summary: KIND_SUMMARY[node.kind],
      source: node.source,
      stage: stageLabelFor(node.kind),
      incoming: edgeCounts.incoming.get(node.id) ?? 0,
      outgoing: edgeCounts.outgoing.get(node.id) ?? 0,
      sourcePosition,
      targetPosition,
      ruleLabels: node.rule_labels,
    },
    sourcePosition,
    targetPosition,
  }
}

export default function AgentTopologyHero({ topology }: Props) {
  const [pinnedNodeId, setPinnedNodeId] = useState<string | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)

  const layout = useMemo(() => buildLayout(topology.nodes), [topology.nodes])
  const fallbackNodeId = topology.nodes.find((node) => node.kind === 'agent')?.id ?? topology.nodes[0]?.id ?? null
  const activeNodeId = pinnedNodeId ?? hoveredNodeId ?? fallbackNodeId
  const activeNode = topology.nodes.find((node) => node.id === activeNodeId) ?? null
  const nodeTypes = useMemo(() => ({ detailNode: DetailNode }), [])
  const nodesById = useMemo(() => {
    const map = new Map<string, AgentTopologyNode>()
    for (const node of topology.nodes) {
      map.set(node.id, node)
    }
    return map
  }, [topology.nodes])

  const edgeCounts = useMemo(() => {
    const incoming = new Map<string, number>()
    const outgoing = new Map<string, number>()
    for (const edge of topology.edges) {
      incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1)
      outgoing.set(edge.source, (outgoing.get(edge.source) ?? 0) + 1)
    }
    return { incoming, outgoing }
  }, [topology.edges])

  const [flowNodes, setFlowNodes, onFlowNodesChange] = useNodesState<ReturnType<typeof buildFlowNode>>([])

  useEffect(() => {
    setFlowNodes((current) => {
      const currentById = new Map(current.map((node) => [node.id, node]))
      return topology.nodes.map((node) => {
        const existing = currentById.get(node.id)
        const point = layout.get(node.id) ?? { x: 0, y: 0 }
        return buildFlowNode(node, existing?.position ?? point, edgeCounts)
      })
    })
  }, [edgeCounts, layout, topology.nodes, setFlowNodes])

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
        <h2>Job Manager Agent</h2>
        <p className="agent-hero-subtitle">
          Hover or click nodes to inspect exact runtime prompt text, tool descriptions, middleware, and guardrails.
        </p>
      </div>

      {/* <div className="agent-hero-kpis">
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
      </div> */}

      <h3>Agent Workflow Stages</h3>
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
            <ActiveNodeContext.Provider value={activeNodeId}>
              <ReactFlow
                nodes={flowNodes}
                edges={flowEdges}
                nodeTypes={nodeTypes}
                onNodesChange={onFlowNodesChange}
                nodesDraggable
                nodesConnectable={false}
                elementsSelectable={false}
                nodeDragThreshold={2}
                zoomOnDoubleClick={false}
                panOnScroll
                minZoom={0.45}
                maxZoom={1.35}
                fitView
                fitViewOptions={{ padding: 0.14, minZoom: 0.45 }}
                defaultViewport={{ x: 0, y: 0, zoom: 0.7 }}
                onNodeMouseEnter={(_, node) => setHoveredNodeId(node.id)}
                onNodeMouseLeave={(_, node) => {
                  setHoveredNodeId((current) => (current === node.id ? null : current))
                }}
                onNodeClick={(_, node) => {
                  setPinnedNodeId((current) => (current === node.id ? null : node.id))
                }}
              >
                <Background color="rgba(20, 26, 31, 0.1)" gap={22} size={1.4} />
                <Controls showInteractive={false} />
                <MiniMap
                  pannable
                  zoomable
                  nodeStrokeWidth={2}
                  nodeColor={(node) => MINIMAP_COLOR[(node.data as unknown as DetailNodeData)?.kind] ?? '#9db8a6'}
                  maskColor="rgba(20, 26, 31, 0.08)"
                  className="agent-flow-minimap"
                  style={{ width: 140, height: 96 }}
                />
              </ReactFlow>
            </ActiveNodeContext.Provider>
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
