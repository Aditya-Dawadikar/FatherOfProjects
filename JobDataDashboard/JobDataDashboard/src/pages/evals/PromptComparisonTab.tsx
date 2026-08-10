import { useState } from 'react'
import { FiPlay, FiRefreshCw, FiZap } from 'react-icons/fi'
import { useEvals, usePrompts, useTriggerEval, useTriggerEvalSweep } from '../../hooks'
import { MetricGlossary, PromptComparisonTable } from './evalsComponents'
import { RESULT_METRICS } from './evalsUtils'

export default function PromptComparisonTab() {
  const evalsQuery = useEvals()
  const promptsQuery = usePrompts()
  const sweepMutation = useTriggerEvalSweep()
  const triggerMutation = useTriggerEval()
  const runs = evalsQuery.data ?? []
  const prompts = promptsQuery.data ?? []

  const [selectedVersion, setSelectedVersion] = useState('')
  // Derived, not state-synced-via-effect: defaults the picker to whichever version is currently
  // 'production'-aliased once the registry loads, so the common case (eval the version that's
  // actually live) needs no selection at all, without an effect+setState render cascade.
  const defaultVersion = (prompts.find((prompt) => prompt.is_active) ?? prompts[0])?.version ?? ''
  const effectiveVersion = selectedVersion || defaultVersion

  function runSweep() {
    sweepMutation.mutate(undefined, {
      onSuccess: () => {
        evalsQuery.refetch()
      },
    })
  }

  function runForSelectedVersion() {
    if (!effectiveVersion) return
    triggerMutation.mutate(
      { prompt_source: 'production', prompt_version: Number(effectiveVersion) },
      {
        onSuccess: () => {
          evalsQuery.refetch()
        },
      },
    )
  }

  return (
    <>
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Current Agent State</p>
          <h2>Prompt version comparison</h2>
        </div>
        <div className="toolbar-actions">
          <select
            className="search-input filter-select"
            value={effectiveVersion}
            onChange={(event) => setSelectedVersion(event.target.value)}
            aria-label="Prompt version to run an eval against"
            disabled={promptsQuery.isLoading || prompts.length === 0}
          >
            {prompts.length === 0 && <option value="">No registered prompt versions</option>}
            {prompts.map((prompt) => (
              <option key={prompt.version} value={prompt.version}>
                v{prompt.version} · {prompt.schema_mode}
                {prompt.is_active ? ' · active' : ''}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="primary-button ghost-button-with-icon"
            onClick={runForSelectedVersion}
            disabled={triggerMutation.isPending || !effectiveVersion}
          >
            <FiPlay aria-hidden="true" className="button-icon" />
            {triggerMutation.isPending ? 'Triggering run...' : `Run Eval for v${effectiveVersion || '—'}`}
          </button>
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={runSweep}
            disabled={sweepMutation.isPending}
          >
            <FiZap aria-hidden="true" className="button-icon" />
            {sweepMutation.isPending ? 'Triggering sweep...' : 'Run Sweep (all versions)'}
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

      {triggerMutation.isSuccess && (
        <div className="banner banner-info">
          Triggered eval run {triggerMutation.data.eval_id} against prompt v{triggerMutation.data.prompt_version ?? effectiveVersion}.
        </div>
      )}
      {triggerMutation.error && <div className="banner banner-error">{triggerMutation.error.message}</div>}
      {sweepMutation.isSuccess && (
        <div className="banner banner-info">
          Triggered {sweepMutation.data.length} eval run{sweepMutation.data.length === 1 ? '' : 's'} — one per registered prompt version.
        </div>
      )}
      {sweepMutation.error && <div className="banner banner-error">{sweepMutation.error.message}</div>}
      {evalsQuery.error && <div className="banner banner-error">{evalsQuery.error.message}</div>}
      {promptsQuery.error && <div className="banner banner-error">{promptsQuery.error.message}</div>}

      <MetricGlossary title="What these metrics mean" metrics={RESULT_METRICS} />

      <PromptComparisonTable runs={runs} />
    </>
  )
}
