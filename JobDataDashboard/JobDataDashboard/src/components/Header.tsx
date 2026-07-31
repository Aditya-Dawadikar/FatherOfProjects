import { useJobDataHealth } from '../hooks'

export default function Header() {
  const { data: health } = useJobDataHealth()
  const status = health?.status ?? 'checking'

  return (
    <header className="app-header">
      <div>
        <p className="eyebrow">JobDataServer</p>
        <h1>Scraped Records</h1>
      </div>
      <div className="header-meta">
        <div className="status-card">
          <span className={`status-dot status-${status === 'ok' ? 'ok' : 'pending'}`} />
          <span>{status === 'ok' ? 'API healthy' : 'Checking API'}</span>
        </div>
        <div className="status-card muted">Table: {health?.table ?? 'Loading...'}</div>
        <div className="status-card muted">Matches: {health?.match_table ?? 'Loading...'}</div>
      </div>
    </header>
  )
}