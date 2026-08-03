import { useState } from 'react'
import { FiRefreshCw } from 'react-icons/fi'
import { useEvals, useGuardrailsEvals, useToolEvals } from '../../hooks'
import { EvalRunRow, GuardrailsEvalRunRow, SweepGroupRow, ToolEvalRunRow } from './vitalsComponents'
import {
  distinctExperimentNames,
  groupRunsForDisplay,
  matchesHistoryFilters,
  type HistoryFilters,
} from './vitalsUtils'

export default function RunHistoryTab() {
  const evalsQuery = useEvals()
  const toolEvalsQuery = useToolEvals()
  const guardrailsEvalsQuery = useGuardrailsEvals()
  const runs = evalsQuery.data ?? []
  const toolRuns = toolEvalsQuery.data ?? []
  const guardrailsRuns = guardrailsEvalsQuery.data ?? []

  const isLoading = evalsQuery.isLoading || toolEvalsQuery.isLoading || guardrailsEvalsQuery.isLoading
  const isFetching = evalsQuery.isFetching || toolEvalsQuery.isFetching || guardrailsEvalsQuery.isFetching
  const totalRunCount = runs.length + toolRuns.length + guardrailsRuns.length

  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [experimentFilter, setExperimentFilter] = useState('')
  const hasActiveFilters = Boolean(dateFrom || dateTo || experimentFilter)
  const historyFilters: HistoryFilters = { dateFrom, dateTo, experimentName: experimentFilter }
  const experimentNames = distinctExperimentNames(runs, toolRuns, guardrailsRuns)
  const filteredRuns = runs.filter((run) => matchesHistoryFilters(run, historyFilters))
  const filteredToolRuns = toolRuns.filter((run) => matchesHistoryFilters(run, historyFilters))
  const filteredGuardrailsRuns = guardrailsRuns.filter((run) => matchesHistoryFilters(run, historyFilters))
  const filteredRunCount = filteredRuns.length + filteredToolRuns.length + filteredGuardrailsRuns.length

  function clearHistoryFilters() {
    setDateFrom('')
    setDateTo('')
    setExperimentFilter('')
  }

  return (
    <>
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">JobManagerAgent</p>
          <h2>
            {isLoading
              ? 'Loading eval runs...'
              : hasActiveFilters
                ? `${filteredRunCount} of ${totalRunCount} eval run${totalRunCount === 1 ? '' : 's'}`
                : `${totalRunCount} eval run${totalRunCount === 1 ? '' : 's'}`}
          </h2>
        </div>
        <div className="toolbar-actions">
          <select
            className="search-input filter-select"
            value={experimentFilter}
            onChange={(event) => setExperimentFilter(event.target.value)}
            aria-label="Filter by experiment"
          >
            <option value="">All experiments</option>
            {experimentNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <input
            className="search-input date-input"
            type="date"
            value={dateFrom}
            max={dateTo || undefined}
            onChange={(event) => setDateFrom(event.target.value)}
            aria-label="From date"
          />
          <input
            className="search-input date-input"
            type="date"
            value={dateTo}
            min={dateFrom || undefined}
            onChange={(event) => setDateTo(event.target.value)}
            aria-label="To date"
          />
          {hasActiveFilters && (
            <button type="button" className="ghost-button" onClick={clearHistoryFilters}>
              Clear filters
            </button>
          )}
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={() => {
              evalsQuery.refetch()
              toolEvalsQuery.refetch()
              guardrailsEvalsQuery.refetch()
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
      {guardrailsEvalsQuery.error && <div className="banner banner-error">{guardrailsEvalsQuery.error.message}</div>}

      {!isLoading && totalRunCount === 0 && (
        <div className="empty-state">
          <h2>No eval runs yet</h2>
          <p>Switch to Prompt Version Comparison, Agent Behavior, or Guardrails to trigger a run.</p>
        </div>
      )}

      {!isLoading && totalRunCount > 0 && filteredRunCount === 0 && (
        <div className="empty-state">
          <h2>No runs match these filters</h2>
          <p>Try widening the date range or clearing the experiment filter.</p>
        </div>
      )}

      {filteredRunCount > 0 && (
        <div className="eval-run-list">
          {groupRunsForDisplay(filteredRuns, filteredToolRuns, filteredGuardrailsRuns).map((item) => {
            if (item.kind === 'single') return <EvalRunRow key={`match-${item.run.eval_id}`} run={item.run} />
            if (item.kind === 'sweep') return <SweepGroupRow key={`sweep-${item.sweepId}`} sweepId={item.sweepId} runs={item.runs} />
            if (item.kind === 'tool') return <ToolEvalRunRow key={`tool-${item.run.eval_id}`} run={item.run} />
            return <GuardrailsEvalRunRow key={`guardrails-${item.run.eval_id}`} run={item.run} />
          })}
        </div>
      )}
    </>
  )
}
