import { createContext, useContext, useMemo, useState } from 'react'
import type { NodeProps } from '@xyflow/react'
import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { IconType } from 'react-icons'
import { SiFastapi, SiGrafana, SiLangchain, SiMlflow, SiPostgresql, SiPrometheus, SiPython, SiReact, SiRedis } from 'react-icons/si'

// Unlike AgentTopologyHero (which renders a *live* topology fetched from JobManagerAgent's own
// introspection of its running config/prompt/tools), this graph describes the system's actual
// service/data-flow architecture -- infrastructure topology that doesn't change per request, so
// it's hardcoded here rather than served from an endpoint. Verified against docker-compose.yml,
// Observability/docker-compose.yml, the Caddyfile, and each service's own source (see each node's
// `source` field below) rather than described from memory.

type SystemNodeKind = 'ingestion' | 'datastore' | 'compute' | 'observability' | 'frontend'

type SystemNode = {
  id: string
  label: string
  kind: SystemNodeKind
  tech: string
  detail: string
  source: string
}

type SystemEdge = {
  source: string
  target: string
  label?: string
  emphasis?: 'primary' | 'observability'
}

type Point = { x: number; y: number }

const SYSTEM_NODES: SystemNode[] = [
  {
    id: 'webscraper',
    label: 'WebScraper',
    kind: 'ingestion',
    tech: 'Python',
    detail:
      'Scrapes job listings from external boards and upserts them into Postgres (job_listings table, via shared.job_data.JobListing) -- the same table/model JobDataServer reads from. Runs as a Railway cron job every 4 hours (restartPolicyType=never), not a long-running service; in dev, triggered on demand via `docker compose --profile scraper run --rm webscraper`. On completion, publishes pipeline_started, stage_started/stage_completed (scrape + write stages), and pipeline_completed/pipeline_failed events onto the shared Redis stream.',
    source: 'WebScraper/job_runner.py, WebScraper/dataWriter.py',
  },
  {
    id: 'postgres',
    label: 'Postgres',
    kind: 'datastore',
    tech: 'PostgreSQL',
    detail:
      "Single Postgres server holding two separate databases: webscraper (job_listings + job_matches, shared by WebScraper/JobDataServer/JobManagerAgent) and mlflow (MLflowServer's own backing store, created by postgres-init/01-create-mlflow-db.sql on first boot). Dev mode runs its own local container, isolated from prod's hosted Railway instance -- dev never reads or writes prod data.",
    source: 'docker-compose.yml, postgres-init/01-create-mlflow-db.sql',
  },
  {
    id: 'redis',
    label: 'Redis',
    kind: 'datastore',
    tech: 'Redis',
    detail:
      "Not a queue or cache -- a Redis Stream (XADD/XREAD) used as an append-only event log. WebScraper publishes pipeline lifecycle events; JobManagerAgent's stream consumer blocks on pipeline_completed to trigger a live matching cycle (with an idle-timeout backfill so it never waits forever); JobManagerAgent and JobDataServer each publish their own lifecycle events (matching_cycle_*, job_created/updated/deleted) for any future consumer to pick up.",
    source: 'JobManagerAgent/integrations/streaming/stream_events.py, stream_consumer.py',
  },
  {
    id: 'jobmanageragent',
    label: 'JobManagerAgent',
    kind: 'compute',
    tech: 'LangChain',
    detail:
      'The ReAct orchestrator: pulls unprocessed jobs from Postgres, scores each against the resume through an LLM-driven tool sequence (get_jobs_to_process -> crawl_job -> evaluate_match -> record_job_result), and writes results back. Every cycle is also logged to MLflow as a run+trace. Exposes its own FastAPI app (/evals, /agent-topology, /mlflow-summary, /metrics) alongside the background worker thread -- the same API this dashboard\'s Agent Graph, Agent Evals, and Agent Tracking tabs all read from.',
    source: 'JobManagerAgent/agents/react_agent.py, JobManagerAgent/api/app.py',
  },
  {
    id: 'jobdataserver',
    label: 'JobDataServer',
    kind: 'compute',
    tech: 'FastAPI',
    detail:
      'FastAPI service exposing CRUD over job_listings and read-only access to job_matches, backing this dashboard\'s Jobs and Matches tabs. JobManagerAgent is the sole writer of job_matches -- this service only reads them, and has no MLflow or agent logic of its own.',
    source: 'JobDataServer/main.py',
  },
  {
    id: 'mlflowserver',
    label: 'MLflowServer',
    kind: 'observability',
    tech: 'MLflow',
    detail:
      "MLflow tracking server, Postgres-backed. Records every live matching cycle (run+trace), every offline eval run (prompt/tool-selection/guardrails), and the versioned prompt registry. JobManagerAgent is the only writer; this dashboard never talks to MLflow directly -- it reads summarized KPIs back through JobManagerAgent's own /mlflow-summary endpoint (see the Agent Tracking tab).",
    source: 'MLflowServer/, JobManagerAgent/utils/mlflow_utils.py',
  },
  {
    id: 'prometheus',
    label: 'Prometheus',
    kind: 'observability',
    tech: 'Prometheus',
    detail:
      "Scrapes JobManagerAgent's /metrics endpoint on an interval (job name job-manager-agent, metrics_path=/metrics) for system-level and custom counters, e.g. guardrail triggers. Lives in its own separate Observability/docker-compose.yml stack, decoupled from the main app's compose file.",
    source: 'Observability/prometheus/prometheus.yml',
  },
  {
    id: 'grafana',
    label: 'Grafana',
    kind: 'observability',
    tech: 'Grafana',
    detail:
      "Dashboards over Prometheus's scraped metrics (datasource type=prometheus). The JobManagerAgent System Metrics dashboard is embedded directly into this app's Observability tab via iframe (kiosk=tv, requires GF_SECURITY_ALLOW_EMBEDDING=true) rather than linked out to.",
    source: 'Observability/grafana/provisioning/datasources/prometheus.yml, dashboards/json/jobmanageragent.json',
  },
  {
    id: 'jobdatadashboard',
    label: 'JobDataDashboard',
    kind: 'frontend',
    tech: 'React',
    detail:
      'This React + Vite SPA. Served by Caddy, which reverse-proxies /api/* to JobDataServer and /agent-api/* to JobManagerAgent so the browser only ever talks to one origin -- everything else falls through to the static SPA build. Also the only place Grafana gets embedded (iframe) and the only place MLflow gets linked out to (via JobManagerAgent\'s deep links).',
    source: 'JobDataDashboard/Caddyfile',
  },
]

const SYSTEM_EDGES: SystemEdge[] = [
  { source: 'webscraper', target: 'postgres', label: 'writes jobs', emphasis: 'primary' },
  { source: 'webscraper', target: 'redis', label: 'pipeline events' },
  { source: 'redis', target: 'jobmanageragent', label: 'triggers cycle' },
  { source: 'jobmanageragent', target: 'postgres', label: 'reads/writes matches', emphasis: 'primary' },
  { source: 'jobmanageragent', target: 'redis', label: 'cycle events' },
  { source: 'jobmanageragent', target: 'mlflowserver', label: 'logs runs & traces', emphasis: 'primary' },
  { source: 'mlflowserver', target: 'postgres', label: 'mlflow db', emphasis: 'observability' },
  { source: 'jobdataserver', target: 'postgres', label: 'CRUD jobs', emphasis: 'primary' },
  { source: 'jobdataserver', target: 'redis', label: 'job events' },
  { source: 'jobdatadashboard', target: 'jobdataserver', label: '/api/*' },
  { source: 'jobdatadashboard', target: 'jobmanageragent', label: '/agent-api/*' },
  { source: 'jobdatadashboard', target: 'grafana', label: 'iframe embed', emphasis: 'observability' },
  { source: 'prometheus', target: 'jobmanageragent', label: 'scrapes /metrics', emphasis: 'observability' },
  { source: 'grafana', target: 'prometheus', label: 'datasource', emphasis: 'observability' },
]

const PIPELINE_STAGES = [
  { title: '1. Ingest', subtitle: 'WebScraper pulls listings' },
  { title: '2. Persist', subtitle: 'Postgres + Redis event log' },
  { title: '3. Process', subtitle: 'Agent matches, API serves' },
  { title: '4. Observe', subtitle: 'MLflow, Prometheus, Grafana' },
  { title: '5. Present', subtitle: 'Dashboard reads it all back' },
]

const KIND_CLASS: Record<SystemNodeKind, string> = {
  ingestion: 'arch-node-ingestion',
  datastore: 'arch-node-datastore',
  compute: 'arch-node-compute',
  observability: 'arch-node-observability',
  frontend: 'arch-node-frontend',
}

const KIND_SUMMARY: Record<SystemNodeKind, string> = {
  ingestion: 'Data source',
  datastore: 'Persisted state',
  compute: 'Processing service',
  observability: 'Tracking & metrics',
  frontend: 'User-facing UI',
}

// One recognizable brand icon per node (not per kind) -- e.g. JobManagerAgent and JobDataServer
// share a "compute" kind/color but run different tech (LangChain vs. plain FastAPI), so the logo
// is what actually differentiates them at a glance.
const NODE_ICON: Record<string, IconType> = {
  webscraper: SiPython,
  postgres: SiPostgresql,
  redis: SiRedis,
  jobmanageragent: SiLangchain,
  jobdataserver: SiFastapi,
  mlflowserver: SiMlflow,
  prometheus: SiPrometheus,
  grafana: SiGrafana,
  jobdatadashboard: SiReact,
}

const MINIMAP_COLOR: Record<SystemNodeKind, string> = {
  ingestion: '#1b5f87',
  datastore: '#785114',
  compute: '#17553b',
  observability: '#4b3787',
  frontend: '#7e2520',
}

const KIND_COLUMN_X: Record<SystemNodeKind, number> = {
  ingestion: 100,
  datastore: 400,
  compute: 700,
  observability: 1000,
  frontend: 1300,
}

function distribute(nodes: SystemNode[], x: number, minY: number, maxY: number): Array<{ node: SystemNode; point: Point }> {
  if (nodes.length === 0) return []
  if (nodes.length === 1) return [{ node: nodes[0], point: { x, y: (minY + maxY) / 2 } }]
  const step = (maxY - minY) / (nodes.length - 1)
  return nodes.map((node, index) => ({ node, point: { x, y: minY + step * index } }))
}

function buildLayout(nodes: SystemNode[]): Map<string, Point> {
  const layout = new Map<string, Point>()
  const kinds: SystemNodeKind[] = ['ingestion', 'datastore', 'compute', 'observability', 'frontend']
  for (const kind of kinds) {
    const nodesOfKind = nodes.filter((node) => node.kind === kind)
    for (const item of distribute(nodesOfKind, KIND_COLUMN_X[kind], 120, 520)) {
      layout.set(item.node.id, item.point)
    }
  }
  return layout
}

function shortSourcePath(source: string): string {
  if (!source) return 'n/a'
  const normalized = source.replace(/\\/g, '/')
  const parts = normalized.split('/')
  if (parts.length <= 2) return normalized
  return `${parts[parts.length - 2]}/${parts[parts.length - 1]}`
}

const ActiveNodeContext = createContext<string | null>(null)

type DetailNodeData = {
  label: string
  kind: SystemNodeKind
  tech: string
  summary: string
  source: string
  isCurrentApp: boolean
}

// The only node that's this actual running app -- everything else in the graph is a service this
// app talks to, but never itself.
const CURRENT_APP_NODE_ID = 'jobdatadashboard'

function DetailNode({ id, data, selected }: NodeProps) {
  const nodeData = data as unknown as DetailNodeData
  const activeNodeId = useContext(ActiveNodeContext)
  const isActive = activeNodeId === id
  const TechIcon = NODE_ICON[id]
  return (
    <div className={`agent-card-node ${KIND_CLASS[nodeData.kind]}${isActive ? ' is-active' : ''}${selected ? ' is-selected' : ''}`}>
      <Handle type="target" position={Position.Left} className="agent-handle" />
      <Handle type="source" position={Position.Right} className="agent-handle" />

      {nodeData.isCurrentApp && <span className="you-are-here-badge">You are here</span>}

      <div className="node-card-layout">
        <div className="node-card-logo-rail">{TechIcon && <TechIcon aria-hidden="true" />}</div>

        <div className="node-card-content">
          <div className="node-card-head">
            <strong className="agent-card-title">{nodeData.label}</strong>
            <span className="agent-card-status">{isActive ? 'FOCUS' : 'LIVE'}</span>
          </div>

          <div className="agent-card-body">
            <p className="agent-card-summary">{nodeData.summary}</p>
            <div className="agent-card-meta-row">
              <span>{nodeData.tech}</span>
            </div>
            <p className="agent-card-source">{shortSourcePath(nodeData.source)}</p>
          </div>
        </div>
      </div>
    </div>
  )
}

function buildFlowNode(node: SystemNode, point: Point) {
  return {
    id: node.id,
    type: 'detailNode',
    position: point,
    data: {
      label: node.label,
      kind: node.kind,
      tech: node.tech,
      summary: KIND_SUMMARY[node.kind],
      source: node.source,
      isCurrentApp: node.id === CURRENT_APP_NODE_ID,
    },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  }
}

export default function SystemArchitectureHero() {
  const [pinnedNodeId, setPinnedNodeId] = useState<string | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)

  const layout = useMemo(() => buildLayout(SYSTEM_NODES), [])
  const fallbackNodeId = SYSTEM_NODES[0]?.id ?? null
  const activeNodeId = pinnedNodeId ?? hoveredNodeId ?? fallbackNodeId
  const activeNode = SYSTEM_NODES.find((node) => node.id === activeNodeId) ?? null
  const ActiveDetailIcon = activeNode ? NODE_ICON[activeNode.id] : null
  const nodeTypes = useMemo(() => ({ detailNode: DetailNode }), [])

  const flowNodes = useMemo(
    () => SYSTEM_NODES.map((node) => buildFlowNode(node, layout.get(node.id) ?? { x: 0, y: 0 })),
    [layout],
  )

  const flowEdges = useMemo(
    () =>
      SYSTEM_EDGES.map((edge, index) => ({
        id: `${edge.source}-${edge.target}-${index}`,
        source: edge.source,
        target: edge.target,
        label: edge.label,
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed, width: 13, height: 13 },
        className: `agent-flow-edge${edge.emphasis === 'primary' ? ' edge-primary' : ''}${edge.emphasis === 'observability' ? ' edge-observability' : ''}`,
        labelStyle: { fill: '#4f6157', fontSize: 10, fontWeight: 600 },
      })),
    [],
  )

  return (
    <section className="agent-hero" aria-label="System architecture">
      <div className="agent-hero-header">
        <p className="eyebrow">ETL Architecture</p>
        <h2>Scrape &rarr; Match &rarr; Track &rarr; Present</h2>
        <p className="agent-hero-subtitle">
          Hover or click a service to see its exact role, what it reads/writes, and where in the codebase it lives.
        </p>
      </div>

      <div className="agent-hero-kpis">
        <article className="agent-hero-chip">
          <span>Services</span>
          <strong>4</strong>
        </article>
        <article className="agent-hero-chip">
          <span>Datastores</span>
          <strong>2</strong>
        </article>
        <article className="agent-hero-chip">
          <span>Observability Tools</span>
          <strong>3</strong>
        </article>
        <article className="agent-hero-chip">
          <span>Deploy Targets</span>
          <strong>Docker Compose + Railway</strong>
        </article>
      </div>

      <h3>Pipeline Stages</h3>
      <div className="agent-flow-stages" aria-label="Pipeline stages">
        {PIPELINE_STAGES.map((stage) => (
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
            {activeNode && ActiveDetailIcon && <ActiveDetailIcon aria-hidden="true" className="agent-detail-tech-icon" />}
            <strong>{activeNode?.label ?? 'No node selected'}</strong>
          </div>
          <p className="agent-detail-source">Source: {activeNode?.source ?? 'n/a'}</p>
          <pre className="agent-detail-content">{activeNode?.detail ?? ''}</pre>
        </aside>
      </div>
    </section>
  )
}
