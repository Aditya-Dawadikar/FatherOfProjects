import { FiExternalLink } from 'react-icons/fi'
import type { EvalRun, GuardrailsEvalRun, ToolEvalRun } from '../../types'
import {
  GUARDRAILS_RESULT_METRICS,
  RESULT_METRICS,
  STATUS_LABEL,
  SWEEP_COMPARE_COLUMNS,
  TOOL_RESULT_METRICS,
  formatDateTime,
  formatDuration,
  formatGuardrailsMetric,
  formatMetric,
  formatToolMetric,
  latestGuardrailsRun,
  latestSweepGroup,
  latestToolRun,
} from './vitalsUtils'

export function MlflowLink({ href, label, onClick }: { href: string | null; label: string; onClick?: () => void }) {
  if (!href) {
    return <strong>{label === 'View trace' ? 'not available' : 'not configured'}</strong>
  }
  return (
    <a
      className="mlflow-link"
      href={href}
      target="_blank"
      rel="noreferrer"
      onClick={(event) => {
        event.stopPropagation()
        onClick?.()
      }}
    >
      <FiExternalLink aria-hidden="true" className="button-icon" />
      {label}
    </a>
  )
}

export function KpiCard({ label, value }: { label: string; value: string | number }) {
  return (
    <article className="summary-card">
      <span>{label}</span>
      <strong>{typeof value === 'number' ? value.toFixed(2) : value}</strong>
    </article>
  )
}

export function EvalRunRow({ run }: { run: EvalRun }) {
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
            <span>MLflow Run</span>
            <MlflowLink href={run.mlflow_url} label="View run" />
          </div>
          <div>
            <span>MLflow Trace</span>
            <MlflowLink href={run.mlflow_trace_url} label="View trace" />
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

export function ToolEvalRunRow({ run }: { run: ToolEvalRun }) {
  const duration = formatDuration(run.started_at, run.finished_at)

  return (
    <details className="eval-run-item">
      <summary className="eval-run-summary">
        <span className={`status-pill status-pill-${run.status}`}>{STATUS_LABEL[run.status]}</span>
        <span className="eval-run-name">{run.run_name ?? run.eval_id}</span>
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
            <span>LLM model</span>
            <strong>{run.llm_model ?? '—'}</strong>
          </div>
          <div>
            <span>Dataset cases</span>
            <strong>{run.dataset_case_count ?? '—'}</strong>
          </div>
          <div>
            <span>Repeats / case</span>
            <strong>{run.repeats ?? '—'}</strong>
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
            <span>MLflow Run</span>
            <MlflowLink href={run.mlflow_url} label="View run" />
          </div>
          <div>
            <span>MLflow Trace</span>
            <MlflowLink href={run.mlflow_trace_url} label="View trace" />
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
            {TOOL_RESULT_METRICS.filter((metric) => run.result?.[metric.key] !== undefined).map((metric) => {
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

export function GuardrailsEvalRunRow({ run }: { run: GuardrailsEvalRun }) {
  const duration = formatDuration(run.started_at, run.finished_at)

  return (
    <details className="eval-run-item">
      <summary className="eval-run-summary">
        <span className={`status-pill status-pill-${run.status}`}>{STATUS_LABEL[run.status]}</span>
        <span className="eval-run-name">{run.run_name ?? run.eval_id}</span>
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
            <span>MLflow Run</span>
            <MlflowLink href={run.mlflow_url} label="View run" />
          </div>
          <div>
            <span>MLflow Trace</span>
            <MlflowLink href={run.mlflow_trace_url} label="View trace" />
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
            {GUARDRAILS_RESULT_METRICS.filter((metric) => run.result?.[metric.key] !== undefined).map((metric) => {
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

export function SweepGroupRow({ sweepId, runs }: { sweepId: string; runs: EvalRun[] }) {
  const latestStartedAt = runs.reduce<string | null>((latest, run) => {
    if (!run.started_at) return latest
    return !latest || run.started_at > latest ? run.started_at : latest
  }, null)
  const runningCount = runs.filter((run) => run.status === 'running').length

  return (
    <details className="eval-run-item sweep-group">
      <summary className="eval-run-summary">
        <span className="status-pill status-pill-sweep">Sweep</span>
        <span className="eval-run-name">{runs.length} prompt versions compared</span>
        <span className="eval-run-meta">sweep {sweepId}</span>
        <span className="eval-run-meta">{formatDateTime(latestStartedAt)}</span>
        {runningCount > 0 && <span className="eval-run-meta">{runningCount} still running</span>}
      </summary>

      <div className="eval-run-body">
        <div className="table-wrap">
          <table className="sweep-compare-table">
            <thead>
              <tr>
                <th>Prompt Version</th>
                <th>Status</th>
                {SWEEP_COMPARE_COLUMNS.map((column) => (
                  <th key={column.key}>{column.label}</th>
                ))}
                <th>Duration</th>
                <th>MLflow</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.eval_id}>
                  <td>v{run.prompt_version ?? '—'}</td>
                  <td>
                    <span className={`status-pill status-pill-${run.status}`}>{STATUS_LABEL[run.status]}</span>
                  </td>
                  {SWEEP_COMPARE_COLUMNS.map((column) => (
                    <td key={column.key}>{formatMetric(run, column.key)}</td>
                  ))}
                  <td>{formatDuration(run.started_at, run.finished_at) ?? '—'}</td>
                  <td className="sweep-compare-links">
                    <MlflowLink href={run.mlflow_url} label="Run" />
                    <MlflowLink href={run.mlflow_trace_url} label="View trace" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {runs.some((run) => run.status === 'failed' && run.error) && (
          <div className="banner banner-error">
            {runs
              .filter((run) => run.status === 'failed' && run.error)
              .map((run) => `v${run.prompt_version ?? '—'}: ${run.error}`)
              .join(' · ')}
          </div>
        )}
      </div>
    </details>
  )
}

export function PromptComparisonTable({ runs }: { runs: EvalRun[] }) {
  const latest = latestSweepGroup(runs)

  if (!latest) {
    return (
      <div className="empty-state">
        <p>Trigger an offline eval sweep to compare every registered prompt version's full metrics here.</p>
      </div>
    )
  }

  const versions = [...latest.runs].sort((a, b) =>
    (a.prompt_version ?? '').localeCompare(b.prompt_version ?? '', undefined, { numeric: true }),
  )
  const runningCount = versions.filter((run) => run.status === 'running').length

  return (
    <>
      <div className="pane-meta">
        <span className="eval-run-meta">sweep {latest.sweepId}</span>
        <span className="eval-run-meta">{formatDateTime(latest.latestStartedAt)}</span>
        {runningCount > 0 && <span className="eval-run-meta">{runningCount} still running</span>}
      </div>
      <div className="table-wrap">
        <table className="sweep-compare-table">
          <thead>
            <tr>
              <th>Prompt Version</th>
              <th>Status</th>
              {RESULT_METRICS.map((metric) => (
                <th key={metric.key}>{metric.label}</th>
              ))}
              <th>Duration</th>
              <th>MLflow</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((run) => (
              <tr key={run.eval_id}>
                <td>v{run.prompt_version ?? '—'}</td>
                <td>
                  <span className={`status-pill status-pill-${run.status}`}>{STATUS_LABEL[run.status]}</span>
                </td>
                {RESULT_METRICS.map((metric) => (
                  <td key={metric.key}>{formatMetric(run, metric.key)}</td>
                ))}
                <td>{formatDuration(run.started_at, run.finished_at) ?? '—'}</td>
                <td className="sweep-compare-links">
                  <MlflowLink href={run.mlflow_url} label="Run" />
                  <MlflowLink href={run.mlflow_trace_url} label="Trace" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {versions.some((run) => run.status === 'failed' && run.error) && (
        <div className="banner banner-error">
          {versions
            .filter((run) => run.status === 'failed' && run.error)
            .map((run) => `v${run.prompt_version ?? '—'}: ${run.error}`)
            .join(' · ')}
        </div>
      )}
    </>
  )
}

export function AgentBehaviorTable({ toolRuns }: { toolRuns: ToolEvalRun[] }) {
  const latest = latestToolRun(toolRuns)

  if (!latest) {
    return (
      <div className="empty-state">
        <p>Trigger a tool-selection eval run to see the agent's tool-calling behavior metrics here.</p>
      </div>
    )
  }

  return (
    <>
      <div className="pane-meta">
        <span className="eval-run-meta">{latest.run_name ?? latest.eval_id}</span>
        <span className="eval-run-meta">{formatDateTime(latest.started_at)}</span>
      </div>
      <div className="table-wrap">
        <table className="sweep-compare-table">
          <thead>
            <tr>
              <th>Run</th>
              <th>Status</th>
              {TOOL_RESULT_METRICS.map((metric) => (
                <th key={metric.key}>{metric.label}</th>
              ))}
              <th>Duration</th>
              <th>MLflow</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{latest.run_name ?? latest.eval_id}</td>
              <td>
                <span className={`status-pill status-pill-${latest.status}`}>{STATUS_LABEL[latest.status]}</span>
              </td>
              {TOOL_RESULT_METRICS.map((metric) => (
                <td key={metric.key}>{formatToolMetric(latest, metric.key)}</td>
              ))}
              <td>{formatDuration(latest.started_at, latest.finished_at) ?? '—'}</td>
              <td className="sweep-compare-links">
                <MlflowLink href={latest.mlflow_url} label="Run" />
                <MlflowLink href={latest.mlflow_trace_url} label="Trace" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      {latest.status === 'failed' && latest.error && <div className="banner banner-error">{latest.error}</div>}
    </>
  )
}

export function GuardrailsTable({ guardrailsRuns }: { guardrailsRuns: GuardrailsEvalRun[] }) {
  const latest = latestGuardrailsRun(guardrailsRuns)

  if (!latest) {
    return (
      <div className="empty-state">
        <p>Trigger a guardrails eval run to see the guardrail-check accuracy metrics here.</p>
      </div>
    )
  }

  return (
    <>
      <div className="pane-meta">
        <span className="eval-run-meta">{latest.run_name ?? latest.eval_id}</span>
        <span className="eval-run-meta">{formatDateTime(latest.started_at)}</span>
      </div>
      <div className="table-wrap">
        <table className="sweep-compare-table">
          <thead>
            <tr>
              <th>Run</th>
              <th>Status</th>
              {GUARDRAILS_RESULT_METRICS.map((metric) => (
                <th key={metric.key}>{metric.label}</th>
              ))}
              <th>Duration</th>
              <th>MLflow</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{latest.run_name ?? latest.eval_id}</td>
              <td>
                <span className={`status-pill status-pill-${latest.status}`}>{STATUS_LABEL[latest.status]}</span>
              </td>
              {GUARDRAILS_RESULT_METRICS.map((metric) => (
                <td key={metric.key}>{formatGuardrailsMetric(latest, metric.key)}</td>
              ))}
              <td>{formatDuration(latest.started_at, latest.finished_at) ?? '—'}</td>
              <td className="sweep-compare-links">
                <MlflowLink href={latest.mlflow_url} label="Run" />
                <MlflowLink href={latest.mlflow_trace_url} label="Trace" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      {latest.status === 'failed' && latest.error && <div className="banner banner-error">{latest.error}</div>}
    </>
  )
}
