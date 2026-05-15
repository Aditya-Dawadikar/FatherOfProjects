import { useSystemHealth } from '../hooks'

const STATUS_LABEL: Record<string, string> = {
  healthy: 'Healthy',
  warning: 'Degraded',
  error:   'Down',
}

export default function Header() {
  const { data: health } = useSystemHealth()
  const status = health?.status ?? 'healthy'

  return (
    <header className="dash-header">
      <div className="header-left">
        <span className="header-icon">◈</span>
        <h1 className="header-title">Observability Dashboard</h1>
        <span className="env-badge">Production</span>
      </div>
      <div className="header-right">
        <span className="last-updated">
          Updated {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </span>
        <span className={`status-pill status-pill-${status}`}>
          <span className={`status-pip ${status === 'healthy' ? 'pip-pulse' : ''}`} />
          {STATUS_LABEL[status]}
        </span>
      </div>
    </header>
  )
}
