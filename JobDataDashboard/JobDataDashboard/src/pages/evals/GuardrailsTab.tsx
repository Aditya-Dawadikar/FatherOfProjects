import { FiRefreshCw, FiZap } from 'react-icons/fi'
import { useGuardrailsEvals, useTriggerGuardrailsEval } from '../../hooks'
import { GuardrailsTable } from './evalsComponents'

export default function GuardrailsTab() {
  const guardrailsEvalsQuery = useGuardrailsEvals()
  const guardrailsEvalMutation = useTriggerGuardrailsEval()
  const guardrailsRuns = guardrailsEvalsQuery.data ?? []

  function runGuardrailsEval() {
    guardrailsEvalMutation.mutate(undefined, {
      onSuccess: () => {
        guardrailsEvalsQuery.refetch()
      },
    })
  }

  return (
    <>
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Current Agent State</p>
          <h2>Guardrails experiments</h2>
        </div>
        <div className="toolbar-actions">
          <button
            type="button"
            className="primary-button ghost-button-with-icon"
            onClick={runGuardrailsEval}
            disabled={guardrailsEvalMutation.isPending}
          >
            <FiZap aria-hidden="true" className="button-icon" />
            {guardrailsEvalMutation.isPending ? 'Triggering run...' : 'Run Guardrails Eval'}
          </button>
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={() => guardrailsEvalsQuery.refetch()}
            disabled={guardrailsEvalsQuery.isFetching}
          >
            <FiRefreshCw aria-hidden="true" className={guardrailsEvalsQuery.isFetching ? 'button-icon spin' : 'button-icon'} />
            {guardrailsEvalsQuery.isFetching ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {guardrailsEvalMutation.isSuccess && (
        <div className="banner banner-info">Triggered a guardrails eval run against the golden dataset.</div>
      )}
      {guardrailsEvalMutation.error && <div className="banner banner-error">{guardrailsEvalMutation.error.message}</div>}
      {guardrailsEvalsQuery.error && <div className="banner banner-error">{guardrailsEvalsQuery.error.message}</div>}

      <GuardrailsTable guardrailsRuns={guardrailsRuns} />
    </>
  )
}
