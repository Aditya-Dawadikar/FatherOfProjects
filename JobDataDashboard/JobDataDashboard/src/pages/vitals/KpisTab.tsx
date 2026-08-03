import { useEvals, useToolEvals } from '../../hooks'
import { KpiCard } from './vitalsComponents'
import {
  BEHAVIOR_KPI_METRICS,
  PROMPT_KPI_METRICS,
  RESULT_METRICS,
  TOOL_RESULT_METRICS,
  formatDateTime,
  formatMetric,
  formatToolMetric,
  latestCompletedRun,
} from './vitalsUtils'

export default function KpisTab() {
  const evalsQuery = useEvals()
  const toolEvalsQuery = useToolEvals()
  const runs = evalsQuery.data ?? []
  const toolRuns = toolEvalsQuery.data ?? []

  const latestPromptRun = latestCompletedRun(runs)
  const latestBehaviorRun = latestCompletedRun(toolRuns)

  return (
    <div className="kpi-tab">
      <section className="kpi-section">
        <div className="kpi-section-header">
          <h3>Prompt Matching Quality</h3>
          {latestPromptRun && (
            <span className="eval-run-meta">
              {latestPromptRun.run_name ?? latestPromptRun.eval_id} · prompt v{latestPromptRun.prompt_version ?? '—'} ·{' '}
              {formatDateTime(latestPromptRun.started_at)}
            </span>
          )}
        </div>
        {latestPromptRun ? (
          <div className="summary-grid">
            {PROMPT_KPI_METRICS.map((key) => (
              <KpiCard
                key={key}
                label={RESULT_METRICS.find((metric) => metric.key === key)?.label ?? key}
                value={formatMetric(latestPromptRun, key)}
              />
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <p>No completed offline eval run yet -- trigger one from Prompt Version Comparison.</p>
          </div>
        )}
      </section>

      <section className="kpi-section">
        <div className="kpi-section-header">
          <h3>Agent Behavior</h3>
          {latestBehaviorRun && (
            <span className="eval-run-meta">
              {latestBehaviorRun.run_name ?? latestBehaviorRun.eval_id} · {formatDateTime(latestBehaviorRun.started_at)}
            </span>
          )}
        </div>
        {latestBehaviorRun ? (
          <div className="summary-grid">
            {BEHAVIOR_KPI_METRICS.map((key) => (
              <KpiCard
                key={key}
                label={TOOL_RESULT_METRICS.find((metric) => metric.key === key)?.label ?? key}
                value={formatToolMetric(latestBehaviorRun, key)}
              />
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <p>No completed tool-selection eval run yet -- trigger one from Agent Behavior.</p>
          </div>
        )}
      </section>
    </div>
  )
}
