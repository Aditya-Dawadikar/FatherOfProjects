import { FiRefreshCw } from 'react-icons/fi'
import { useFeatureFlags, useSetFeatureFlag } from '../../hooks'
import { formatDateTime } from './adminUtils'

// scrape_enabled/agent_live_enabled/agent_backfill_enabled today -- see JobManagerAgent/shared/
// feature_flags.py. This list has no fixed set of names on either side: a flag added there later
// (a migration seed row, or just its first POST) appears here automatically, no dashboard change
// needed. "Turn off" here is what actually produces zero API calls -- more direct than driving an
// RPM cap on the Rate Limits tab to 0, which its own validation doesn't even allow.

export default function FeatureFlagsTab() {
  const flagsQuery = useFeatureFlags()
  const setFlagMutation = useSetFeatureFlag()
  const flags = flagsQuery.data ?? []

  function toggleFlag(name: string, currentlyEnabled: boolean) {
    setFlagMutation.mutate({ name, enabled: !currentlyEnabled, reason: 'Toggled from dashboard' })
  }

  return (
    <section className="migration-section">
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Kill switches</p>
          <h2>Feature flags</h2>
        </div>
        <div className="toolbar-actions">
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={() => flagsQuery.refetch()}
            disabled={flagsQuery.isFetching}
          >
            <FiRefreshCw aria-hidden="true" className={flagsQuery.isFetching ? 'button-icon spin' : 'button-icon'} />
            Refresh
          </button>
        </div>
      </div>

      {flagsQuery.error && <div className="banner banner-error">{flagsQuery.error.message}</div>}
      {setFlagMutation.error && <div className="banner banner-error">{setFlagMutation.error.message}</div>}

      {flagsQuery.isLoading ? (
        <p className="match-detail-hint">Loading flags...</p>
      ) : flags.length === 0 ? (
        <p className="match-detail-hint">No flags registered yet.</p>
      ) : (
        <div className="summary-grid">
          {flags.map((flag) => (
            <article key={flag.name} className="summary-card">
              <span>{flag.name}</span>
              <strong>
                <span className={`match-badge ${flag.enabled ? 'match-badge-yes' : 'match-badge-no'}`}>
                  {flag.enabled ? 'ON' : 'OFF'}
                </span>
              </strong>
              {flag.description && <span className="match-detail-hint">{flag.description}</span>}
              <button
                type="button"
                className="ghost-button ghost-button-with-icon"
                disabled={setFlagMutation.isPending}
                onClick={() => toggleFlag(flag.name, flag.enabled)}
              >
                {flag.enabled ? 'Turn off' : 'Turn on'}
              </button>
              <span className="match-detail-hint">
                Updated {formatDateTime(flag.updated_at)}
                {flag.updated_reason ? ` -- ${flag.updated_reason}` : ''}
              </span>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
