import { FiRefreshCw, FiZap } from 'react-icons/fi'
import { useEvals, useTriggerEvalSweep } from '../../hooks'
import { PromptComparisonTable } from './evalsComponents'

export default function PromptComparisonTab() {
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
  )
}
