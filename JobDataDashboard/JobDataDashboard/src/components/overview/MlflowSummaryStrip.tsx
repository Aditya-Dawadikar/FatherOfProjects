import { useMlflowSummary } from '../../hooks'
import { MlflowLink } from '../../pages/evals/evalsComponents'

function formatCount(value: number): string {
  return value.toLocaleString()
}

function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`
}

export default function MlflowSummaryStrip() {
  const summaryQuery = useMlflowSummary()
  const summary = summaryQuery.data

  if (summaryQuery.isLoading) {
    return <div className="mlflow-summary-skeleton">Loading Agent Evals KPIs...</div>
  }

  if (summaryQuery.error || !summary) {
    return (
      <div className="banner banner-error">
        Could not load Agent Evals summary
        {summaryQuery.error ? `: ${summaryQuery.error.message}` : ''}
      </div>
    )
  }

  return (
    <section className="mlflow-summary-strip">
      <div className="mlflow-summary-strip-header">
        <div>
          <h3>Agent Evals Overview</h3>
          <p className="mlflow-summary-strip-subtitle">
            Every agent cycle and every prompt/tool/guardrail evaluation is tracked in MLflow.
          </p>
        </div>
        <MlflowLink href={summary.mlflow_base_url} label="Open MLflow" />
      </div>

      <div className="mlflow-summary-grid">
        <article className="summary-card mlflow-summary-card">
          <span>Production Traces Collected</span>
          <strong className="mlflow-summary-value">{formatCount(summary.traces_collected)}</strong>
          <p className="mlflow-summary-card-note">One trace per live agent matching cycle</p>
          <MlflowLink href={summary.traces_mlflow_url} label="View traces" />
        </article>

        <article className="summary-card mlflow-summary-card">
          <span>Offline Evals Triggered</span>
          <strong className="mlflow-summary-value">{formatCount(summary.offline_evals_triggered)}</strong>
          <ul className="mlflow-summary-breakdown">
            {summary.offline_evals_by_type.map((evalType) => (
              <li key={evalType.experiment_name}>
                <span>
                  {evalType.label} · {formatCount(evalType.run_count)}
                </span>
                <MlflowLink href={evalType.mlflow_url} label="View" />
              </li>
            ))}
          </ul>
        </article>

        <article className="summary-card mlflow-summary-card">
          <span>Prompt Versions Registered</span>
          <strong className="mlflow-summary-value">{formatCount(summary.registered_prompt_versions)}</strong>
          <p className="mlflow-summary-card-note">
            {summary.production_prompt_version
              ? `Production is running v${summary.production_prompt_version}`
              : 'Production version unavailable'}
          </p>
          <MlflowLink href={summary.mlflow_base_url} label="View registry" />
        </article>

        <article className="summary-card mlflow-summary-card">
          <span>LLM Tokens Tracked</span>
          <strong className="mlflow-summary-value">{formatCount(summary.total_tokens_tracked)}</strong>
          <p className="mlflow-summary-card-note">Summed across completed prompt evals</p>
        </article>

        <article className="summary-card mlflow-summary-card">
          <span>Est. Eval Spend Tracked</span>
          <strong className="mlflow-summary-value">{formatUsd(summary.total_cost_usd_tracked)}</strong>
          <p className="mlflow-summary-card-note">Summed across completed tool-selection evals</p>
        </article>
      </div>
    </section>
  )
}
