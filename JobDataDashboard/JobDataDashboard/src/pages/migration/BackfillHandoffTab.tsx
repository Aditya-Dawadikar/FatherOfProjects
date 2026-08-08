import { useState } from 'react'
import { FiChevronDown, FiChevronUp, FiPause, FiPlay, FiRefreshCw, FiSlash, FiZap } from 'react-icons/fi'
import {
  useBackfillProcesses,
  useBackfillRuns,
  useCancelBackfillRun,
  usePauseUnscoredBackfill,
  usePrompts,
  useResumeUnscoredBackfill,
  useTriggerBackfill,
  useUnscoredBackfillStatus,
} from '../../hooks'
import type { BackfillRun, BackfillRunStatusValue } from '../../types'

const RUN_STATUS_LABEL: Record<BackfillRunStatusValue, string> = {
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

function formatDateTime(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

// Error/cancel-reason text (rescore_with_prompt.py's MatchResponseError messages in particular
// can run long, e.g. echoing a full model response) collapses past this length rather than
// stretching the row -- see ReasonCell below.
const REASON_COLLAPSE_THRESHOLD = 80

function UnscoredBackfillControl() {
  const statusQuery = useUnscoredBackfillStatus()
  const pauseMutation = usePauseUnscoredBackfill()
  const resumeMutation = useResumeUnscoredBackfill()
  const [pauseReason, setPauseReason] = useState('prompt cutover')

  const paused = statusQuery.data?.paused ?? false

  return (
    <div className="migration-subsection">
      <div className="migration-subsection-header">
        <h3>Never-scored-jobs backfill (idle-triggered)</h3>
        <span className={`status-pill ${paused ? 'status-pill-failed' : 'status-pill-completed'}`}>
          {paused ? `Paused (${statusQuery.data?.reason})` : 'Running normally'}
        </span>
      </div>
      <p className="match-detail-hint">
        Only affects idle-triggered "drain never-scored jobs" cycles -- live cycles never pause. Not required for
        correctness (the active prompt is re-resolved fresh every cycle regardless), but gives a clean, predictable
        window during a cutover.
      </p>
      <div className="toolbar-actions">
        <input
          className="search-input"
          type="text"
          value={pauseReason}
          onChange={(event) => setPauseReason(event.target.value)}
          placeholder="Reason for pausing"
          disabled={paused}
        />
        <button
          type="button"
          className="ghost-button ghost-button-with-icon"
          onClick={() => pauseMutation.mutate(pauseReason)}
          disabled={paused || pauseMutation.isPending}
        >
          <FiPause aria-hidden="true" className="button-icon" />
          Pause
        </button>
        <button
          type="button"
          className="ghost-button ghost-button-with-icon"
          onClick={() => resumeMutation.mutate()}
          disabled={!paused || resumeMutation.isPending}
        >
          <FiPlay aria-hidden="true" className="button-icon" />
          Resume
        </button>
      </div>
    </div>
  )
}

function BackfillTriggerForm() {
  const processesQuery = useBackfillProcesses()
  const promptsQuery = usePrompts()
  const triggerMutation = useTriggerBackfill()
  const processes = processesQuery.data ?? []
  const prompts = promptsQuery.data ?? []
  const [process, setProcess] = useState('rescore_with_prompt')
  const [promptVersion, setPromptVersion] = useState('')
  const [limitText, setLimitText] = useState('5')

  const selectedProcess = processes.find((item) => item.name === process)

  function trigger() {
    if (!promptVersion.trim()) return
    const limit = limitText.trim() ? Number(limitText) : null
    triggerMutation.mutate({ process, params: { prompt_version: promptVersion.trim() }, limit })
  }

  return (
    <div className="migration-subsection">
      <div className="migration-subsection-header">
        <h3>Trigger a backfill run</h3>
      </div>
      {selectedProcess && <p className="match-detail-hint">{selectedProcess.description}</p>}
      <div className="toolbar-actions">
        <select className="search-input filter-select" value={process} onChange={(event) => setProcess(event.target.value)}>
          {processes.map((item) => (
            <option key={item.name} value={item.name}>
              {item.name}
            </option>
          ))}
        </select>
        <select
          className="search-input filter-select"
          value={promptVersion}
          onChange={(event) => setPromptVersion(event.target.value)}
          disabled={promptsQuery.isLoading}
        >
          <option value="">Select a prompt version...</option>
          {prompts.map((prompt) => (
            <option key={prompt.version} value={prompt.version}>
              v{prompt.version} · {prompt.schema_mode}
              {prompt.is_active ? ' (currently active)' : ''}
            </option>
          ))}
        </select>
        <input
          className="search-input min-score-input"
          type="number"
          min={1}
          value={limitText}
          onChange={(event) => setLimitText(event.target.value)}
          placeholder="limit (blank = full run)"
        />
        <button
          type="button"
          className="primary-button ghost-button-with-icon"
          onClick={trigger}
          disabled={!promptVersion.trim() || triggerMutation.isPending}
        >
          <FiZap aria-hidden="true" className="button-icon" />
          {triggerMutation.isPending ? 'Triggering...' : 'Trigger'}
        </button>
      </div>
      <p className="match-detail-hint">
        Start with a small limit (e.g. 5) to validate output quality via the Matches page before re-triggering
        without a limit. Only one backfill run is ever allowed to be "running" -- triggering here automatically
        stops any run already in flight (it finishes its current batch first; nothing already written is purged).
      </p>
      {triggerMutation.isSuccess && (
        <div className="banner banner-info">Started run {triggerMutation.data.run_id}.</div>
      )}
      {triggerMutation.error && <div className="banner banner-error">{triggerMutation.error.message}</div>}
      {promptsQuery.error && <div className="banner banner-error">{promptsQuery.error.message}</div>}
    </div>
  )
}

function ReasonCell({ text }: { text: string | null }) {
  const [isExpanded, setIsExpanded] = useState(false)

  if (!text) {
    return <td>—</td>
  }

  const isCollapsible = text.length > REASON_COLLAPSE_THRESHOLD

  return (
    <td className="reason-cell">
      <div className={`reason-text${isExpanded ? ' is-expanded' : ''}`} title={isCollapsible && !isExpanded ? text : undefined}>
        {text}
      </div>
      {isCollapsible && (
        <button type="button" className="reason-toggle" onClick={() => setIsExpanded((value) => !value)}>
          {isExpanded ? <FiChevronUp aria-hidden="true" className="button-icon" /> : <FiChevronDown aria-hidden="true" className="button-icon" />}
          {isExpanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </td>
  )
}

function BackfillRunRow({ run }: { run: BackfillRun }) {
  const cancelMutation = useCancelBackfillRun()
  const total = run.candidate_count ?? 0
  const progressPercent = total > 0 ? Math.min(100, Math.round((run.processed / total) * 100)) : 0

  return (
    <tr>
      <td>
        <span className={`status-pill status-pill-${run.status === 'cancelled' ? 'failed' : run.status}`}>
          {RUN_STATUS_LABEL[run.status]}
        </span>
      </td>
      <td>{run.process}</td>
      <td>{typeof run.params.prompt_version === 'string' || typeof run.params.prompt_version === 'number' ? `v${run.params.prompt_version}` : '—'}</td>
      <td>
        {run.candidate_count === null ? 'selecting...' : `${run.processed} / ${total} (${progressPercent}%)`}
      </td>
      <td>{run.rescored}</td>
      <td>{run.not_found_404}</td>
      <td>{run.crawl_error}</td>
      <td>{run.errored}</td>
      <ReasonCell text={run.error ?? run.cancel_reason ?? null} />
      <td>{formatDateTime(run.started_at)}</td>
      <td>{formatDateTime(run.finished_at)}</td>
      <td>
        {run.status === 'running' && (
          <button
            type="button"
            className="danger-button danger-button-compact ghost-button-with-icon"
            onClick={() => cancelMutation.mutate(run.run_id)}
            disabled={cancelMutation.isPending}
          >
            <FiSlash aria-hidden="true" className="button-icon" />
            Cancel
          </button>
        )}
      </td>
    </tr>
  )
}

function BackfillRunHistory() {
  const runsQuery = useBackfillRuns()
  const runs = runsQuery.data ?? []

  return (
    <div className="migration-subsection">
      <div className="migration-subsection-header">
        <h3>Backfill run history</h3>
        <button
          type="button"
          className="ghost-button ghost-button-with-icon"
          onClick={() => runsQuery.refetch()}
          disabled={runsQuery.isFetching}
        >
          <FiRefreshCw aria-hidden="true" className={runsQuery.isFetching ? 'button-icon spin' : 'button-icon'} />
          Refresh
        </button>
      </div>
      {runsQuery.error && <div className="banner banner-error">{runsQuery.error.message}</div>}
      <div className="table-wrap">
        <table className="jobs-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Process</th>
              <th>Prompt</th>
              <th>Progress</th>
              <th>Rescored</th>
              <th>404s</th>
              <th>Crawl err</th>
              <th>Errored</th>
              <th>Error / cancel reason</th>
              <th>Started</th>
              <th>Finished</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <BackfillRunRow key={run.run_id} run={run} />
            ))}
          </tbody>
        </table>
        {!runsQuery.isLoading && runs.length === 0 && (
          <div className="empty-state">
            <p>No backfill runs yet -- trigger one above.</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default function BackfillHandoffTab() {
  return (
    <section className="migration-section">
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Migration handoff</p>
          <h2>Observability</h2>
        </div>
      </div>
      <UnscoredBackfillControl />
      <BackfillTriggerForm />
      <BackfillRunHistory />
    </section>
  )
}
