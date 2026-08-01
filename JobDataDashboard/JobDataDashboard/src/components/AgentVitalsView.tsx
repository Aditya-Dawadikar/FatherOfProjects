import { FiExternalLink, FiRefreshCw, FiZap } from 'react-icons/fi'
import { useEvals, useTriggerEvalSweep } from '../hooks'
import type { EvalRun, EvalRunStatus } from '../types'

const STATUS_LABEL: Record<EvalRunStatus, string> = {
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
}

const RESULT_METRICS: Array<{ key: keyof NonNullable<EvalRun['result']>; label: string; formatter?: (value: number) => string }> = [
  { key: 'accuracy', label: 'Accuracy', formatter: formatPercent },
  { key: 'precision', label: 'Precision', formatter: formatPercent },
  { key: 'recall', label: 'Recall', formatter: formatPercent },
  { key: 'f1', label: 'F1' },
  { key: 'score_in_range_rate', label: 'Score In-Range Rate', formatter: formatPercent },
  { key: 'mean_predicted_score', label: 'Mean Predicted Score' },
  { key: 'evaluated_cases', label: 'Evaluated Cases' },
  { key: 'errored_cases', label: 'Errored Cases' },
  { key: 'total_tokens', label: 'Total Tokens' },
  { key: 'mean_tokens_per_case', label: 'Mean Tokens / Case' },
]

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

function formatDateTime(value: string | null) {
  if (!value) {
    return '—'
  }
  return new Date(value).toLocaleString()
}

function formatDuration(startedAt: string | null, finishedAt: string | null) {
  if (!startedAt || !finishedAt) {
    return null
  }
  const ms = new Date(finishedAt).getTime() - new Date(startedAt).getTime()
  if (!Number.isFinite(ms) || ms < 0) {
    return null
  }
  const totalSeconds = Math.round(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`
}

function EvalRunRow({ run }: { run: EvalRun }) {
  const duration = formatDuration(run.started_at, run.finished_at)

  return (
    <details className="eval-run-item">
      <summary className="eval-run-summary">
        <span className={`status-pill status-pill-${run.status}`}>{STATUS_LABEL[run.status]}</span>
        <span className="eval-run-name">{run.run_name ?? run.eval_id}</span>
        <span className="eval-run-meta">prompt v{run.prompt_version ?? '—'}</span>
        <span className="eval-run-meta">{formatDateTime(run.started_at)}</span>
        {duration && <span className="eval-run-meta">{duration}</span>}
      </summary>

      <div className="eval-run-body">
        <div className="eval-run-fields">
          <div>
            <span>Dataset</span>
            <strong>{run.dataset_path ?? '—'}</strong>
          </div>
          <div>
            <span>Prompt source</span>
            <strong>{run.prompt_source ?? '—'}</strong>
          </div>
          <div>
            <span>LLM model</span>
            <strong>{run.llm_model ?? '—'}</strong>
          </div>
          <div>
            <span>Match threshold</span>
            <strong>{run.match_threshold ?? '—'}</strong>
          </div>
          <div>
            <span>Dataset cases</span>
            <strong>{run.dataset_case_count ?? '—'}</strong>
          </div>
          <div>
            <span>Limit</span>
            <strong>{run.limit ?? 'full dataset'}</strong>
          </div>
          <div>
            <span>Experiment</span>
            <strong>{run.experiment_name ?? '—'}</strong>
          </div>
          <div>
            <span>Run ID</span>
            <strong className="eval-run-id">{run.run_id}</strong>
          </div>
          <div>
            <span>MLflow</span>
            {run.mlflow_url ? (
              <a
                className="mlflow-link"
                href={run.mlflow_url}
                target="_blank"
                rel="noreferrer"
                onClick={(event) => event.stopPropagation()}
              >
                <FiExternalLink aria-hidden="true" className="button-icon" />
                View run
              </a>
            ) : (
              <strong>not configured</strong>
            )}
          </div>
        </div>

        {run.status === 'failed' && run.error && (
          <div className="banner banner-error">{run.error}</div>
        )}

        {run.status === 'running' && (
          <div className="banner banner-info">Run in progress — this list refreshes automatically.</div>
        )}

        {run.result && (
          <div className="summary-grid eval-run-result-grid">
            {RESULT_METRICS.filter((metric) => run.result?.[metric.key] !== undefined).map((metric) => {
              const rawValue = run.result?.[metric.key] as number
              return (
                <article className="summary-card" key={metric.key}>
                  <span>{metric.label}</span>
                  <strong>{metric.formatter ? metric.formatter(rawValue) : rawValue}</strong>
                </article>
              )
            })}
          </div>
        )}
      </div>
    </details>
  )
}

export default function AgentVitalsView() {
  const evalsQuery = useEvals()
  const sweepMutation = useTriggerEvalSweep()
  const runs = evalsQuery.data ?? []

  function runSweep() {
    sweepMutation.mutate(undefined, {
      onSuccess: () => {
        evalsQuery.refetch()
      },
    })
  }

  return (
    <section className="content-panel">
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">JobManagerAgent</p>
          <h2>{evalsQuery.isLoading ? 'Loading eval runs...' : `${runs.length} eval run${runs.length === 1 ? '' : 's'}`}</h2>
        </div>
        <div className="toolbar-actions">
          <button
            type="button"
            className="primary-button ghost-button-with-icon"
            onClick={runSweep}
            disabled={sweepMutation.isPending}
          >
            <FiZap aria-hidden="true" className="button-icon" />
            {sweepMutation.isPending ? 'Triggering sweep...' : 'Run Offline Eval Sweep'}
          </button>
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={() => evalsQuery.refetch()}
            disabled={evalsQuery.isFetching}
          >
            <FiRefreshCw
              aria-hidden="true"
              className={evalsQuery.isFetching ? 'button-icon spin' : 'button-icon'}
            />
            {evalsQuery.isFetching ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {sweepMutation.isSuccess && (
        <div className="banner banner-info">
          Triggered {sweepMutation.data.length} eval run{sweepMutation.data.length === 1 ? '' : 's'} — one per registered prompt version.
        </div>
      )}
      {sweepMutation.error && <div className="banner banner-error">{sweepMutation.error.message}</div>}
      {evalsQuery.error && <div className="banner banner-error">{evalsQuery.error.message}</div>}

      {!evalsQuery.isLoading && runs.length === 0 && (
        <div className="empty-state">
          <h2>No eval runs yet</h2>
          <p>Trigger an offline eval sweep to score every registered prompt version against the golden dataset.</p>
        </div>
      )}

      {runs.length > 0 && (
        <div className="eval-run-list">
          {runs.map((run) => (
            <EvalRunRow key={run.eval_id} run={run} />
          ))}
        </div>
      )}
    </section>
  )
}
