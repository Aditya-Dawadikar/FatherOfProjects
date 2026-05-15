# Observability Dashboard

## Goal

Build a single-page observability dashboard for the website scraper platform. The page should present the whole system as a connected node graph and let the user inspect the health, logs, and metrics of each component without navigating to separate tabs or pages.

The dashboard is meant to feel operational, simple, and visually clean. It should prioritize fast scanning over dense analytics. The UI theme should use dark grey surfaces with green accents to communicate live system health.

## Product Summary

The dashboard represents the end-to-end flow of the scraper platform shown in the architecture diagram:

1. Scheduler triggers the scraper job.
2. Scraper writes job data into the scraped data table.
3. Data server backend exposes scraped data to the viewer UI.
4. Redis stream collects trigger events, job outcomes, probe events, logs, and traces.
5. Log aggregator worker persists observability records into the observability table.
6. Observability server serves live and historical data to the dashboard.
7. Query agent supports operator-style querying over the observability data.

The main user job is to answer three questions quickly:

1. What part of the system is unhealthy right now?
2. What happened recently?
3. What logs and metrics explain the problem?

## Core UX

The application is a single-page interface with three persistent regions:

### 1. Top header

- Product title: Observability Dashboard
- Small environment badge: Local, Staging, or Production
- Last updated timestamp
- Global system status pill: Healthy, Degraded, or Down

### 2. Central node map

- The main canvas is a connected systems diagram inspired by the provided architecture image.
- Each system component is shown as a rounded rectangular node.
- Nodes are grouped into visual clusters:
	- Scraper application flow
	- Observability module
	- Observer dashboard services
- Edges between nodes show data movement or event flow.
- Edges should include lightweight labels where useful, such as Trigger Job, Write to PG, SQL Query, REST HTTP, Logs, Trace, SSE Events.
- The graph should remain readable on a laptop without zoom controls in the first version.

### 3. Inspector panel

- Selecting a node opens or updates a persistent inspector panel on the right side on desktop.
- On smaller screens, the inspector becomes a bottom sheet.
- The inspector contains the operational details for the selected component.
- No tabs. The panel should stack sections vertically.

## Node Inventory

The first version should include these nodes:

### Scraper flow

- Scheduler (Railway Cron Job)
- Scrape YC Website Script
- Postgres Scraped Data Table
- Data Server Backend
- Data Viewer UI

### Observability module

- Redis Stream
- Log Aggregator Worker
- Postgres Observability Table

### Observer dashboard

- Observability Server
- Query Agent
- Observability Dashboard

## Node Status Model

Each node should expose a compact operational state that can be rendered directly on the graph.

Required fields:

- id
- name
- category
- status: healthy | warning | error | idle
- healthScore: 0-100
- lastSeenAt
- shortDescription
- inboundConnections
- outboundConnections

Optional operational metadata:

- serviceType
- host or deployment target
- latestVersion
- owner
- recentIncidentCount

## Inspector Content

When a node is selected, the inspector should show the following blocks in order:

### 1. Node summary

- Node name
- Current status badge
- One-sentence description
- Last heartbeat or last event time
- Current latency or processing duration if available

### 2. Key metrics

Show 3 to 6 compact metric cards depending on the node type.

Examples:

- Success rate
- Error rate
- P95 latency
- Jobs processed in 24h
- Redis backlog depth
- Events per minute
- DB write duration
- SSE client count

### 3. Recent logs

- A small live log list with timestamps
- Use severity color coding for info, warning, and error
- Keep entries scannable: timestamp, source, message
- Limit the first version to the most recent 10 to 20 records

### 4. Recent events

- Health probe results
- Job success or failure events
- Deployment or restart markers
- Query executions

### 5. Related links

- Upstream nodes
- Downstream nodes
- Quick action to focus the linked node in the graph

## Edge Behavior

Connections should communicate system flow without becoming visually noisy.

- Use subtle grey lines for normal connections.
- Use green pulse or glow for active healthy traffic.
- Use amber or red highlighting when a downstream dependency is degraded.
- Hovering an edge should reveal a compact tooltip with:
	- connection name
	- last event time
	- message count or request count
	- error percentage if available

## Visual Direction

The visual style should be understated and technical, not flashy.

### Color palette

- Background: near-black or deep charcoal
- Primary surface: dark grey panels
- Secondary surface: slightly lighter grey for cards and graph groups
- Accent: saturated green
- Healthy: green
- Warning: yellow-green or muted amber
- Error: restrained red
- Text: soft off-white and cool grey

Suggested tokens:

- --bg: #111315
- --panel: #1a1f1d
- --panel-2: #242b28
- --line: #33413b
- --text: #eef3ef
- --muted: #95a39b
- --accent: #4ade80
- --accent-strong: #22c55e
- --warn: #d4b85f
- --error: #e16d6d

### Component styling

- Nodes should have soft rounded corners and thin borders.
- Healthy nodes get a faint green inner glow.
- Selected node gets a stronger green outline and subtle shadow.
- Group containers should use translucent panels with light edge definition.
- Logs and metrics should feel like operator tooling, not marketing cards.

### Motion

- Subtle fade-in on page load
- Soft pulse on active nodes
- Gentle line animation for live event flow
- Inspector should slide in smoothly but quickly

## Information Architecture

The page should read in this order:

1. Header with overall health
2. Large architecture graph as the primary artifact
3. Inspector details for the selected node
4. Small footer or status strip if needed for stream connection state

The graph is the main product surface. The inspector is secondary but always available.

## Default States

### Initial load

- The graph renders with all nodes visible.
- Observability Server is selected by default.
- The inspector shows a meaningful set of live metrics and recent logs.

### Healthy state

- Most nodes appear green-accented but restrained.
- Edge activity is visible but subtle.
- Metrics show stable values.

### Degraded state

- Affected node shifts to warning or error.
- Connected edges visually indicate the impact chain.
- Inspector prioritizes the latest errors and failed probes.

### Empty or disconnected state

- Graph still renders with nodes in idle state.
- Inspector explains that live observability data is unavailable.
- Use helpful placeholders instead of blank areas.

## Suggested Data Contracts

The frontend should treat the system map as a canonical DAG payload. All rendering, selection, inspector content, and relationship traversal should derive from this object graph rather than from hardcoded component-level state.

## State Management Architecture

Use a two-layer state model:

### 1. Server state with TanStack Query

Use TanStack Query and React Query patterns for all API-backed data so network requests are deduplicated, cached, and refetched consistently.

- `systemDag` query for the node and edge graph definition
- `nodeDetails(nodeId)` query for enriched node metadata
- `nodeLogs(nodeId, range)` query for recent logs
- `nodeMetrics(nodeId, range)` query for metric summaries
- `nodeEvents(nodeId, range)` query for recent events
- `systemHealth` query for the global header status

Guidelines:

- Keep query keys stable and parameterized.
- Prefer shared hooks over inline fetches inside components.
- Use stale times for slow-moving metadata such as DAG structure.
- Use shorter refetch intervals only for live operational data.
- Hydrate the inspector from cached query data when revisiting nodes.
- Avoid duplicate fetches by letting node cards and the inspector consume the same query cache.

### 2. Client UI state

Keep local UI state minimal and focused on interaction state:

- selectedNodeId
- hoveredNodeId
- hoveredEdgeId
- activeTimeRange
- inspectorOpen
- graphFocusMode
- searchText or filter text if added later

This state can live in React context or a small app-level store. It should not duplicate API data already managed by TanStack Query.

## DAG-First System Model

The architecture must be defined as a directed acyclic graph. Each node describes itself, how it is observed, and how it relates to upstream and downstream systems.

Rules:

- Every node must have a stable `id`.
- Every edge must point from upstream producer to downstream consumer.
- The graph must remain acyclic.
- The graph definition is the source of truth for connection labels, dependency paths, and inspector relationship lists.
- Impact highlighting should traverse the DAG downstream from a degraded node.
- Related links in the inspector should come from graph relationships, not hand-maintained arrays in components.

### Node

```ts
type NodeStatus = 'healthy' | 'warning' | 'error' | 'idle'

type LogSource = {
	type: 'http' | 'sse' | 'stream' | 'database' | 'static'
	endpoint?: string
	streamName?: string
	table?: string
	queryKey: string[]
	description: string
}

type NodeRelationship = {
	edgeId: string
	targetNodeId: string
	type: 'triggers' | 'writes_to' | 'reads_from' | 'publishes_to' | 'consumes_from' | 'serves' | 'observes'
	label: string
}

type SystemNode = {
	id: string
	name: string
	category: 'scraper' | 'storage' | 'backend' | 'stream' | 'worker' | 'dashboard'
	status: NodeStatus
	healthScore: number
	shortDescription: string
	description: string
	lastSeenAt: string
	logSource: LogSource
	upstream: NodeRelationship[]
	downstream: NodeRelationship[]
	metrics: Array<{
		label: string
		value: string
		trend?: 'up' | 'down' | 'flat'
	}>
	logs: Array<{
		id: string
		timestamp: string
		level: 'info' | 'warning' | 'error'
		message: string
	}>
	events: Array<{
		id: string
		timestamp: string
		label: string
		detail?: string
	}>
}
```

### Canonical node JSON shape

Every node should be serializable in a backend-delivered JSON object with enough information for the graph and inspector to render without additional hardcoded knowledge.

```json
{
	"id": "redis-stream",
	"name": "Redis Stream",
	"category": "stream",
	"status": "healthy",
	"healthScore": 96,
	"shortDescription": "Central event bus for triggers, logs, traces, and health probes.",
	"description": "Receives scraper job events and observability traffic, then fan-outs data to aggregation and live dashboard consumers.",
	"lastSeenAt": "2026-05-15T18:42:00Z",
	"logSource": {
		"type": "stream",
		"streamName": "observability-events",
		"queryKey": ["nodeLogs", "redis-stream", "24h"],
		"description": "Consume recent stream entries exposed by the observability server."
	},
	"upstream": [
		{
			"edgeId": "scraper-to-redis",
			"targetNodeId": "scrape-yc-script",
			"type": "consumes_from",
			"label": "Job Success / Job Failure"
		}
	],
	"downstream": [
		{
			"edgeId": "redis-to-worker",
			"targetNodeId": "log-aggregator-worker",
			"type": "publishes_to",
			"label": "Aggregated event stream"
		}
	],
	"metrics": [
		{ "label": "Events / min", "value": "128", "trend": "up" },
		{ "label": "Backlog", "value": "14", "trend": "flat" }
	],
	"logs": [],
	"events": []
}
```

### Edge

```ts
type SystemEdge = {
	id: string
	source: string
	target: string
	label: string
	status: NodeStatus
	throughput?: string
	lastEventAt?: string
}
```

## System DAG Definition

The first version should define the architecture as explicit nodes plus explicit edges. The UI should derive cluster views, dependency badges, and inspector relationship lists from this DAG.

### Required edges

```ts
const systemEdges: SystemEdge[] = [
	{ id: 'scheduler-to-scraper', source: 'scheduler', target: 'scrape-yc-script', label: 'Trigger Job', status: 'healthy' },
	{ id: 'scraper-to-scraped-db', source: 'scrape-yc-script', target: 'scraped-data-table', label: 'Write to PG', status: 'healthy' },
	{ id: 'scraped-db-to-data-server', source: 'scraped-data-table', target: 'data-server-backend', label: 'SQL Query', status: 'healthy' },
	{ id: 'data-server-to-viewer', source: 'data-server-backend', target: 'data-viewer-ui', label: 'REST HTTP', status: 'healthy' },
	{ id: 'scheduler-to-redis', source: 'scheduler', target: 'redis-stream', label: 'Trigger Events', status: 'healthy' },
	{ id: 'scraper-to-redis', source: 'scrape-yc-script', target: 'redis-stream', label: 'Job Success / Job Failure', status: 'healthy' },
	{ id: 'scraped-db-to-redis', source: 'scraped-data-table', target: 'redis-stream', label: 'Liveness / Health Probes', status: 'healthy' },
	{ id: 'data-server-to-redis', source: 'data-server-backend', target: 'redis-stream', label: 'Logs / Trace', status: 'healthy' },
	{ id: 'viewer-to-redis', source: 'data-viewer-ui', target: 'redis-stream', label: 'Sentry Performance Metrics', status: 'healthy' },
	{ id: 'redis-to-worker', source: 'redis-stream', target: 'log-aggregator-worker', label: 'Live Data', status: 'healthy' },
	{ id: 'worker-to-observability-db', source: 'log-aggregator-worker', target: 'observability-table', label: 'Persist History', status: 'healthy' },
	{ id: 'redis-to-observability-server', source: 'redis-stream', target: 'observability-server', label: 'Live Logs / Trace', status: 'healthy' },
	{ id: 'observability-db-to-observability-server', source: 'observability-table', target: 'observability-server', label: 'Historical Data', status: 'healthy' },
	{ id: 'query-agent-to-observability-server', source: 'query-agent', target: 'observability-server', label: 'Structured Query', status: 'healthy' },
	{ id: 'observability-server-to-dashboard', source: 'observability-server', target: 'observability-dashboard', label: 'SSE Events + REST', status: 'healthy' }
]
```

### Relationship semantics

- `triggers`: job kickoff or schedule-driven control flow
- `writes_to`: persistent storage writes
- `reads_from`: query or data fetch dependency
- `publishes_to`: stream or event emission
- `consumes_from`: stream or queue consumption
- `serves`: API or SSE delivery to a UI or dependent service
- `observes`: probe, telemetry, log, metric, or trace collection path

## Log Consumption Contract

Every node must define where its logs should be consumed from so the inspector can render a consistent log section without special-case branching.

Required per node:

- canonical log source type
- backing endpoint, stream, or table
- query key for TanStack Query
- human-readable description of what the log feed represents

Recommended mapping for the first version:

- Scheduler: logs exposed by Observability Server from Railway cron executions
- Scrape YC Website Script: job execution logs exposed by Observability Server from Redis-streamed scraper events
- Postgres Scraped Data Table: probe and write health logs exposed by Observability Server
- Data Server Backend: API logs and traces exposed by Observability Server
- Data Viewer UI: client-side performance and error logs exposed by Observability Server from Sentry-style ingestion
- Redis Stream: stream activity logs and backlog metrics exposed by Observability Server
- Log Aggregator Worker: worker processing logs exposed by Observability Server
- Postgres Observability Table: persistence and query health logs exposed by Observability Server
- Observability Server: direct server logs and SSE delivery health
- Query Agent: query execution logs exposed by Observability Server
- Observability Dashboard: front-end runtime and performance events exposed by Observability Server

## MVP Scope

The first implementation should include:

- Static node layout matching the architecture diagram
- Click-to-inspect interactions
- Mock data for metrics, logs, and events
- Status-aware node and edge styling
- Responsive single-page layout
- Dark grey and green aesthetic

The first implementation does not need:

- Authentication
- Multi-page navigation
- Drag-and-drop node editing
- Advanced time-range controls
- Full tracing explorer
- Complex charting libraries unless clearly needed

## Frontend Notes

- Build with React and TypeScript inside the existing Vite app.
- Use `@tanstack/react-query` as the standard API state layer.
- Keep the page single-screen and lightweight.
- Prefer a fixed layout with a graph stage and inspector rather than a dashboard grid.
- Use reusable DAG-based node and edge structures so the UI can later connect to live APIs.
- Avoid overengineering the graph. The first version can use absolute positioning or CSS grid if it keeps the architecture readable.
- Build a small query layer with hooks such as `useSystemDag`, `useNodeDetails`, `useNodeLogs`, and `useNodeMetrics`.
- Keep selection and hover state local to the app shell while all fetchable data stays in the React Query cache.

## Success Criteria

The project is successful when:

1. A user can understand the system architecture within a few seconds.
2. A user can click any node and inspect recent logs and health metrics immediately.
3. The visual design feels cohesive, dark, and operational with green-accented status cues.
4. The page works well on desktop and remains usable on smaller screens.

## Build Sequence

Recommended implementation order:

1. Define node and edge data models.
2. Build the graph layout with grouped node sections.
3. Add node selection and inspector behavior.
4. Add metrics, logs, and event blocks.
5. Apply dark grey and green styling.
6. Add small motion and responsive behavior.

