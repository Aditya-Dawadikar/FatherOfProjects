import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { systemDag } from '../data/dag'
import type {
  DashboardSnapshot,
  LiveSourceState,
  DashboardStreamState,
  LivePullState,
  SystemDag,
  SystemEdge,
  SystemNode,
} from '../types'

const API_BASE = (import.meta.env.DEV ? import.meta.env.VITE_OBSERVABILITY_API_BASE_URL ?? '' : '').replace(/\/$/, '')
const DAG_STALE = 5_000
const NODE_STALE = 5_000
const SYSTEM_DAG_QUERY_KEY = ['systemDag'] as const
const LIVE_EDGE_SOURCE = 'redis-stream'
const LIVE_EDGE_TARGET = 'redis-stream'

function buildInactiveMetrics(baseNode: SystemNode) {
  return [
    { label: 'Live data', value: 'Not observed', trend: 'flat' as const },
    { label: 'Source', value: baseNode.category === 'stream' ? 'Polling idle' : 'No active feed', trend: 'flat' as const },
  ]
}

function buildApiUrl(path: string) {
  return `${API_BASE}${path}`
}

async function fetchDashboardSnapshot(): Promise<DashboardSnapshot> {
  const response = await fetch(buildApiUrl('/api/dashboard'))
  if (!response.ok) {
    throw new Error(`Dashboard request failed with ${response.status}`)
  }
  return response.json() as Promise<DashboardSnapshot>
}

function mergeNode(baseNode: SystemNode, snapshot: DashboardSnapshot['nodes'][number] | undefined): SystemNode {
  if (!snapshot) {
    return {
      ...baseNode,
      status: 'idle',
      healthScore: 78,
      lastSeenAt: '--:--:--',
      metrics: buildInactiveMetrics(baseNode),
      logs: [],
      events: [],
    }
  }
  return {
    ...baseNode,
    status: snapshot.status,
    healthScore: snapshot.healthScore,
    lastSeenAt: snapshot.lastSeenAt,
    metrics: snapshot.metrics,
    logs: snapshot.logs,
    events: snapshot.events,
  }
}

function mergeEdge(baseEdge: SystemEdge, snapshot: DashboardSnapshot['edges'][number] | undefined): SystemEdge {
  if (!snapshot) {
    return {
      ...baseEdge,
      status: 'idle',
      throughput: undefined,
      lastEventAt: undefined,
    }
  }
  return {
    ...baseEdge,
    status: snapshot.status,
    throughput: snapshot.throughput,
    lastEventAt: snapshot.lastEventAt,
  }
}

function attachLivePullState(dag: SystemDag): SystemDag {
  const consumerTargets = new Set(
    dag.edges
      .filter(edge => edge.source === LIVE_EDGE_SOURCE)
      .map(edge => edge.target),
  )

  const activeConsumerTargets = new Set(
    dag.edges
      .filter(edge => edge.source === LIVE_EDGE_SOURCE && edge.status !== 'idle')
      .map(edge => edge.target),
  )

  return {
    ...dag,
    nodes: dag.nodes.map(node => {
      let livePullState: LivePullState = 'none'
      let liveSourceState: LiveSourceState = 'none'

      if (consumerTargets.has(node.id)) {
        livePullState = activeConsumerTargets.has(node.id) ? 'active' : 'inactive'
      }

      const sourceTargets = new Set(
        dag.edges
          .filter(edge => edge.target === LIVE_EDGE_TARGET)
          .map(edge => edge.source),
      )

      const activeSourceTargets = new Set(
        dag.edges
          .filter(edge => edge.target === LIVE_EDGE_TARGET && edge.status !== 'idle')
          .map(edge => edge.source),
      )

      if (sourceTargets.has(node.id)) {
        liveSourceState = activeSourceTargets.has(node.id) ? 'active' : 'inactive'
      }

      return {
        ...node,
        livePullState,
        liveSourceState,
      }
    }),
  }
}

async function fetchSystemDag(): Promise<SystemDag> {
  try {
    const snapshot = await fetchDashboardSnapshot()
    const nodeSnapshots = new Map(snapshot.nodes.map(node => [node.id, node]))
    const edgeSnapshots = new Map(snapshot.edges.map(edge => [edge.id, edge]))

    return attachLivePullState({
      nodes: systemDag.nodes.map(node => mergeNode(node, nodeSnapshots.get(node.id))),
      edges: systemDag.edges.map(edge => mergeEdge(edge, edgeSnapshots.get(edge.id))),
    })
  } catch (error) {
    console.warn('Falling back to static dashboard data', error)
    return attachLivePullState({
      nodes: systemDag.nodes.map(node => mergeNode(node, undefined)),
      edges: systemDag.edges.map(edge => mergeEdge(edge, undefined)),
    })
  }
}

function systemDagQueryOptions() {
  return {
    queryKey: SYSTEM_DAG_QUERY_KEY,
    queryFn: fetchSystemDag,
    staleTime: DAG_STALE,
  } as const
}

async function getNodeFromCache(queryClient: ReturnType<typeof useQueryClient>, nodeId: string | null) {
  const dag = await queryClient.ensureQueryData(systemDagQueryOptions())
  return dag.nodes.find(node => node.id === nodeId) ?? null
}

export function useSystemDag() {
  return useQuery(systemDagQueryOptions())
}

export function useNodeDetails(nodeId: string | null) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: ['nodeDetails', nodeId],
    queryFn: () => getNodeFromCache(queryClient, nodeId),
    enabled: nodeId != null,
    staleTime: NODE_STALE,
  })
}

export function useNodeLogs(nodeId: string | null) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: ['nodeLogs', nodeId],
    queryFn: async () => (await getNodeFromCache(queryClient, nodeId))?.logs ?? [],
    enabled: nodeId != null,
    staleTime: NODE_STALE,
  })
}

export function useNodeMetrics(nodeId: string | null) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: ['nodeMetrics', nodeId],
    queryFn: async () => (await getNodeFromCache(queryClient, nodeId))?.metrics ?? [],
    enabled: nodeId != null,
    staleTime: NODE_STALE,
  })
}

export function useNodeEvents(nodeId: string | null) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: ['nodeEvents', nodeId],
    queryFn: async () => (await getNodeFromCache(queryClient, nodeId))?.events ?? [],
    enabled: nodeId != null,
    staleTime: NODE_STALE,
  })
}

export function useSystemHealth() {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: ['systemHealth'],
    queryFn: async () => {
      const dag = await queryClient.ensureQueryData(systemDagQueryOptions())
      const nodes = dag.nodes
      const hasError   = nodes.some(n => n.status === 'error')
      const hasWarning = nodes.some(n => n.status === 'warning')
      const status = hasError ? 'error' : hasWarning ? 'warning' : 'healthy'
      const avgHealth  = Math.round(nodes.reduce((s, n) => s + n.healthScore, 0) / nodes.length)
      return { status, avgHealth }
    },
    staleTime: DAG_STALE,
  })
}

export function useObservabilityStream(): DashboardStreamState {
  const queryClient = useQueryClient()
  const [streamState, setStreamState] = useState<DashboardStreamState>({
    connected: false,
    lastEventAt: null,
  })

  useEffect(() => {
    const source = new EventSource(buildApiUrl('/api/events/stream'))

    source.onopen = () => {
      setStreamState(current => ({ ...current, connected: true }))
    }

    source.addEventListener('dashboard-update', () => {
      const now = new Date().toISOString()
      setStreamState({ connected: true, lastEventAt: now })
      void queryClient.invalidateQueries({ queryKey: SYSTEM_DAG_QUERY_KEY })
      void queryClient.invalidateQueries({ queryKey: ['systemHealth'] })
    })

    source.onerror = () => {
      setStreamState(current => ({ ...current, connected: false }))
    }

    return () => {
      source.close()
      setStreamState(current => ({ ...current, connected: false }))
    }
  }, [queryClient])

  return streamState
}
