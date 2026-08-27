import { useEffect, useState } from 'react'
import { FiRefreshCw, FiZap } from 'react-icons/fi'
import { useRateLimits, useUpdateRateLimitsDistribution } from '../../hooks'
import { BUCKET_LABEL, usagePercent } from './adminUtils'

export default function RateLimitsTab() {
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
