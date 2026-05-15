import type { SystemDag, SystemNode, SystemEdge } from '../types'

// Canvas: 920 × 510 px
// Node default: width=148, height=52 (hw=74, hh=26)
// Redis Stream: width=200 (hw=100)
// Positions are center coordinates (cx, cy)

const nodes: SystemNode[] = [
  {
    id: 'scheduler',
    name: 'Scheduler',
    category: 'scraper',
    status: 'healthy',
    healthScore: 98,
    shortDescription: 'Railway cron job that triggers the scraper on a fixed schedule.',
    lastSeenAt: '18:44:01',
    cx: 100, cy: 75,
    upstream: [],
    downstream: [
      { edgeId: 'scheduler-to-scraper', targetNodeId: 'scrape-yc-script', type: 'triggers', label: 'Trigger Job' },
      { edgeId: 'scheduler-to-redis', targetNodeId: 'redis-stream', type: 'publishes_to', label: 'Trigger Events' },
    ],
    metrics: [
      { label: 'Jobs triggered (24h)', value: '6', trend: 'flat' },
      { label: 'Success rate', value: '100%', trend: 'flat' },
      { label: 'Avg trigger delay', value: '420ms', trend: 'flat' },
    ],
    logs: [
      { id: 'l1', timestamp: '18:44:01', level: 'info', message: 'Cron trigger fired — dispatching scrape-yc-script' },
      { id: 'l2', timestamp: '14:44:01', level: 'info', message: 'Cron trigger fired — dispatching scrape-yc-script' },
      { id: 'l3', timestamp: '10:44:01', level: 'info', message: 'Cron trigger fired — dispatching scrape-yc-script' },
      { id: 'l4', timestamp: '06:44:01', level: 'info', message: 'Cron trigger fired — dispatching scrape-yc-script' },
    ],
    events: [
      { id: 'e1', timestamp: '18:44:01', label: 'Cron fired', detail: 'Job #1248 dispatched' },
      { id: 'e2', timestamp: '14:44:01', label: 'Cron fired', detail: 'Job #1247 dispatched' },
      { id: 'e3', timestamp: '10:44:01', label: 'Cron fired', detail: 'Job #1246 dispatched' },
    ],
  },
  {
    id: 'scrape-yc-script',
    name: 'Scrape YC Script',
    category: 'scraper',
    status: 'healthy',
    healthScore: 95,
    shortDescription: 'Scraper that fetches YC company data and writes records to Postgres.',
    lastSeenAt: '18:45:12',
    cx: 100, cy: 185,
    upstream: [
      { edgeId: 'scheduler-to-scraper', targetNodeId: 'scheduler', type: 'triggers', label: 'Trigger Job' },
    ],
    downstream: [
      { edgeId: 'scraper-to-scraped-db', targetNodeId: 'scraped-data-table', type: 'writes_to', label: 'Write to PG' },
      { edgeId: 'scraper-to-redis', targetNodeId: 'redis-stream', type: 'publishes_to', label: 'Job Success / Failure' },
    ],
    metrics: [
      { label: 'Jobs (24h)', value: '6', trend: 'flat' },
      { label: 'Avg duration', value: '47s', trend: 'flat' },
      { label: 'Records written', value: '1,284', trend: 'up' },
      { label: 'Error rate', value: '0%', trend: 'flat' },
    ],
    logs: [
      { id: 'l1', timestamp: '18:45:12', level: 'info', message: 'Job #1248 completed — 214 companies written' },
      { id: 'l2', timestamp: '18:44:31', level: 'info', message: 'Job #1248 started' },
      { id: 'l3', timestamp: '14:45:09', level: 'info', message: 'Job #1247 completed — 211 companies written' },
      { id: 'l4', timestamp: '10:45:03', level: 'info', message: 'Job #1246 completed — 209 companies written' },
      { id: 'l5', timestamp: '06:44:58', level: 'info', message: 'Job #1245 completed — 208 companies written' },
    ],
    events: [
      { id: 'e1', timestamp: '18:45:12', label: 'Job success', detail: '#1248 — 214 records in 47s' },
      { id: 'e2', timestamp: '14:45:09', label: 'Job success', detail: '#1247 — 211 records in 45s' },
      { id: 'e3', timestamp: '10:45:03', label: 'Job success', detail: '#1246 — 209 records in 44s' },
    ],
  },
  {
    id: 'scraped-data-table',
    name: 'Scraped Data Table',
    category: 'storage',
    status: 'healthy',
    healthScore: 99,
    shortDescription: 'Postgres table storing raw scraped YC company records.',
    lastSeenAt: '18:45:12',
    cx: 100, cy: 295,
    upstream: [
      { edgeId: 'scraper-to-scraped-db', targetNodeId: 'scrape-yc-script', type: 'writes_to', label: 'Write to PG' },
    ],
    downstream: [
      { edgeId: 'scraped-db-to-data-server', targetNodeId: 'data-server-backend', type: 'reads_from', label: 'SQL Query' },
      { edgeId: 'scraped-db-to-redis', targetNodeId: 'redis-stream', type: 'publishes_to', label: 'Health Probes' },
    ],
    metrics: [
      { label: 'Row count', value: '28,341', trend: 'up' },
      { label: 'Write latency P95', value: '12ms', trend: 'flat' },
      { label: 'Read latency P95', value: '8ms', trend: 'flat' },
      { label: 'Table size', value: '94 MB', trend: 'up' },
    ],
    logs: [
      { id: 'l1', timestamp: '18:45:12', level: 'info', message: 'Batch insert: 214 rows — 11ms' },
      { id: 'l2', timestamp: '18:45:10', level: 'info', message: 'Health probe: OK' },
      { id: 'l3', timestamp: '18:42:10', level: 'info', message: 'Health probe: OK' },
      { id: 'l4', timestamp: '18:39:10', level: 'info', message: 'Health probe: OK' },
    ],
    events: [
      { id: 'e1', timestamp: '18:45:12', label: 'Batch write', detail: '214 rows inserted in 11ms' },
      { id: 'e2', timestamp: '18:45:10', label: 'Health probe passed' },
      { id: 'e3', timestamp: '14:45:09', label: 'Batch write', detail: '211 rows inserted in 10ms' },
    ],
  },
  {
    id: 'data-server-backend',
    name: 'Data Server',
    category: 'backend',
    status: 'healthy',
    healthScore: 97,
    shortDescription: 'REST API that queries Postgres and serves scraped data to the viewer UI.',
    lastSeenAt: '18:44:59',
    cx: 100, cy: 405,
    upstream: [
      { edgeId: 'scraped-db-to-data-server', targetNodeId: 'scraped-data-table', type: 'reads_from', label: 'SQL Query' },
    ],
    downstream: [
      { edgeId: 'data-server-to-viewer', targetNodeId: 'data-viewer-ui', type: 'serves', label: 'REST HTTP' },
      { edgeId: 'data-server-to-redis', targetNodeId: 'redis-stream', type: 'publishes_to', label: 'Logs / Trace' },
    ],
    metrics: [
      { label: 'Req / min', value: '42', trend: 'flat' },
      { label: 'P95 latency', value: '38ms', trend: 'flat' },
      { label: 'Error rate', value: '0.2%', trend: 'flat' },
      { label: 'Uptime', value: '99.97%', trend: 'flat' },
    ],
    logs: [
      { id: 'l1', timestamp: '18:44:59', level: 'info', message: 'GET /api/companies 200 — 36ms' },
      { id: 'l2', timestamp: '18:44:53', level: 'info', message: 'GET /api/companies 200 — 41ms' },
      { id: 'l3', timestamp: '18:43:11', level: 'warning', message: 'GET /api/companies 200 — 210ms (slow query)' },
      { id: 'l4', timestamp: '18:41:02', level: 'info', message: 'GET /api/companies 200 — 35ms' },
    ],
    events: [
      { id: 'e1', timestamp: '18:43:11', label: 'Slow query', detail: '210ms — above P95 threshold' },
      { id: 'e2', timestamp: '18:30:00', label: 'Deployment', detail: 'v1.4.2 deployed' },
    ],
  },
  {
    id: 'data-viewer-ui',
    name: 'Data Viewer UI',
    category: 'dashboard',
    status: 'healthy',
    healthScore: 100,
    shortDescription: 'Frontend for browsing and searching scraped company data.',
    lastSeenAt: '18:44:55',
    cx: 280, cy: 405,
    upstream: [
      { edgeId: 'data-server-to-viewer', targetNodeId: 'data-server-backend', type: 'serves', label: 'REST HTTP' },
    ],
    downstream: [
      { edgeId: 'viewer-to-redis', targetNodeId: 'redis-stream', type: 'publishes_to', label: 'Sentry Performance' },
    ],
    metrics: [
      { label: 'Active sessions', value: '3', trend: 'flat' },
      { label: 'Page load P95', value: '820ms', trend: 'flat' },
      { label: 'JS errors (24h)', value: '0', trend: 'flat' },
    ],
    logs: [
      { id: 'l1', timestamp: '18:44:55', level: 'info', message: 'Page load: / — 810ms' },
      { id: 'l2', timestamp: '18:44:20', level: 'info', message: 'Page load: / — 824ms' },
      { id: 'l3', timestamp: '18:43:45', level: 'info', message: 'Page load: / — 815ms' },
    ],
    events: [
      { id: 'e1', timestamp: '18:44:55', label: 'Page load', detail: '810ms — 3 active sessions' },
    ],
  },
  {
    id: 'redis-stream',
    name: 'Redis Stream',
    category: 'stream',
    status: 'healthy',
    healthScore: 96,
    shortDescription: 'Central event bus for triggers, job outcomes, logs, traces, and health probes.',
    lastSeenAt: '18:45:00',
    cx: 510, cy: 225,
    width: 200,
    upstream: [
      { edgeId: 'scheduler-to-redis', targetNodeId: 'scheduler', type: 'consumes_from', label: 'Trigger Events' },
      { edgeId: 'scraper-to-redis', targetNodeId: 'scrape-yc-script', type: 'consumes_from', label: 'Job Events' },
      { edgeId: 'scraped-db-to-redis', targetNodeId: 'scraped-data-table', type: 'consumes_from', label: 'Health Probes' },
      { edgeId: 'data-server-to-redis', targetNodeId: 'data-server-backend', type: 'consumes_from', label: 'Logs / Trace' },
      { edgeId: 'viewer-to-redis', targetNodeId: 'data-viewer-ui', type: 'consumes_from', label: 'Sentry Performance' },
    ],
    downstream: [
      { edgeId: 'redis-to-worker', targetNodeId: 'log-aggregator-worker', type: 'publishes_to', label: 'Live Data' },
      { edgeId: 'redis-to-observability-server', targetNodeId: 'observability-server', type: 'publishes_to', label: 'Live Logs / Trace' },
    ],
    metrics: [
      { label: 'Events / min', value: '128', trend: 'up' },
      { label: 'Backlog depth', value: '14', trend: 'flat' },
      { label: 'Consumers', value: '2', trend: 'flat' },
      { label: 'Memory used', value: '12 MB', trend: 'flat' },
    ],
    logs: [
      { id: 'l1', timestamp: '18:45:00', level: 'info', message: 'Entry: job.completed — #1248' },
      { id: 'l2', timestamp: '18:44:59', level: 'info', message: 'Entry: log.data-server — GET /api/companies' },
      { id: 'l3', timestamp: '18:44:58', level: 'info', message: 'Entry: probe.scraped-db — OK' },
      { id: 'l4', timestamp: '18:44:40', level: 'warning', message: 'Consumer lag: log-aggregator-worker — 14 entries behind' },
    ],
    events: [
      { id: 'e1', timestamp: '18:45:00', label: 'Job completed event', detail: '#1248 published to stream' },
      { id: 'e2', timestamp: '18:44:40', label: 'Consumer lag', detail: 'log-aggregator-worker at 14 entries' },
    ],
  },
  {
    id: 'log-aggregator-worker',
    name: 'Log Aggregator',
    category: 'worker',
    status: 'warning',
    healthScore: 74,
    shortDescription: 'Worker that consumes Redis stream entries and persists observability records to Postgres.',
    lastSeenAt: '18:44:41',
    cx: 510, cy: 340,
    upstream: [
      { edgeId: 'redis-to-worker', targetNodeId: 'redis-stream', type: 'consumes_from', label: 'Live Data' },
    ],
    downstream: [
      { edgeId: 'worker-to-observability-db', targetNodeId: 'observability-table', type: 'writes_to', label: 'Persist History' },
    ],
    metrics: [
      { label: 'Events processed (1h)', value: '4,821', trend: 'flat' },
      { label: 'Write latency P95', value: '34ms', trend: 'up' },
      { label: 'Consumer lag', value: '14', trend: 'up' },
      { label: 'Error rate', value: '0.8%', trend: 'up' },
    ],
    logs: [
      { id: 'l1', timestamp: '18:44:41', level: 'warning', message: 'Consumer lag growing: 14 entries behind stream head' },
      { id: 'l2', timestamp: '18:44:35', level: 'info', message: 'Batch flush: 48 records written in 32ms' },
      { id: 'l3', timestamp: '18:44:01', level: 'warning', message: 'Write latency spike: 89ms (threshold: 50ms)' },
      { id: 'l4', timestamp: '18:43:55', level: 'info', message: 'Batch flush: 47 records written in 28ms' },
    ],
    events: [
      { id: 'e1', timestamp: '18:44:41', label: 'Consumer lag warning', detail: '14 entries behind stream head' },
      { id: 'e2', timestamp: '18:44:01', label: 'Write latency spike', detail: '89ms — P95 threshold exceeded' },
      { id: 'e3', timestamp: '18:30:00', label: 'Worker restart', detail: 'Recovered after OOM signal' },
    ],
  },
  {
    id: 'observability-table',
    name: 'Observability Table',
    category: 'storage',
    status: 'healthy',
    healthScore: 98,
    shortDescription: 'Postgres table persisting all observability records and event history.',
    lastSeenAt: '18:44:35',
    cx: 510, cy: 445,
    upstream: [
      { edgeId: 'worker-to-observability-db', targetNodeId: 'log-aggregator-worker', type: 'writes_to', label: 'Persist History' },
    ],
    downstream: [
      { edgeId: 'observability-db-to-observability-server', targetNodeId: 'observability-server', type: 'reads_from', label: 'Historical Data' },
    ],
    metrics: [
      { label: 'Row count', value: '1.2M', trend: 'up' },
      { label: 'Write latency P95', value: '18ms', trend: 'flat' },
      { label: 'Table size', value: '4.2 GB', trend: 'up' },
    ],
    logs: [
      { id: 'l1', timestamp: '18:44:35', level: 'info', message: 'Insert batch: 48 rows — 17ms' },
      { id: 'l2', timestamp: '18:44:28', level: 'info', message: 'Insert batch: 51 rows — 18ms' },
      { id: 'l3', timestamp: '18:43:55', level: 'info', message: 'Insert batch: 47 rows — 16ms' },
    ],
    events: [
      { id: 'e1', timestamp: '18:44:35', label: 'Batch write', detail: '48 rows in 17ms' },
      { id: 'e2', timestamp: '18:30:00', label: 'VACUUM completed', detail: '120 dead tuples reclaimed' },
    ],
  },
  {
    id: 'observability-server',
    name: 'Observability Server',
    category: 'backend',
    status: 'healthy',
    healthScore: 99,
    shortDescription: 'Serves live and historical observability data via SSE and REST to this dashboard.',
    lastSeenAt: '18:45:01',
    cx: 775, cy: 225,
    upstream: [
      { edgeId: 'redis-to-observability-server', targetNodeId: 'redis-stream', type: 'consumes_from', label: 'Live Logs / Trace' },
      { edgeId: 'observability-db-to-observability-server', targetNodeId: 'observability-table', type: 'reads_from', label: 'Historical Data' },
      { edgeId: 'query-agent-to-observability-server', targetNodeId: 'query-agent', type: 'serves', label: 'Structured Query' },
    ],
    downstream: [
      { edgeId: 'observability-server-to-dashboard', targetNodeId: 'observability-dashboard', type: 'serves', label: 'SSE Events + REST' },
    ],
    metrics: [
      { label: 'SSE clients', value: '1', trend: 'flat' },
      { label: 'Req / min', value: '18', trend: 'flat' },
      { label: 'P95 latency', value: '22ms', trend: 'flat' },
      { label: 'Uptime', value: '99.99%', trend: 'flat' },
      { label: 'Stream lag', value: '0ms', trend: 'flat' },
    ],
    logs: [
      { id: 'l1', timestamp: '18:45:01', level: 'info', message: 'SSE dispatched — job.completed #1248' },
      { id: 'l2', timestamp: '18:45:00', level: 'info', message: 'GET /api/nodes/redis-stream 200 — 20ms' },
      { id: 'l3', timestamp: '18:44:45', level: 'info', message: 'GET /api/system/dag 200 — 14ms' },
      { id: 'l4', timestamp: '18:44:30', level: 'info', message: 'GET /api/nodes/scheduler/logs 200 — 31ms' },
    ],
    events: [
      { id: 'e1', timestamp: '18:45:01', label: 'SSE dispatched', detail: 'job.completed #1248 → 1 client' },
      { id: 'e2', timestamp: '18:30:00', label: 'Deployment', detail: 'v0.9.1 deployed' },
      { id: 'e3', timestamp: '18:00:00', label: 'Health check passed' },
    ],
  },
  {
    id: 'query-agent',
    name: 'Query Agent',
    category: 'backend',
    status: 'idle',
    healthScore: 100,
    shortDescription: 'AI-powered agent for natural-language queries over observability data.',
    lastSeenAt: '17:30:00',
    cx: 775, cy: 115,
    upstream: [],
    downstream: [
      { edgeId: 'query-agent-to-observability-server', targetNodeId: 'observability-server', type: 'serves', label: 'Structured Query' },
    ],
    metrics: [
      { label: 'Queries (24h)', value: '3', trend: 'flat' },
      { label: 'Avg query time', value: '1.4s', trend: 'flat' },
      { label: 'Last query', value: '1h ago', trend: 'flat' },
    ],
    logs: [
      { id: 'l1', timestamp: '17:30:00', level: 'info', message: 'Query: "Show error logs for log-aggregator-worker in last 2h"' },
      { id: 'l2', timestamp: '14:00:00', level: 'info', message: 'Query: "What is the current Redis backlog depth?"' },
      { id: 'l3', timestamp: '10:00:00', level: 'info', message: 'Query: "Summarize all job runs since midnight"' },
    ],
    events: [
      { id: 'e1', timestamp: '17:30:00', label: 'Query executed', detail: 'Completed in 1.2s' },
      { id: 'e2', timestamp: '14:00:00', label: 'Query executed', detail: 'Completed in 1.6s' },
    ],
  },
  {
    id: 'observability-dashboard',
    name: 'Obs. Dashboard',
    category: 'dashboard',
    status: 'healthy',
    healthScore: 100,
    shortDescription: 'This page — the single-pane observability interface for the scraper platform.',
    lastSeenAt: '18:45:01',
    cx: 775, cy: 345,
    upstream: [
      { edgeId: 'observability-server-to-dashboard', targetNodeId: 'observability-server', type: 'serves', label: 'SSE Events + REST' },
    ],
    downstream: [],
    metrics: [
      { label: 'SSE connected', value: 'Yes', trend: 'flat' },
      { label: 'Active sessions', value: '1', trend: 'flat' },
      { label: 'Last event', value: '< 1s ago', trend: 'flat' },
    ],
    logs: [
      { id: 'l1', timestamp: '18:45:01', level: 'info', message: 'SSE received: job.completed #1248' },
      { id: 'l2', timestamp: '18:44:45', level: 'info', message: 'DAG refresh: 11 nodes, 15 edges loaded' },
      { id: 'l3', timestamp: '18:44:00', level: 'info', message: 'SSE connection established' },
    ],
    events: [
      { id: 'e1', timestamp: '18:45:01', label: 'SSE event received', detail: 'job.completed #1248' },
      { id: 'e2', timestamp: '18:44:45', label: 'DAG refreshed', detail: '11 nodes, 15 edges' },
    ],
  },
]

const edges: SystemEdge[] = [
  { id: 'scheduler-to-scraper',                source: 'scheduler',              target: 'scrape-yc-script',        label: 'Trigger Job',          status: 'healthy', lastEventAt: '18:44:01' },
  { id: 'scraper-to-scraped-db',               source: 'scrape-yc-script',       target: 'scraped-data-table',      label: 'Write to PG',          status: 'healthy', throughput: '214 rows', lastEventAt: '18:45:12' },
  { id: 'scraped-db-to-data-server',           source: 'scraped-data-table',     target: 'data-server-backend',     label: 'SQL Query',            status: 'healthy', lastEventAt: '18:44:59' },
  { id: 'data-server-to-viewer',               source: 'data-server-backend',    target: 'data-viewer-ui',          label: 'REST HTTP',            status: 'healthy', lastEventAt: '18:44:59' },
  { id: 'scheduler-to-redis',                  source: 'scheduler',              target: 'redis-stream',            label: 'Trigger Events',       status: 'healthy', lastEventAt: '18:44:01' },
  { id: 'scraper-to-redis',                    source: 'scrape-yc-script',       target: 'redis-stream',            label: 'Job Success / Failure', status: 'healthy', lastEventAt: '18:45:00' },
  { id: 'scraped-db-to-redis',                 source: 'scraped-data-table',     target: 'redis-stream',            label: 'Health Probes',        status: 'healthy', lastEventAt: '18:45:10' },
  { id: 'data-server-to-redis',                source: 'data-server-backend',    target: 'redis-stream',            label: 'Logs / Trace',         status: 'healthy', lastEventAt: '18:44:59' },
  { id: 'viewer-to-redis',                     source: 'data-viewer-ui',         target: 'redis-stream',            label: 'Sentry Metrics',       status: 'healthy', lastEventAt: '18:44:55' },
  { id: 'redis-to-worker',                     source: 'redis-stream',           target: 'log-aggregator-worker',   label: 'Live Data',            status: 'warning', lastEventAt: '18:44:41' },
  { id: 'worker-to-observability-db',          source: 'log-aggregator-worker',  target: 'observability-table',     label: 'Persist History',      status: 'warning', lastEventAt: '18:44:35' },
  { id: 'redis-to-observability-server',       source: 'redis-stream',           target: 'observability-server',    label: 'Live Logs / Trace',    status: 'healthy', lastEventAt: '18:45:01' },
  { id: 'observability-db-to-observability-server', source: 'observability-table', target: 'observability-server', label: 'Historical Data',      status: 'healthy', lastEventAt: '18:44:35' },
  { id: 'query-agent-to-observability-server', source: 'query-agent',            target: 'observability-server',    label: 'Structured Query',     status: 'idle',    lastEventAt: '17:30:00' },
  { id: 'observability-server-to-dashboard',   source: 'observability-server',   target: 'observability-dashboard', label: 'SSE Events + REST',    status: 'healthy', lastEventAt: '18:45:01' },
]

export const systemDag: SystemDag = { nodes, edges }
