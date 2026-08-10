import { useEvals, useGuardrailsEvals, useToolEvals } from '../../hooks'
import { EmptyKpiCard, KpiCard } from './evalsComponents'
import {
  BEHAVIOR_KPI_METRICS,
  GUARDRAILS_KPI_METRICS,
  GUARDRAILS_RESULT_METRICS,
  PROMPT_KPI_METRICS,
  RESULT_METRICS,
  TOOL_RESULT_METRICS,
  formatDateTime,
  formatGuardrailsMetric,
  formatMetric,
  formatToolMetric,
  latestCompletedRun,
} from './evalsUtils'

export default function KpisTab() {
  const evalsQuery = useEvals()
  const toolEvalsQuery = useToolEvals()
  const guardrailsEvalsQuery = useGuardrailsEvals()
  const runs = evalsQuery.data ?? []
  const toolRuns = toolEvalsQuery.data ?? []
  const guardrailsRuns = guardrailsEvalsQuery.data ?? []

  const latestPromptRun = latestCompletedRun(runs)
  const latestBehaviorRun = latestCompletedRun(toolRuns)
  const latestGuardrailsRun = latestCompletedRun(guardrailsRuns)

  const promptMeta = latestPromptRun
    ? `${latestPromptRun.run_name ?? latestPromptRun.eval_id} · prompt v${latestPromptRun.prompt_version ?? '—'} · ${formatDateTime(latestPromptRun.started_at)}`
    : undefined
  const behaviorMeta = latestBehaviorRun
    ? `${latestBehaviorRun.run_name ?? latestBehaviorRun.eval_id} · ${formatDateTime(latestBehaviorRun.started_at)}`
    : undefined
  const guardrailsMeta = latestGuardrailsRun
    ? `${latestGuardrailsRun.run_name ?? latestGuardrailsRun.eval_id} · ${formatDateTime(latestGuardrailsRun.started_at)}`
    : undefined

  return (
    <div className="kpi-tab">
      <div className="kpi-grid">
        {latestPromptRun ? (
          PROMPT_KPI_METRICS.map((key) => {
            const metric = RESULT_METRICS.find((entry) => entry.key === key)
            return (
              <KpiCard
                key={`prompt-${key}`}
                category="Prompt Matching Quality"
                label={metric?.label ?? key}
                description={metric?.description ?? ''}
                value={formatMetric(latestPromptRun, key)}
                meta={promptMeta}
              />
            )
          })
        ) : (
          <EmptyKpiCard
            category="Prompt Matching Quality"
            message="No completed offline eval run yet -- trigger one from Prompt Version Comparison."
          />
        )}

        {latestBehaviorRun ? (
          BEHAVIOR_KPI_METRICS.map((key) => {
            const metric = TOOL_RESULT_METRICS.find((entry) => entry.key === key)
            return (
              <KpiCard
                key={`behavior-${key}`}
                category="Agent Behavior"
                label={metric?.label ?? key}
                description={metric?.description ?? ''}
                value={formatToolMetric(latestBehaviorRun, key)}
                meta={behaviorMeta}
              />
            )
          })
        ) : (
          <EmptyKpiCard
            category="Agent Behavior"
            message="No completed tool-selection eval run yet -- trigger one from Agent Behavior."
          />
        )}

        {latestGuardrailsRun ? (
          GUARDRAILS_KPI_METRICS.map((key) => {
            const metric = GUARDRAILS_RESULT_METRICS.find((entry) => entry.key === key)
            return (
              <KpiCard
                key={`guardrails-${key}`}
                category="Guardrails"
                label={metric?.label ?? key}
                description={metric?.description ?? ''}
                value={formatGuardrailsMetric(latestGuardrailsRun, key)}
                meta={guardrailsMeta}
              />
            )
          })
        ) : (
          <EmptyKpiCard
            category="Guardrails"
            message="No completed guardrails eval run yet -- trigger one from Guardrails."
          />
        )}
      </div>
    </div>
  )
}
