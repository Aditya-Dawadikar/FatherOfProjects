import { useState } from 'react'
import { FiExternalLink, FiRefreshCw, FiZap } from 'react-icons/fi'
import { useEvals, useTriggerEvalSweep, useToolEvals, useTriggerToolEval } from '../hooks'
import type { EvalRun, EvalRunStatus, ToolEvalRun } from '../types'

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

function formatUsd(value: number) {
  // Per-run/per-success costs are typically fractions of a cent -- fixed 2-decimal formatting
  // would round most of them to "$0.00" and hide exactly the signal this metric exists to show.
  const decimals = value !== 0 && Math.abs(value) < 0.01 ? 4 : 2
  return `$${value.toFixed(decimals)}`
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

function MlflowLink({ href, label, onClick }: { href: string | null; label: string; onClick?: () => void }) {
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

function formatMetric(run: EvalRun, key: keyof NonNullable<EvalRun['result']>) {
  const metric = RESULT_METRICS.find((entry) => entry.key === key)
  const rawValue = run.result?.[key]
  if (rawValue === undefined || metric === undefined) {
    return '—'
  }
  return metric.formatter ? metric.formatter(rawValue) : rawValue
}

function formatToolMetric(run: ToolEvalRun, key: keyof NonNullable<ToolEvalRun['result']>) {
  const metric = TOOL_RESULT_METRICS.find((entry) => entry.key === key)
  const rawValue = run.result?.[key]
  if (rawValue === undefined || metric === undefined) {
    return '—'
  }
  return metric.formatter ? metric.formatter(rawValue) : rawValue
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

const TOOL_RESULT_METRICS: Array<{
  key: keyof NonNullable<ToolEvalRun['result']>
  label: string
  formatter?: (value: number) => string
}> = [
  { key: 'tool_selection_accuracy', label: 'Tool Selection Accuracy', formatter: formatPercent },
  { key: 'tool_error_rate', label: 'Tool Error Rate', formatter: formatPercent },
  { key: 'call_volume_efficiency', label: 'Call Volume Efficiency', formatter: formatPercent },
  { key: 'plan_adherence', label: 'Plan Adherence', formatter: formatPercent },
  { key: 'consistency_score', label: 'Consistency Score', formatter: formatPercent },
  { key: 'success_rate', label: 'Success Rate', formatter: formatPercent },
  { key: 'cost_per_successful_run', label: 'Cost / Successful Run', formatter: formatUsd },
  { key: 'mean_cost_per_run', label: 'Mean Cost / Run', formatter: formatUsd },
  { key: 'evaluated_cases', label: 'Evaluated Cases' },
  { key: 'errored_cases', label: 'Errored Cases' },
  { key: 'incomplete_trials', label: 'Incomplete Trials' },
  { key: 'total_actual_calls', label: 'Total Tool Calls' },
  { key: 'total_guardrail_errors', label: 'Guardrail Violations' },
  { key: 'mean_calls_per_trial', label: 'Mean Calls / Trial' },
  { key: 'total_cost_usd', label: 'Total Cost', formatter: formatUsd },
]

function ToolEvalRunRow({ run }: { run: ToolEvalRun }) {
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

const SWEEP_COMPARE_COLUMNS: Array<{ key: keyof NonNullable<EvalRun['result']>; label: string }> = [
  { key: 'accuracy', label: 'Accuracy' },
  { key: 'precision', label: 'Precision' },
  { key: 'recall', label: 'Recall' },
  { key: 'f1', label: 'F1' },
  { key: 'total_tokens', label: 'Total Tokens' },
  { key: 'mean_tokens_per_case', label: 'Mean Tokens / Case' },
]

function SweepGroupRow({ sweepId, runs }: { sweepId: string; runs: EvalRun[] }) {
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

function latestSweepGroup(runs: EvalRun[]): { sweepId: string; runs: EvalRun[]; latestStartedAt: string } | null {
  const sweepGroups = new Map<string, EvalRun[]>()
  for (const run of runs) {
    if (!run.sweep_id) continue
    const group = sweepGroups.get(run.sweep_id)
    if (group) {
      group.push(run)
    } else {
      sweepGroups.set(run.sweep_id, [run])
    }
  }

  let latest: { sweepId: string; runs: EvalRun[]; latestStartedAt: string } | null = null
  for (const [sweepId, groupRuns] of sweepGroups) {
    const latestStartedAt = groupRuns.reduce(
      (acc, run) => (run.started_at && run.started_at > acc ? run.started_at : acc),
      '',
    )
    if (!latest || latestStartedAt > latest.latestStartedAt) {
      latest = { sweepId, runs: groupRuns, latestStartedAt }
    }
  }
  return latest
}

function latestToolRun(toolRuns: ToolEvalRun[]): ToolEvalRun | null {
  if (toolRuns.length === 0) return null
  return [...toolRuns].sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))[0]
}

function PromptComparisonTable({ runs }: { runs: EvalRun[] }) {
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

function AgentBehaviorTable({ toolRuns }: { toolRuns: ToolEvalRun[] }) {
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

type VitalsListItem =
  | { kind: 'single'; run: EvalRun; sortKey: string }
  | { kind: 'sweep'; sweepId: string; runs: EvalRun[]; sortKey: string }
  | { kind: 'tool'; run: ToolEvalRun; sortKey: string }

function groupRunsForDisplay(runs: EvalRun[], toolRuns: ToolEvalRun[]): VitalsListItem[] {
  const sweepGroups = new Map<string, EvalRun[]>()
  const items: VitalsListItem[] = []

  for (const run of runs) {
    if (!run.sweep_id) {
      items.push({ kind: 'single', run, sortKey: run.started_at ?? '' })
      continue
    }
    const group = sweepGroups.get(run.sweep_id)
    if (group) {
      group.push(run)
    } else {
      sweepGroups.set(run.sweep_id, [run])
    }
  }

  for (const [sweepId, groupRuns] of sweepGroups) {
    groupRuns.sort((a, b) => (a.prompt_version ?? '').localeCompare(b.prompt_version ?? '', undefined, { numeric: true }))
    const sortKey = groupRuns.reduce((latest, run) => (run.started_at && run.started_at > latest ? run.started_at : latest), '')
    items.push({ kind: 'sweep', sweepId, runs: groupRuns, sortKey })
  }

  for (const run of toolRuns) {
    items.push({ kind: 'tool', run, sortKey: run.started_at ?? '' })
  }

  items.sort((a, b) => (a.sortKey < b.sortKey ? 1 : a.sortKey > b.sortKey ? -1 : 0))
  return items
}

type VitalsTab = 'prompt' | 'behavior' | 'history'

// First N tabs are one per experiment type this dashboard tracks (currently prompt-version
// comparison and tool-selection/agent-behavior evals); the last tab is always run history,
// spanning every experiment type at once. Adding a new experiment type later means adding one
// more entry here before 'history', not restructuring the tab bar.
const VITALS_TABS: Array<{ id: VitalsTab; label: string }> = [
  { id: 'prompt', label: 'Prompt Version Comparison' },
  { id: 'behavior', label: 'Agent Behavior' },
  { id: 'history', label: 'Run History' },
]

export default function AgentVitalsView() {
  const [activeTab, setActiveTab] = useState<VitalsTab>('prompt')

  const evalsQuery = useEvals()
  const sweepMutation = useTriggerEvalSweep()
  const runs = evalsQuery.data ?? []

  const toolEvalsQuery = useToolEvals()
  const toolEvalMutation = useTriggerToolEval()
  const toolRuns = toolEvalsQuery.data ?? []

  const isLoading = evalsQuery.isLoading || toolEvalsQuery.isLoading
  const isFetching = evalsQuery.isFetching || toolEvalsQuery.isFetching
  const totalRunCount = runs.length + toolRuns.length

  function runSweep() {
    sweepMutation.mutate(undefined, {
      onSuccess: () => {
        evalsQuery.refetch()
      },
    })
  }

  function runToolEval() {
    toolEvalMutation.mutate(undefined, {
      onSuccess: () => {
        toolEvalsQuery.refetch()
      },
    })
  }

  return (
    <section className="content-panel">
      <div className="vitals-tabs-bar pane-tabs">
        {VITALS_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`pane-tab${activeTab === tab.id ? ' is-active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'prompt' && (
        <>
          <div className="toolbar">
            <div className="toolbar-copy">
              <p className="eyebrow">Current Agent State</p>
              <h2>Prompt version comparison</h2>
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
                <FiRefreshCw aria-hidden="true" className={evalsQuery.isFetching ? 'button-icon spin' : 'button-icon'} />
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

          <PromptComparisonTable runs={runs} />
        </>
      )}

      {activeTab === 'behavior' && (
        <>
          <div className="toolbar">
            <div className="toolbar-copy">
              <p className="eyebrow">Current Agent State</p>
              <h2>Agent behavior experiments</h2>
            </div>
            <div className="toolbar-actions">
              <button
                type="button"
                className="primary-button ghost-button-with-icon"
                onClick={runToolEval}
                disabled={toolEvalMutation.isPending}
              >
                <FiZap aria-hidden="true" className="button-icon" />
                {toolEvalMutation.isPending ? 'Triggering run...' : 'Run Tool Selection Eval'}
              </button>
              <button
                type="button"
                className="ghost-button ghost-button-with-icon"
                onClick={() => toolEvalsQuery.refetch()}
                disabled={toolEvalsQuery.isFetching}
              >
                <FiRefreshCw aria-hidden="true" className={toolEvalsQuery.isFetching ? 'button-icon spin' : 'button-icon'} />
                {toolEvalsQuery.isFetching ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
          </div>

          {toolEvalMutation.isSuccess && (
            <div className="banner banner-info">Triggered a tool-selection eval run against the mocked-tool golden dataset.</div>
          )}
          {toolEvalMutation.error && <div className="banner banner-error">{toolEvalMutation.error.message}</div>}
          {toolEvalsQuery.error && <div className="banner banner-error">{toolEvalsQuery.error.message}</div>}

          <AgentBehaviorTable toolRuns={toolRuns} />
        </>
      )}

      {activeTab === 'history' && (
        <>
          <div className="toolbar">
            <div className="toolbar-copy">
              <p className="eyebrow">JobManagerAgent</p>
              <h2>{isLoading ? 'Loading eval runs...' : `${totalRunCount} eval run${totalRunCount === 1 ? '' : 's'}`}</h2>
            </div>
            <div className="toolbar-actions">
              <button
                type="button"
                className="ghost-button ghost-button-with-icon"
                onClick={() => {
                  evalsQuery.refetch()
                  toolEvalsQuery.refetch()
                }}
                disabled={isFetching}
              >
                <FiRefreshCw aria-hidden="true" className={isFetching ? 'button-icon spin' : 'button-icon'} />
                {isFetching ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
          </div>

          {evalsQuery.error && <div className="banner banner-error">{evalsQuery.error.message}</div>}
          {toolEvalsQuery.error && <div className="banner banner-error">{toolEvalsQuery.error.message}</div>}

          {!isLoading && totalRunCount === 0 && (
            <div className="empty-state">
              <h2>No eval runs yet</h2>
              <p>Switch to Prompt Version Comparison or Agent Behavior to trigger a run.</p>
            </div>
          )}

          {totalRunCount > 0 && (
            <div className="eval-run-list">
              {groupRunsForDisplay(runs, toolRuns).map((item) => {
                if (item.kind === 'single') return <EvalRunRow key={`match-${item.run.eval_id}`} run={item.run} />
                if (item.kind === 'sweep') return <SweepGroupRow key={`sweep-${item.sweepId}`} sweepId={item.sweepId} runs={item.runs} />
                return <ToolEvalRunRow key={`tool-${item.run.eval_id}`} run={item.run} />
              })}
            </div>
          )}
        </>
      )}
    </section>
  )
}
