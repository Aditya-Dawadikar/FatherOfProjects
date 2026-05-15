import { useNodeDetails, useNodeLogs, useNodeMetrics, useNodeEvents } from '../hooks'
import { systemDag } from '../data/dag'
import type { NodeStatus, LogLevel } from '../types'

const STATUS_LABEL: Record<NodeStatus, string> = {
  healthy: 'Healthy',
  warning: 'Warning',
  error:   'Error',
  idle:    'Idle',
}

const LOG_ICON: Record<LogLevel, string> = {
  info:    'ℹ',
  warning: '▲',
  error:   '✕',
}

function HealthBar({ score }: { score: number }) {
  const color = score >= 90 ? 'var(--accent)' : score >= 70 ? 'var(--warn)' : 'var(--error)'
  return (
    <div className="health-bar-wrap">
      <div className="health-bar-track">
        <div className="health-bar-fill" style={{ width: `${score}%`, background: color }} />
      </div>
      <span className="health-bar-label" style={{ color }}>{score}</span>
    </div>
  )
}

interface InspectorProps {
  nodeId: string | null
  onSelectNode: (id: string) => void
}

export default function Inspector({ nodeId, onSelectNode }: InspectorProps) {
  const { data: node }    = useNodeDetails(nodeId)
  const { data: logs }    = useNodeLogs(nodeId)
  const { data: metrics } = useNodeMetrics(nodeId)
  const { data: events }  = useNodeEvents(nodeId)

  if (!nodeId || !node) {
    return (
      <aside className="inspector inspector-empty">
        <p className="inspector-placeholder">Select a node to inspect its health, logs, and metrics.</p>
      </aside>
    )
  }

  const upstreamNodes   = node.upstream.map(r => systemDag.nodes.find(n => n.id === r.targetNodeId)).filter(Boolean)
  const downstreamNodes = node.downstream.map(r => systemDag.nodes.find(n => n.id === r.targetNodeId)).filter(Boolean)

  return (
    <aside className="inspector">
      {/* ── Node Summary ── */}
      <div className="inspector-section inspector-header-section">
        <div className="inspector-node-title">
          <h2 className="inspector-node-name">{node.name}</h2>
          <span className={`insp-badge insp-badge-${node.status}`}>{STATUS_LABEL[node.status]}</span>
        </div>
        <p className="inspector-desc">{node.shortDescription}</p>
        <div className="inspector-meta-row">
          <span className="meta-item">
            <span className="meta-key">Last seen</span>
            <span className="meta-val">{node.lastSeenAt}</span>
          </span>
          <span className="meta-item">
            <span className="meta-key">Category</span>
            <span className="meta-val">{node.category}</span>
          </span>
        </div>
        <div className="health-score-row">
          <span className="meta-key">Health score</span>
          <HealthBar score={node.healthScore} />
        </div>
      </div>

      {/* ── Key Metrics ── */}
      {metrics && metrics.length > 0 && (
        <div className="inspector-section">
          <h3 className="section-title">Key Metrics</h3>
          <div className="metrics-grid">
            {metrics.map(m => (
              <div key={m.label} className="insp-metric">
                <span className="insp-metric-label">{m.label}</span>
                <span className={`insp-metric-value ${m.trend === 'up' ? 'trend-up' : m.trend === 'down' ? 'trend-down' : ''}`}>
                  {m.trend === 'up' ? '↑ ' : m.trend === 'down' ? '↓ ' : ''}{m.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Recent Logs ── */}
      {logs && logs.length > 0 && (
        <div className="inspector-section">
          <h3 className="section-title">Recent Logs</h3>
          <ul className="log-list">
            {logs.map(l => (
              <li key={l.id} className={`log-entry log-${l.level}`}>
                <span className="log-icon">{LOG_ICON[l.level]}</span>
                <span className="log-time">{l.timestamp}</span>
                <span className="log-msg">{l.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Recent Events ── */}
      {events && events.length > 0 && (
        <div className="inspector-section">
          <h3 className="section-title">Recent Events</h3>
          <ul className="event-list">
            {events.map(e => (
              <li key={e.id} className="event-entry">
                <span className="event-time">{e.timestamp}</span>
                <div className="event-body">
                  <span className="event-label">{e.label}</span>
                  {e.detail && <span className="event-detail">{e.detail}</span>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Related Links ── */}
      {(upstreamNodes.length > 0 || downstreamNodes.length > 0) && (
        <div className="inspector-section">
          <h3 className="section-title">Related Nodes</h3>
          {upstreamNodes.length > 0 && (
            <div className="related-group">
              <span className="related-dir">Upstream</span>
              <div className="related-nodes">
                {upstreamNodes.map(n => n && (
                  <button key={n.id} className={`related-node-btn node-btn-${n.status}`} onClick={() => onSelectNode(n.id)}>
                    <span className="related-dot" style={{ background: n.status === 'healthy' ? 'var(--accent)' : n.status === 'warning' ? 'var(--warn)' : n.status === 'error' ? 'var(--error)' : 'var(--muted)' }} />
                    {n.name}
                  </button>
                ))}
              </div>
            </div>
          )}
          {downstreamNodes.length > 0 && (
            <div className="related-group">
              <span className="related-dir">Downstream</span>
              <div className="related-nodes">
                {downstreamNodes.map(n => n && (
                  <button key={n.id} className={`related-node-btn node-btn-${n.status}`} onClick={() => onSelectNode(n.id)}>
                    <span className="related-dot" style={{ background: n.status === 'healthy' ? 'var(--accent)' : n.status === 'warning' ? 'var(--warn)' : n.status === 'error' ? 'var(--error)' : 'var(--muted)' }} />
                    {n.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </aside>
  )
}
