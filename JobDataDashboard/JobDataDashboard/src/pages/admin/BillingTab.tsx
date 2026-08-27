import { FiRefreshCw, FiRotateCcw } from 'react-icons/fi'
import { useBillingStatus, useResetBillingStatus } from '../../hooks'
import { formatDateTime } from './adminUtils'

export default function BillingTab() {
  const billingStatusQuery = useBillingStatus()
  const resetMutation = useResetBillingStatus()
  const status = billingStatusQuery.data

  return (
    <section className="migration-section">
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Gemini billing</p>
          <h2>Billing status</h2>
        </div>
        <div className="toolbar-actions">
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={() => billingStatusQuery.refetch()}
            disabled={billingStatusQuery.isFetching}
          >
            <FiRefreshCw aria-hidden="true" className={billingStatusQuery.isFetching ? 'button-icon spin' : 'button-icon'} />
            Refresh
          </button>
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={() => resetMutation.mutate()}
            disabled={resetMutation.isPending}
          >
            <FiRotateCcw aria-hidden="true" className="button-icon" />
            {resetMutation.isPending ? 'Resetting...' : 'Clear alert'}
          </button>
        </div>
      </div>

      {billingStatusQuery.error && <div className="banner banner-error">{billingStatusQuery.error.message}</div>}
      {resetMutation.error && <div className="banner banner-error">{resetMutation.error.message}</div>}

      {status?.is_billing_exhausted ? (
        <div className="banner banner-error">
          <strong>Billing exhausted</strong> -- Gemini rejected the last call with a prepaid-credits-depleted
          error{status.billing_exhausted_at ? ` at ${formatDateTime(status.billing_exhausted_at)}` : ''}. Every
          live and backfill scoring call will keep failing the same way until credits are topped up.
          {status.billing_exhausted_message ? ` "${status.billing_exhausted_message}"` : ''} Click "Clear alert"
          once resolved.
        </div>
      ) : (
        status && <div className="banner banner-info">No billing exhaustion detected.</div>
      )}
      <p className="match-detail-hint">
        Reflects what Gemini actually returned on the last call (a 429 identified as prepaid-credits-depleted,
        distinct from an ordinary rate limit) -- not a live query against Google's billing API, which doesn't
        expose one. Clears only via "Clear alert".
      </p>
    </section>
  )
}
