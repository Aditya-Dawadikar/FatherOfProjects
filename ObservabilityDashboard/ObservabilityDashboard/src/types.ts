export type NodeStatus = 'healthy' | 'warning' | 'error' | 'idle'
export type LogLevel = 'info' | 'warning' | 'error'
export type NodeCategory = 'scraper' | 'storage' | 'backend' | 'stream' | 'worker' | 'dashboard'
export type LivePullState = 'active' | 'inactive' | 'none'
export type LiveSourceState = 'active' | 'inactive' | 'none'
export type RelType =
  | 'triggers'
  | 'writes_to'
  | 'reads_from'
  | 'publishes_to'
  | 'consumes_from'
  | 'serves'
  | 'observes'

export interface NodeRel {
  edgeId: string
  targetNodeId: string
  type: RelType
  label: string
}

export interface LogEntry {
  id: string
  timestamp: string
  level: LogLevel
  message: string
}

export interface EventEntry {
  id: string
  timestamp: string
  label: string
  detail?: string
}

export interface MetricEntry {
  label: string
  value: string
  trend?: 'up' | 'down' | 'flat'
}

export interface SystemNode {
  id: string
  name: string
  category: NodeCategory
  status: NodeStatus
  livePullState?: LivePullState
  liveSourceState?: LiveSourceState
  healthScore: number
  shortDescription: string
  lastSeenAt: string
  upstream: NodeRel[]
  downstream: NodeRel[]
  metrics: MetricEntry[]
  logs: LogEntry[]
  events: EventEntry[]
  cx: number
  cy: number
  width?: number
}

export interface SystemEdge {
  id: string
  source: string
  target: string
  label: string
  status: NodeStatus
  throughput?: string
  lastEventAt?: string
}

export interface SystemDag {
  nodes: SystemNode[]
  edges: SystemEdge[]
}

export interface DashboardNodeSnapshot {
  id: string
  status: NodeStatus
  healthScore: number
  lastSeenAt: string
  metrics: MetricEntry[]
  logs: LogEntry[]
  events: EventEntry[]
}

export interface DashboardEdgeSnapshot {
  id: string
  status: NodeStatus
  throughput?: string
  lastEventAt?: string
}

export interface DashboardSnapshot {
  nodes: DashboardNodeSnapshot[]
  edges: DashboardEdgeSnapshot[]
  system: {
    status: NodeStatus
    avgHealth: number
  }
  stream: {
    configured: boolean
    streams: string[]
    lastEventAt: string | null
    lastEventId: string | null
    lastStreamName: string | null
    eventsSeenTotal: number
    sseClients: number
    lastDispatchAt: string | null
  }
}

export interface DashboardStreamState {
  connected: boolean
  lastEventAt: string | null
}

export interface DashboardUpdateEvent {
  type: 'dashboard-update'
  stream: string
  entryId: string
  eventType: string
  nodeId: string
  emittedAt: string
}

export interface DashboardReadyEvent {
  type: 'connected'
  connectedAt: string
}
