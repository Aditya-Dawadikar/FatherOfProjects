import type { EvalRun, EvalRunStatus, GuardrailsEvalRun, ToolEvalRun } from '../../types'

export const STATUS_LABEL: Record<EvalRunStatus, string> = {
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
}

export const RESULT_METRICS: Array<{
  key: keyof NonNullable<EvalRun['result']>
  label: string
  description: string
  formatter?: (value: number) => string
}> = [
  {
    key: 'accuracy',
    label: 'Accuracy',
    description: "Share of evaluated cases where the model's match decision agreed with the golden label.",
    formatter: formatPercent,
  },
  {
    key: 'precision',
    label: 'Precision',
    description: 'Of the cases the model flagged as a match, the share that were correct matches per the golden dataset.',
    formatter: formatPercent,
  },
  {
    key: 'recall',
    label: 'Recall',
    description: 'Of the true matches in the golden dataset, the share the model correctly identified.',
    formatter: formatPercent,
  },
  { key: 'f1', label: 'F1', description: 'Harmonic mean of precision and recall — a single score balancing both.' },
  {
    key: 'score_in_range_rate',
    label: 'Score In-Range Rate',
    description: "Share of cases where the model's predicted score fell within the golden dataset's accepted tolerance range.",
    formatter: formatPercent,
  },
  {
    key: 'criteria_in_range_rate',
    label: 'Criteria In-Range Rate',
    description: 'Share of cases where every rubric-criterion sub-score fell within its accepted tolerance range.',
    formatter: formatPercent,
  },
  {
    key: 'mean_predicted_score',
    label: 'Mean Predicted Score',
    description: "Average of the model's predicted match/fit scores across evaluated cases.",
  },
  {
    key: 'evaluated_cases',
    label: 'Evaluated Cases',
    description: 'Number of dataset cases that were actually scored in this run.',
  },
  {
    key: 'errored_cases',
    label: 'Errored Cases',
    description: 'Number of cases that failed to produce a scorable result (e.g. an LLM or tool error).',
  },
  { key: 'total_tokens', label: 'Total Tokens', description: 'Total LLM tokens consumed across the entire run.' },
  {
    key: 'mean_tokens_per_case',
    label: 'Mean Tokens / Case',
    description: 'Average LLM tokens consumed per evaluated case.',
  },
]

export const TOOL_RESULT_METRICS: Array<{
  key: keyof NonNullable<ToolEvalRun['result']>
  label: string
  description: string
  formatter?: (value: number) => string
}> = [
  {
    key: 'tool_selection_accuracy',
    label: 'Tool Selection Accuracy',
    description: 'Share of trials where the agent called the expected tool(s) for the scenario.',
    formatter: formatPercent,
  },
  {
    key: 'tool_error_rate',
    label: 'Tool Error Rate',
    description: 'Share of tool calls that returned an error or otherwise failed to execute.',
    formatter: formatPercent,
  },
  {
    key: 'call_volume_efficiency',
    label: 'Call Volume Efficiency',
    description: 'How close the number of tool calls the agent made was to the expected/minimal number for the scenario — higher means fewer wasted calls.',
    formatter: formatPercent,
  },
  {
    key: 'plan_adherence',
    label: 'Plan Adherence',
    description: "Share of trials where the agent's sequence of actions followed the scenario's expected plan or workflow.",
    formatter: formatPercent,
  },
  {
    key: 'consistency_score',
    label: 'Consistency Score',
    description: 'How consistent the agent behaved across repeated trials of the same scenario.',
    formatter: formatPercent,
  },
  {
    key: 'success_rate',
    label: 'Success Rate',
    description: "Share of trials that reached the scenario's expected end state or outcome.",
    formatter: formatPercent,
  },
  {
    key: 'cost_per_successful_run',
    label: 'Cost / Successful Run',
    description: 'Average LLM cost (USD) per trial that succeeded.',
    formatter: formatUsd,
  },
  {
    key: 'mean_cost_per_run',
    label: 'Mean Cost / Run',
    description: 'Average LLM cost (USD) across all trials, successful or not.',
    formatter: formatUsd,
  },
  {
    key: 'evaluated_cases',
    label: 'Evaluated Cases',
    description: 'Number of dataset cases actually run in this eval.',
  },
  {
    key: 'errored_cases',
    label: 'Errored Cases',
    description: 'Number of cases that failed to complete due to an error.',
  },
  {
    key: 'incomplete_trials',
    label: 'Incomplete Trials',
    description: "Number of trials that didn't finish — for example, they timed out or were cut off.",
  },
  {
    key: 'total_actual_calls',
    label: 'Total Tool Calls',
    description: 'Total number of tool calls made across all trials in the run.',
  },
  {
    key: 'total_guardrail_errors',
    label: 'Guardrail Violations',
    description: 'Total number of guardrail violations triggered across all trials.',
  },
  {
    key: 'mean_calls_per_trial',
    label: 'Mean Calls / Trial',
    description: 'Average number of tool calls made per trial.',
  },
  {
    key: 'total_cost_usd',
    label: 'Total Cost',
    description: 'Total LLM cost (USD) for the entire run.',
    formatter: formatUsd,
  },
]

export const GUARDRAILS_RESULT_METRICS: Array<{
  key: keyof NonNullable<GuardrailsEvalRun['result']>
  label: string
  description: string
  formatter?: (value: number) => string
}> = [
  {
    key: 'accuracy',
    label: 'Accuracy',
    description: "Share of cases where the guardrail's pass/flag decision matched the golden label.",
    formatter: formatPercent,
  },
  {
    key: 'precision',
    label: 'Precision',
    description: 'Of the cases the guardrail flagged as violations, the share that were true violations.',
    formatter: formatPercent,
  },
  {
    key: 'recall',
    label: 'Recall',
    description: 'Of the true violations in the golden dataset, the share the guardrail correctly flagged.',
    formatter: formatPercent,
  },
  {
    key: 'f1',
    label: 'F1',
    description: 'Harmonic mean of precision and recall for guardrail flagging.',
    formatter: formatPercent,
  },
  {
    key: 'guardrail_id_accuracy',
    label: 'Guardrail ID Accuracy',
    description: 'Of the correctly flagged cases, the share where the guardrail also identified the correct violation type/ID, not just that a violation occurred.',
    formatter: formatPercent,
  },
  { key: 'true_positive', label: 'True Positive', description: 'Count of cases correctly flagged as violations.' },
  {
    key: 'false_positive',
    label: 'False Positive',
    description: 'Count of cases incorrectly flagged as violations (false alarms).',
  },
  {
    key: 'false_negative',
    label: 'False Negative',
    description: 'Count of true violations the guardrail missed.',
  },
  {
    key: 'true_negative',
    label: 'True Negative',
    description: 'Count of cases correctly passed through as non-violations.',
  },
  {
    key: 'evaluated_cases',
    label: 'Evaluated Cases',
    description: 'Number of dataset cases actually scored in this run.',
  },
  {
    key: 'total_cases',
    label: 'Total Cases',
    description: 'Total number of cases in the dataset targeted by this run.',
  },
]

// A small, curated subset of RESULT_METRICS/TOOL_RESULT_METRICS/GUARDRAILS_RESULT_METRICS -- the
// KPI tab is meant to be read at a glance, not a replacement for the full comparison tables on
// the other tabs.
export const PROMPT_KPI_METRICS: Array<keyof NonNullable<EvalRun['result']>> = ['accuracy', 'f1', 'score_in_range_rate']
export const BEHAVIOR_KPI_METRICS: Array<keyof NonNullable<ToolEvalRun['result']>> = [
  'tool_selection_accuracy',
  'plan_adherence',
  'success_rate',
  'cost_per_successful_run',
]
export const GUARDRAILS_KPI_METRICS: Array<keyof NonNullable<GuardrailsEvalRun['result']>> = [
  'accuracy',
  'precision',
  'recall',
  'f1',
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

// One row per prompt_version, taking each version's most-recently-started run -- regardless of
// whether it came from a sweep (POST /evals/sweep, sweep_id set) or a standalone single-version
// trigger (POST /evals with prompt_version, sweep_id null). A version comparison table that only
// ever showed the latest sweep's group would go blank/stale the moment someone triggers just one
// version's run without re-sweeping everything.
export function latestRunPerPromptVersion(runs: EvalRun[]): EvalRun[] {
  const byVersion = new Map<string, EvalRun>()
  for (const run of runs) {
    if (!run.prompt_version) continue
    const existing = byVersion.get(run.prompt_version)
    if (!existing || (run.started_at ?? '') > (existing.started_at ?? '')) {
      byVersion.set(run.prompt_version, run)
    }
  }
  return [...byVersion.values()]
}

export function formatGuardrailsMetric(run: GuardrailsEvalRun, key: keyof NonNullable<GuardrailsEvalRun['result']>) {
  const metric = GUARDRAILS_RESULT_METRICS.find((entry) => entry.key === key)
  const rawValue = run.result?.[key]
  if (rawValue === undefined || metric === undefined) {
    return '—'
  }
  return metric.formatter ? metric.formatter(rawValue) : rawValue
}

export function latestToolRun(toolRuns: ToolEvalRun[]): ToolEvalRun | null {
  if (toolRuns.length === 0) return null
  return [...toolRuns].sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))[0]
}

export function latestGuardrailsRun(guardrailsRuns: GuardrailsEvalRun[]): GuardrailsEvalRun | null {
  if (guardrailsRuns.length === 0) return null
  return [...guardrailsRuns].sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))[0]
}

export function latestCompletedRun<T extends { status: EvalRunStatus; started_at: string | null }>(items: T[]): T | null {
  const completed = items.filter((item) => item.status === 'completed')
  if (completed.length === 0) return null
  return [...completed].sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))[0]
}

export type EvalsListItem =
  | { kind: 'single'; run: EvalRun; sortKey: string }
  | { kind: 'sweep'; sweepId: string; runs: EvalRun[]; sortKey: string }
  | { kind: 'tool'; run: ToolEvalRun; sortKey: string }
  | { kind: 'guardrails'; run: GuardrailsEvalRun; sortKey: string }

export function groupRunsForDisplay(
  runs: EvalRun[],
  toolRuns: ToolEvalRun[],
  guardrailsRuns: GuardrailsEvalRun[] = [],
): EvalsListItem[] {
  const sweepGroups = new Map<string, EvalRun[]>()
  const items: EvalsListItem[] = []

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

  for (const run of guardrailsRuns) {
    items.push({ kind: 'guardrails', run, sortKey: run.started_at ?? '' })
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

export function matchesPromptVersion(run: EvalRun, promptVersion: string): boolean {
  if (!promptVersion) return true
  return run.prompt_version === promptVersion
}

export function distinctPromptVersions(runs: EvalRun[]): string[] {
  const versions = new Set<string>()
  for (const run of runs) {
    if (run.prompt_version) versions.add(run.prompt_version)
  }
  return [...versions].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
}

export function distinctExperimentNames(
  runs: EvalRun[],
  toolRuns: ToolEvalRun[],
  guardrailsRuns: GuardrailsEvalRun[] = [],
): string[] {
  const names = new Set<string>()
  for (const run of runs) {
    if (run.experiment_name) names.add(run.experiment_name)
  }
  for (const run of toolRuns) {
    if (run.experiment_name) names.add(run.experiment_name)
  }
  for (const run of guardrailsRuns) {
    if (run.experiment_name) names.add(run.experiment_name)
  }
  return [...names].sort((a, b) => a.localeCompare(b))
}
