import { FiRefreshCw } from 'react-icons/fi'
import { usePrompts } from '../../hooks'
import type { RegisteredPrompt } from '../../types'

function formatTimestamp(value: number | null) {
  if (value === null) return '—'
  return new Date(value).toLocaleString()
}

const SCHEMA_MODE_HINT: Record<string, string> = {
  legacy: 'legacy (v1-v3) -- model decides match_score directly',
  single: 'single -- rubric-scored, one job per call',
  batch: 'batch -- rubric-scored, N jobs per call, backfill-only',
}

// A version is eligible for a new POST /evals/sweep run only when it's status="live" (see
// prompts/version_status.json) AND schema_mode="single" -- schema_mode="batch" scores multiple
// jobs per call and isn't compatible with the sweep's one-run-per-version loop, so a live batch
// version (e.g. v5) still won't be swept. Mirrors integrations/mlflow/prompt_registry.py's
// list_sweep_eligible_versions() -- purely descriptive here, the backend is what actually
// enforces this on POST /evals/sweep.
function isSweepEligible(prompt: RegisteredPrompt) {
  return prompt.status === 'live' && prompt.schema_mode === 'single'
}

export default function PromptVersionsTab() {
  const promptsQuery = usePrompts()
  const prompts = promptsQuery.data ?? []
  const sorted = [...prompts].sort((a, b) => Number(b.version) - Number(a.version))
  const eligibleCount = prompts.filter(isSweepEligible).length

  return (
    <>
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Reference</p>
          <h2>Prompt versions</h2>
        </div>
        <div className="toolbar-actions">
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={() => promptsQuery.refetch()}
            disabled={promptsQuery.isFetching}
          >
            <FiRefreshCw aria-hidden="true" className={promptsQuery.isFetching ? 'button-icon spin' : 'button-icon'} />
            Refresh
          </button>
        </div>
      </div>

      {promptsQuery.error && <div className="banner banner-error">{promptsQuery.error.message}</div>}
      <p className="match-detail-hint">
        Every prompt version ever registered in MLflow, live or decommissioned (nothing is ever
        deleted). Status comes from prompts/version_status.json. Only "live" versions with
        schema_mode="single" are eligible for new sweep studies ({eligibleCount} eligible right
        now) — decommissioned and batch-mode versions still show up here and in past eval runs,
        they just won't be included in a new sweep.
      </p>

      <div className="eval-run-list">
        {sorted.map((prompt) => (
          <details key={prompt.version} className="eval-run-item">
            <summary className="eval-run-summary">
              <span className={`status-pill ${prompt.status === 'live' ? 'status-pill-completed' : 'status-pill-failed'}`}>
                {prompt.status === 'live' ? 'Live' : 'Decommissioned'}
              </span>
              <span className="eval-run-name">v{prompt.version}</span>
              <span className="eval-run-meta" title={SCHEMA_MODE_HINT[prompt.schema_mode]}>
                {prompt.schema_mode}
              </span>
              {prompt.is_active && <span className="status-pill status-pill-running">Active</span>}
              {isSweepEligible(prompt) && <span className="status-pill status-pill-sweep">Sweep-eligible</span>}
              <span className="eval-run-meta">registered {formatTimestamp(prompt.creation_timestamp)}</span>
            </summary>

            <div className="eval-run-body">
              <div className="eval-run-fields">
                <div>
                  <span>Status</span>
                  <strong>{prompt.status}</strong>
                </div>
                <div>
                  <span>Schema mode</span>
                  <strong title={SCHEMA_MODE_HINT[prompt.schema_mode]}>{prompt.schema_mode}</strong>
                </div>
                <div>
                  <span>Rubric version</span>
                  <strong>{prompt.rubric_version}</strong>
                </div>
                <div>
                  <span>Sweep eligible</span>
                  <strong>{isSweepEligible(prompt) ? 'Yes' : 'No'}</strong>
                </div>
                <div>
                  <span>Currently active (production)</span>
                  <strong>{prompt.is_active ? 'Yes' : 'No'}</strong>
                </div>
                <div>
                  <span>Registered</span>
                  <strong>{formatTimestamp(prompt.creation_timestamp)}</strong>
                </div>
              </div>
              <pre className="prompt-text-block">{prompt.template}</pre>
            </div>
          </details>
        ))}
      </div>

      {!promptsQuery.isLoading && sorted.length === 0 && (
        <div className="empty-state">
          <p>No prompt versions registered yet.</p>
        </div>
      )}
    </>
  )
}
