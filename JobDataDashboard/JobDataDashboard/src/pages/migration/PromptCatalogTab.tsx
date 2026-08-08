import { FiRefreshCw } from 'react-icons/fi'
import { usePromptVersions, usePrompts } from '../../hooks'

function formatDateTime(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

function formatTimestamp(value: number | null) {
  if (value === null) return '—'
  return new Date(value).toLocaleString()
}

const SCHEMA_MODE_HINT: Record<string, string> = {
  legacy: 'legacy (v1-v3) -- model decides match_score directly',
  single: 'single -- rubric-scored, one job per call',
  batch: 'batch -- rubric-scored, N jobs per call, backfill-only',
}

// --- Prompt catalog -- every registered version, joined with how much it's actually been used ---
// Union of MLflow's registry (usePrompts -- what's registerable/settable, schema shape, rubric
// version, when it was registered) with job_matches' own usage (usePromptVersions -- how many
// jobs it actually scored and when it last ran) -- the same union MatchesView's filter dropdown
// builds, here surfaced as a full table instead of a dropdown so a cutover decision doesn't have
// to guess at a version's track record from memory.

export default function PromptCatalogTab() {
  const registeredPromptsQuery = usePrompts()
  const promptVersionsQuery = usePromptVersions()
  const registeredPrompts = registeredPromptsQuery.data ?? []
  const scoredVersions = promptVersionsQuery.data ?? []

  const scoredByVersion = new Map(scoredVersions.map((version) => [version.prompt_version, version]))
  const registeredByVersion = new Map(registeredPrompts.map((prompt) => [prompt.version, prompt]))
  const allVersionIds = new Set([...registeredByVersion.keys(), ...scoredByVersion.keys()])

  const rows = Array.from(allVersionIds)
    .sort((a, b) => Number(b) - Number(a))
    .map((version) => ({
      version,
      registered: registeredByVersion.get(version) ?? null,
      scored: scoredByVersion.get(version) ?? null,
    }))

  const isLoading = registeredPromptsQuery.isLoading || promptVersionsQuery.isLoading

  return (
    <section className="migration-section">
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Reference</p>
          <h2>Prompt catalog</h2>
        </div>
        <div className="toolbar-actions">
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={() => {
              registeredPromptsQuery.refetch()
              promptVersionsQuery.refetch()
            }}
            disabled={registeredPromptsQuery.isFetching || promptVersionsQuery.isFetching}
          >
            <FiRefreshCw
              aria-hidden="true"
              className={registeredPromptsQuery.isFetching || promptVersionsQuery.isFetching ? 'button-icon spin' : 'button-icon'}
            />
            Refresh
          </button>
        </div>
      </div>

      {registeredPromptsQuery.error && <div className="banner banner-error">{registeredPromptsQuery.error.message}</div>}
      {promptVersionsQuery.error && <div className="banner banner-error">{promptVersionsQuery.error.message}</div>}
      <p className="match-detail-hint">
        Every version ever registered in MLflow, joined with how much it's actually scored (job_matches). A
        version can be registered with zero matches scored yet (never used in a live/backfill cycle), or have
        matches scored but no longer be registered here if it predates registration tracking.
      </p>

      <div className="table-wrap">
        <table className="jobs-table">
          <thead>
            <tr>
              <th>Version</th>
              <th>Status</th>
              <th>Schema mode</th>
              <th>Rubric version</th>
              <th>Registered</th>
              <th>Matches scored</th>
              <th>Model (last used)</th>
              <th>Last scored</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ version, registered, scored }) => (
              <tr key={version}>
                <td>v{version}</td>
                <td>
                  {registered?.is_active ? (
                    <span className="status-pill status-pill-completed">Active</span>
                  ) : registered ? (
                    <span className="status-pill status-pill-running">Registered</span>
                  ) : (
                    <span className="status-pill status-pill-failed">Unregistered</span>
                  )}
                </td>
                <td title={registered ? SCHEMA_MODE_HINT[registered.schema_mode] : undefined}>
                  {registered?.schema_mode ?? '—'}
                </td>
                <td>{registered?.rubric_version ?? '—'}</td>
                <td>{registered ? formatTimestamp(registered.creation_timestamp) : '—'}</td>
                <td>{scored?.row_count ?? 0}</td>
                <td>{scored?.model_name ?? '—'}</td>
                <td>{scored ? formatDateTime(scored.latest_evaluated_at) : 'never'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!isLoading && rows.length === 0 && (
          <div className="empty-state">
            <p>No prompt versions registered or scored yet.</p>
          </div>
        )}
      </div>
    </section>
  )
}
