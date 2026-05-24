import type { SystemDag, SystemNode, SystemEdge } from '../types'

// Canvas: 920 × 510 px
// Node default: width=148, height=52 (hw=74, hh=26)
// Redis Stream: width=200 (hw=100)
// Positions are center coordinates (cx, cy)

const nodes: SystemNode[] = [
  {
    id: 'scrape-yc-script',
    name: 'WebScraper',
    category: 'scraper',
    status: 'healthy',
    healthScore: 95,
    shortDescription: 'Runs on a schedule, scrapes job data, writes to Postgres, and emits run events to Redis.',
    lastSeenAt: '18:45:12',
    cx: 120, cy: 185,
    upstream: [],
    downstream: [
      { edgeId: 'scraper-to-scraped-db', targetNodeId: 'scraped-data-table', type: 'writes_to', label: 'Write jobs' },
      { edgeId: 'scraper-to-redis', targetNodeId: 'redis-stream', type: 'publishes_to', label: 'Publish run events' },
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
    name: 'Postgres',
    category: 'storage',
    status: 'healthy',
    healthScore: 99,
    shortDescription: 'Primary Postgres datastore holding the scraped job data used by the application.',
    lastSeenAt: '18:45:12',
    cx: 330, cy: 185,
    upstream: [
      { edgeId: 'scraper-to-scraped-db', targetNodeId: 'scrape-yc-script', type: 'writes_to', label: 'Write jobs' },
      { edgeId: 'data-server-to-scraped-db', targetNodeId: 'data-server-backend', type: 'writes_to', label: 'CRUD on PG' },
    ],
    downstream: [],
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
    name: 'JobDataServer',
    category: 'backend',
    status: 'healthy',
    healthScore: 97,
    shortDescription: 'CRUD API for the Postgres job data that also emits server-side telemetry to Redis.',
    lastSeenAt: '18:44:59',
    cx: 330, cy: 340,
    upstream: [],
    downstream: [
      { edgeId: 'data-server-to-scraped-db', targetNodeId: 'scraped-data-table', type: 'writes_to', label: 'CRUD on PG' },
      { edgeId: 'data-server-to-redis', targetNodeId: 'redis-stream', type: 'publishes_to', label: 'Publish API telemetry' },
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
    id: 'redis-stream',
    name: 'Redis',
    category: 'stream',
    status: 'healthy',
    healthScore: 96,
    shortDescription: 'Redis Streams backbone carrying scraper runs plus API logs, metrics, and traces.',
    lastSeenAt: '18:45:00',
    cx: 510, cy: 225,
    width: 200,
    upstream: [
      { edgeId: 'scraper-to-redis', targetNodeId: 'scrape-yc-script', type: 'consumes_from', label: 'Run events' },
      { edgeId: 'data-server-to-redis', targetNodeId: 'data-server-backend', type: 'consumes_from', label: 'API telemetry' },
    ],
    downstream: [
      { edgeId: 'redis-to-observability-server', targetNodeId: 'observability-server', type: 'publishes_to', label: 'Logs, metrics, traces' },
    ],
    metrics: [
      { label: 'Events / min', value: '128', trend: 'up' },
      { label: 'Streams tracked', value: '2', trend: 'flat' },
      { label: 'Consumers', value: '1', trend: 'flat' },
      { label: 'Memory used', value: '12 MB', trend: 'flat' },
    ],
    logs: [
      { id: 'l1', timestamp: '18:45:00', level: 'info', message: 'Entry: job.completed — #1248' },
      { id: 'l2', timestamp: '18:44:59', level: 'info', message: 'Entry: log.data-server — GET /api/companies' },
      { id: 'l3', timestamp: '18:44:58', level: 'info', message: 'Entry: stage.write — job_count=214 written_count=214' },
      { id: 'l4', timestamp: '18:44:40', level: 'info', message: 'Consumer: observability-server — live stream connected' },
    ],
    events: [
      { id: 'e1', timestamp: '18:45:00', label: 'Job completed event', detail: '#1248 published to stream' },
      { id: 'e2', timestamp: '18:44:40', label: 'Consumer connected', detail: 'observability-server attached to live stream' },
    ],
  },
  {
    id: 'observability-server',
    name: 'ObservabilityServer',
    category: 'backend',
    status: 'healthy',
    healthScore: 99,
    shortDescription: 'Consumes Redis logs, metrics, and traces and exposes them to the dashboard over REST and SSE.',
    lastSeenAt: '18:45:01',
    cx: 775, cy: 225,
    upstream: [
      { edgeId: 'redis-to-observability-server', targetNodeId: 'redis-stream', type: 'consumes_from', label: 'Logs, metrics, traces' },
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
    id: 'observability-dashboard',
    name: 'ObservabilityDashboard',
    category: 'dashboard',
    status: 'healthy',
    healthScore: 100,
    shortDescription: 'Visualization UI for the live observability feeds coming from the ObservabilityServer.',
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
  { id: 'scraper-to-scraped-db',               source: 'scrape-yc-script',       target: 'scraped-data-table',      label: 'Write jobs',             status: 'healthy', throughput: '214 rows', lastEventAt: '18:45:12' },
  { id: 'data-server-to-scraped-db',           source: 'data-server-backend',    target: 'scraped-data-table',      label: 'CRUD on PG',             status: 'healthy', lastEventAt: '18:44:59' },
  { id: 'scraper-to-redis',                    source: 'scrape-yc-script',       target: 'redis-stream',            label: 'Publish run events',     status: 'healthy', lastEventAt: '18:45:00' },
  { id: 'data-server-to-redis',                source: 'data-server-backend',    target: 'redis-stream',            label: 'Publish API telemetry',  status: 'healthy', lastEventAt: '18:44:59' },
  { id: 'redis-to-observability-server',       source: 'redis-stream',           target: 'observability-server',    label: 'Logs, metrics, traces',  status: 'healthy', lastEventAt: '18:45:01' },
  { id: 'observability-server-to-dashboard',   source: 'observability-server',   target: 'observability-dashboard', label: 'REST + SSE',              status: 'healthy', lastEventAt: '18:45:01' },
]

export const systemDag: SystemDag = { nodes, edges }
