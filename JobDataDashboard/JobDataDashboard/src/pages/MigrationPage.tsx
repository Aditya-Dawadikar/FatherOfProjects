import { useEffect, useState } from 'react'
import { FiChevronDown, FiChevronUp, FiPause, FiPlay, FiRefreshCw, FiRotateCcw, FiSlash, FiZap } from 'react-icons/fi'
import {
  useBackfillProcesses,
  useBackfillRuns,
  useCancelBackfillRun,
  usePauseUnscoredBackfill,
  usePromptHistory,
  usePrompts,
  useRateLimits,
  useResumeUnscoredBackfill,
  useRevertActivePrompt,
  useSetActivePrompt,
  useTriggerBackfill,
  useUpdateRateLimitsDistribution,
  useUnscoredBackfillStatus,
} from '../hooks'
import type { BackfillRun, BackfillRunStatusValue } from '../types'

const RUN_STATUS_LABEL: Record<BackfillRunStatusValue, string> = {
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

const BUCKET_LABEL: Record<string, string> = {
  live: 'Live (x)',
  backfill: 'Backfill (y)',
  eval: 'Eval (z)',
}

function formatDateTime(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

function usagePercent(count: number, cap: number) {
  if (cap <= 0) return 0
  return Math.min(100, Math.round((count / cap) * 100))
}

// Error/cancel-reason text (rescore_with_prompt.py's MatchResponseError messages in particular
// can run long, e.g. echoing a full model response) collapses past this length rather than
// stretching the row -- see ReasonCell below.
const REASON_COLLAPSE_THRESHOLD = 80

// --- Section 1: Feature flag -- active prompt version -----------------------------------------

function FeatureFlagSection() {
  const promptsQuery = usePrompts()
  const historyQuery = usePromptHistory()
  const setActiveMutation = useSetActivePrompt()
  const revertMutation = useRevertActivePrompt()
  const [selectedVersion, setSelectedVersion] = useState('')

  const prompts = promptsQuery.data ?? []
  const active = prompts.find((prompt) => prompt.is_active)
  const settableVersions = prompts.filter((prompt) => prompt.schema_mode !== 'batch')

  function applyActiveVersion() {
    if (!selectedVersion) return
    setActiveMutation.mutate(selectedVersion, {
      onSuccess: () => {
        promptsQuery.refetch()
        historyQuery.refetch()
      },
    })
  }

  return (
    <section className="migration-section">
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Feature flag</p>
          <h2>Active prompt version</h2>
        </div>
        <div className="toolbar-actions">
          <select
            className="search-input filter-select"
            value={selectedVersion}
            onChange={(event) => setSelectedVersion(event.target.value)}
            disabled={promptsQuery.isLoading}
          >
            <option value="">Select a version to activate...</option>
            {settableVersions.map((prompt) => (
              <option key={prompt.version} value={prompt.version}>
                v{prompt.version} · {prompt.schema_mode}
                {prompt.is_active ? ' (currently active)' : ''}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="primary-button ghost-button-with-icon"
            onClick={applyActiveVersion}
            disabled={!selectedVersion || setActiveMutation.isPending}
          >
            <FiZap aria-hidden="true" className="button-icon" />
            {setActiveMutation.isPending ? 'Setting active...' : 'Set active'}
          </button>
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={() => revertMutation.mutate(undefined, { onSuccess: () => { promptsQuery.refetch(); historyQuery.refetch() } })}
            disabled={revertMutation.isPending}
          >
            <FiRotateCcw aria-hidden="true" className="button-icon" />
            {revertMutation.isPending ? 'Reverting...' : 'Revert to previous'}
          </button>
        </div>
      </div>

      {active && (
        <div className="banner banner-info">
          Production is currently <strong>v{active.version}</strong> ({active.schema_mode}, rubric v{active.rubric_version}).
          Batch-mode versions (schema_mode="batch") can never be set active -- they're backfill-only.
        </div>
      )}
      {setActiveMutation.isSuccess && (
        <div className="banner banner-info">
          Set active: v{setActiveMutation.data.version}. Takes effect on the next live/backfill cycle.
        </div>
      )}
      {setActiveMutation.error && <div className="banner banner-error">{setActiveMutation.error.message}</div>}
      {revertMutation.isSuccess && (
        <div className="banner banner-info">Reverted to v{revertMutation.data.version}. No data was purged.</div>
      )}
      {revertMutation.error && <div className="banner banner-error">{revertMutation.error.message}</div>}
      {promptsQuery.error && <div className="banner banner-error">{promptsQuery.error.message}</div>}

      <div className="table-wrap">
        <table className="jobs-table">
          <thead>
            <tr>
              <th>When</th>
              <th>From</th>
              <th>To</th>
              <th>Schema</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {(historyQuery.data ?? []).map((entry, index) => (
              <tr key={`${entry.changed_at}-${index}`}>
                <td>{formatDateTime(entry.changed_at)}</td>
                <td>{entry.from_version ? `v${entry.from_version}` : 'n/a (bootstrap)'}</td>
                <td>v{entry.to_version}</td>
                <td>{entry.schema_mode}</td>
                <td>{entry.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!historyQuery.isLoading && (historyQuery.data ?? []).length === 0 && (
          <div className="empty-state">
            <p>No prompt version changes recorded yet.</p>
          </div>
        )}
      </div>
    </section>
  )
}

// --- Section 2: Migration handoff observability ------------------------------------------------

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

function HandoffObservabilitySection() {
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

// --- Section 3: Real-time RPM breakdown --------------------------------------------------------

function RpmBreakdownSection() {
  const rateLimitsQuery = useRateLimits()
  const updateDistributionMutation = useUpdateRateLimitsDistribution()
  const breakdown = rateLimitsQuery.data
  const [liveCap, setLiveCap] = useState('')
  const [backfillCap, setBackfillCap] = useState('')
  const [evalCap, setEvalCap] = useState('')
  const [providerQuota, setProviderQuota] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (!breakdown) return
    const live = breakdown.buckets.find((bucket) => bucket.bucket === 'live')
    const backfill = breakdown.buckets.find((bucket) => bucket.bucket === 'backfill')
    const evalBucket = breakdown.buckets.find((bucket) => bucket.bucket === 'eval')
    setLiveCap(live ? String(live.cap) : '')
    setBackfillCap(backfill ? String(backfill.cap) : '')
    setEvalCap(evalBucket ? String(evalBucket.cap) : '')
    setProviderQuota(breakdown.provider_quota !== null ? String(breakdown.provider_quota) : '')
  }, [breakdown])

  function applyDistribution() {
    const nextLive = Number(liveCap)
    const nextBackfill = Number(backfillCap)
    const nextEval = Number(evalCap)
    const quotaText = providerQuota.trim()
    const nextProviderQuota = quotaText ? Number(quotaText) : null

    if (!Number.isInteger(nextLive) || nextLive < 1) {
      setFormError('Live cap must be an integer >= 1.')
      return
    }
    if (!Number.isInteger(nextBackfill) || nextBackfill < 1) {
      setFormError('Backfill cap must be an integer >= 1.')
      return
    }
    if (!Number.isInteger(nextEval) || nextEval < 1) {
      setFormError('Eval cap must be an integer >= 1.')
      return
    }
    if (nextProviderQuota !== null && (!Number.isInteger(nextProviderQuota) || nextProviderQuota < 1)) {
      setFormError('Provider quota must be blank or an integer >= 1.')
      return
    }
    const total = nextLive + nextBackfill + nextEval
    if (nextProviderQuota !== null && total > nextProviderQuota) {
      setFormError(`Allocated caps (${total}) exceed provider quota (${nextProviderQuota}).`)
      return
    }

    setFormError(null)
    updateDistributionMutation.mutate({
      live_cap: nextLive,
      backfill_cap: nextBackfill,
      eval_cap: nextEval,
      provider_quota: nextProviderQuota,
    })
  }

  return (
    <section className="migration-section">
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">x + y + z + w = total RPM quota</p>
          <h2>Real-time RPM breakdown{breakdown ? ` -- ${breakdown.model}` : ''}</h2>
        </div>
        <div className="toolbar-actions">
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={() => rateLimitsQuery.refetch()}
            disabled={rateLimitsQuery.isFetching}
          >
            <FiRefreshCw aria-hidden="true" className={rateLimitsQuery.isFetching ? 'button-icon spin' : 'button-icon'} />
            Refresh
          </button>
        </div>
      </div>
      {rateLimitsQuery.error && <div className="banner banner-error">{rateLimitsQuery.error.message}</div>}
      {formError && <div className="banner banner-error">{formError}</div>}
      {updateDistributionMutation.error && <div className="banner banner-error">{updateDistributionMutation.error.message}</div>}
      {updateDistributionMutation.isSuccess && (
        <div className="banner banner-info">RPM distribution updated. New caps apply immediately.</div>
      )}

      <div className="migration-subsection">
        <div className="migration-subsection-header">
          <h3>Edit RPM distribution</h3>
        </div>
        <div className="rpm-config-grid">
          <label className="field">
            <span>Live cap (x)</span>
            <input
              className="search-input min-score-input"
              type="number"
              min={1}
              value={liveCap}
              onChange={(event) => setLiveCap(event.target.value)}
              placeholder="Live"
            />
          </label>
          <label className="field">
            <span>Backfill cap (y)</span>
            <input
              className="search-input min-score-input"
              type="number"
              min={1}
              value={backfillCap}
              onChange={(event) => setBackfillCap(event.target.value)}
              placeholder="Backfill"
            />
          </label>
          <label className="field">
            <span>Eval cap (z)</span>
            <input
              className="search-input min-score-input"
              type="number"
              min={1}
              value={evalCap}
              onChange={(event) => setEvalCap(event.target.value)}
              placeholder="Eval"
            />
          </label>
          <label className="field">
            <span>Provider quota (w source)</span>
            <input
              className="search-input"
              type="number"
              min={1}
              value={providerQuota}
              onChange={(event) => setProviderQuota(event.target.value)}
              placeholder="Optional"
            />
          </label>
        </div>
        <div className="toolbar-actions">
          <button
            type="button"
            className="primary-button ghost-button-with-icon"
            onClick={applyDistribution}
            disabled={updateDistributionMutation.isPending}
          >
            <FiZap aria-hidden="true" className="button-icon" />
            {updateDistributionMutation.isPending ? 'Saving...' : 'Apply RPM split'}
          </button>
        </div>
        <p className="match-detail-hint">
          Provider quota is the real total RPM limit from your model provider console. It is used only to compute
          headroom (w = quota - x - y - z). Leaving it blank keeps headroom as unknown.
        </p>
      </div>

      {breakdown && (
        <>
          <div className="summary-grid rpm-grid">
            {breakdown.buckets.map((bucket) => {
              const percent = usagePercent(bucket.count, bucket.cap)
              return (
                <article key={bucket.bucket} className="summary-card rpm-bucket-card">
                  <span>{BUCKET_LABEL[bucket.bucket] ?? bucket.bucket}</span>
                  <strong>
                    {bucket.count} / {bucket.cap} rpm
                  </strong>
                  <div className="rpm-bar">
                    <div className={`rpm-bar-fill rpm-bar-${percent >= 90 ? 'high' : percent >= 60 ? 'mid' : 'low'}`} style={{ width: `${percent}%` }} />
                  </div>
                  <span className="match-detail-hint">{bucket.remaining} remaining this window</span>
                </article>
              )
            })}
            <article className="summary-card rpm-bucket-card">
              <span>Headroom (w)</span>
              <strong>{breakdown.headroom !== null ? `${breakdown.headroom} rpm` : 'unknown'}</strong>
              <span className="match-detail-hint">
                {breakdown.provider_quota !== null
                  ? `${breakdown.total_allocated} allocated of ${breakdown.provider_quota} quota`
                  : 'Set PROVIDER_RPM_QUOTA from the provider console to compute this'}
              </span>
            </article>
          </div>
          <p className="match-detail-hint">
            Read-only peek at each bucket's current sliding window ({breakdown.window_seconds}s) -- polling this
            never itself consumes budget. "backfill" (y) is what a running rescore process draws from; it never
            shares a counter with "live" (x) or "eval" (z).
          </p>
        </>
      )}
    </section>
  )
}

export default function MigrationPage() {
  return (
    <main className="app-body app-body-single">
      <FeatureFlagSection />
      <HandoffObservabilitySection />
      <RpmBreakdownSection />
    </main>
  )
}
