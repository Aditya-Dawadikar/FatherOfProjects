import { useQuery } from '@tanstack/react-query'
import { systemDag } from '../data/dag'

const DAG_STALE = 30_000
const NODE_STALE = 10_000

export function useSystemDag() {
  return useQuery({
    queryKey: ['systemDag'],
    queryFn: () => Promise.resolve(systemDag),
    staleTime: DAG_STALE,
  })
}

export function useNodeDetails(nodeId: string | null) {
  return useQuery({
    queryKey: ['nodeDetails', nodeId],
    queryFn: () => {
      const node = systemDag.nodes.find(n => n.id === nodeId) ?? null
      return Promise.resolve(node)
    },
    enabled: nodeId != null,
    staleTime: NODE_STALE,
  })
}

export function useNodeLogs(nodeId: string | null) {
  return useQuery({
    queryKey: ['nodeLogs', nodeId],
    queryFn: () => {
      const node = systemDag.nodes.find(n => n.id === nodeId)
      return Promise.resolve(node?.logs ?? [])
    },
    enabled: nodeId != null,
    staleTime: NODE_STALE,
  })
}

export function useNodeMetrics(nodeId: string | null) {
  return useQuery({
    queryKey: ['nodeMetrics', nodeId],
    queryFn: () => {
      const node = systemDag.nodes.find(n => n.id === nodeId)
      return Promise.resolve(node?.metrics ?? [])
    },
    enabled: nodeId != null,
    staleTime: NODE_STALE,
  })
}

export function useNodeEvents(nodeId: string | null) {
  return useQuery({
    queryKey: ['nodeEvents', nodeId],
    queryFn: () => {
      const node = systemDag.nodes.find(n => n.id === nodeId)
      return Promise.resolve(node?.events ?? [])
    },
    enabled: nodeId != null,
    staleTime: NODE_STALE,
  })
}

export function useSystemHealth() {
  return useQuery({
    queryKey: ['systemHealth'],
    queryFn: () => {
      const nodes = systemDag.nodes
      const hasError   = nodes.some(n => n.status === 'error')
      const hasWarning = nodes.some(n => n.status === 'warning')
      const status = hasError ? 'error' : hasWarning ? 'warning' : 'healthy'
      const avgHealth  = Math.round(nodes.reduce((s, n) => s + n.healthScore, 0) / nodes.length)
      return Promise.resolve({ status, avgHealth })
    },
    staleTime: DAG_STALE,
  })
}
