import { FiRefreshCw, FiZap } from 'react-icons/fi'
import { useToolEvals, useTriggerToolEval } from '../../hooks'
import { AgentBehaviorTable } from './vitalsComponents'

export default function AgentBehaviorTab() {
  const toolEvalsQuery = useToolEvals()
  const toolEvalMutation = useTriggerToolEval()
  const toolRuns = toolEvalsQuery.data ?? []

  function runToolEval() {
    toolEvalMutation.mutate(undefined, {
      onSuccess: () => {
        toolEvalsQuery.refetch()
      },
    })
  }

  return (
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
  )
}
