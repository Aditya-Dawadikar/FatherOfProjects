import type { EvalRun, EvalRunStatus, ToolEvalRun } from '../../types'

export const STATUS_LABEL: Record<EvalRunStatus, string> = {
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
}

export const RESULT_METRICS: Array<{ key: keyof NonNullable<EvalRun['result']>; label: string; formatter?: (value: number) => string }> = [
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

export const TOOL_RESULT_METRICS: Array<{
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

// A small, curated subset of RESULT_METRICS/TOOL_RESULT_METRICS -- the KPI tab is meant to be
// read at a glance, not a replacement for the full comparison tables on the other tabs.
export const PROMPT_KPI_METRICS: Array<keyof NonNullable<EvalRun['result']>> = ['accuracy', 'f1', 'score_in_range_rate']
export const BEHAVIOR_KPI_METRICS: Array<keyof NonNullable<ToolEvalRun['result']>> = [
  'tool_selection_accuracy',
  'plan_adherence',
  'success_rate',
  'cost_per_successful_run',
]

export const SWEEP_COMPARE_COLUMNS: Array<{ key: keyof NonNullable<EvalRun['result']>; label: string }> = [
  { key: 'accuracy', label: 'Accuracy' },
  { key: 'precision', label: 'Precision' },
  { key: 'recall', label: 'Recall' },
  { key: 'f1', label: 'F1' },
  { key: 'total_tokens', label: 'Total Tokens' },
  { key: 'mean_tokens_per_case', label: 'Mean Tokens / Case' },
]

export function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

export function formatUsd(value: number) {
  // Per-run/per-success costs are typically fractions of a cent -- fixed 2-decimal formatting
  // would round most of them to "$0.00" and hide exactly the signal this metric exists to show.
  const decimals = value !== 0 && Math.abs(value) < 0.01 ? 4 : 2
  return `$${value.toFixed(decimals)}`
}

export function formatDateTime(value: string | null) {
  if (!value) {
    return '—'
  }
  return new Date(value).toLocaleString()
}

export function formatDuration(startedAt: string | null, finishedAt: string | null) {
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

export function formatMetric(run: EvalRun, key: keyof NonNullable<EvalRun['result']>) {
  const metric = RESULT_METRICS.find((entry) => entry.key === key)
  const rawValue = run.result?.[key]
  if (rawValue === undefined || metric === undefined) {
    return '—'
  }
  return metric.formatter ? metric.formatter(rawValue) : rawValue
}

export function formatToolMetric(run: ToolEvalRun, key: keyof NonNullable<ToolEvalRun['result']>) {
  const metric = TOOL_RESULT_METRICS.find((entry) => entry.key === key)
  const rawValue = run.result?.[key]
  if (rawValue === undefined || metric === undefined) {
    return '—'
  }
  return metric.formatter ? metric.formatter(rawValue) : rawValue
}

export function latestSweepGroup(runs: EvalRun[]): { sweepId: string; runs: EvalRun[]; latestStartedAt: string } | null {
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

export function latestToolRun(toolRuns: ToolEvalRun[]): ToolEvalRun | null {
  if (toolRuns.length === 0) return null
  return [...toolRuns].sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))[0]
}

export function latestCompletedRun<T extends { status: EvalRunStatus; started_at: string | null }>(items: T[]): T | null {
  const completed = items.filter((item) => item.status === 'completed')
  if (completed.length === 0) return null
  return [...completed].sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))[0]
}

export type VitalsListItem =
  | { kind: 'single'; run: EvalRun; sortKey: string }
  | { kind: 'sweep'; sweepId: string; runs: EvalRun[]; sortKey: string }
  | { kind: 'tool'; run: ToolEvalRun; sortKey: string }

export function groupRunsForDisplay(runs: EvalRun[], toolRuns: ToolEvalRun[]): VitalsListItem[] {
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

export type HistoryFilters = { dateFrom: string; dateTo: string; experimentName: string }

export function matchesHistoryFilters(
  run: { started_at: string | null; experiment_name: string | null },
  filters: HistoryFilters,
): boolean {
  if (filters.experimentName && run.experiment_name !== filters.experimentName) {
    return false
  }
  if (filters.dateFrom || filters.dateTo) {
    // started_at is an ISO datetime (see api/eval_runs.py's _ms_to_iso) -- the first 10 chars are
    // always its YYYY-MM-DD date, which sorts lexicographically the same as chronologically, so
    // string comparison against the <input type="date"> values (same format) works directly.
    const runDate = run.started_at?.slice(0, 10) ?? ''
    if (!runDate) return false
    if (filters.dateFrom && runDate < filters.dateFrom) return false
    if (filters.dateTo && runDate > filters.dateTo) return false
  }
  return true
}

export function distinctExperimentNames(runs: EvalRun[], toolRuns: ToolEvalRun[]): string[] {
  const names = new Set<string>()
  for (const run of runs) {
    if (run.experiment_name) names.add(run.experiment_name)
  }
  for (const run of toolRuns) {
    if (run.experiment_name) names.add(run.experiment_name)
  }
  return [...names].sort((a, b) => a.localeCompare(b))
}
