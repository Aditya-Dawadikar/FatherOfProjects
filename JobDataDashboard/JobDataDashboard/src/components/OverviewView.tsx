import AlluvialChart from './AlluvialChart'
import { usePipelineFunnel } from '../hooks'

const LEGEND_ITEMS = [
  { key: 'total', label: 'Scraped / processed', swatchClass: 'legend-swatch-total' },
  { key: 'pending', label: 'Not yet processed', swatchClass: 'legend-swatch-pending' },
  { key: 'good', label: 'Good match', swatchClass: 'legend-swatch-good' },
  { key: 'moderate', label: 'Moderate match', swatchClass: 'legend-swatch-moderate' },
  { key: 'bad', label: 'Bad match', swatchClass: 'legend-swatch-bad' },
  { key: 'failed', label: 'Failed (not found)', swatchClass: 'legend-swatch-failed' },
]

export default function OverviewView() {
  const funnelQuery = usePipelineFunnel()
  const funnel = funnelQuery.data

  return (
    <section className="content-panel">
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Scrape &rarr; agent &rarr; match quality</p>
          <h2>{funnelQuery.isLoading ? 'Loading pipeline...' : 'Pipeline overview'}</h2>
        </div>
        <div className="toolbar-actions">
          <button
            type="button"
            className="ghost-button"
            onClick={() => funnelQuery.refetch()}
            disabled={funnelQuery.isFetching}
          >
            {funnelQuery.isFetching ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {funnel && (
        <div className="summary-grid">
          <article className="summary-card">
            <span>Scraped</span>
            <strong>{funnel.total_scraped}</strong>
          </article>
          <article className="summary-card">
            <span>Processed by agent</span>
            <strong>{funnel.total_processed}</strong>
          </article>
          <article className="summary-card">
            <span>Good matches</span>
            <strong>{funnel.good_matches}</strong>
          </article>
          <article className="summary-card">
            <span>Moderate / bad</span>
            <strong>{funnel.moderate_matches} / {funnel.bad_matches}</strong>
          </article>
          <article className="summary-card">
            <span>Failed (not found)</span>
            <strong>{funnel.failed_matches}</strong>
          </article>
        </div>
      )}

      {funnelQuery.error && <div className="banner banner-error">{funnelQuery.error.message}</div>}

      {funnel && (
        <>
          <AlluvialChart funnel={funnel} />
          <div className="alluvial-legend">
            {LEGEND_ITEMS.map((item) => (
              <div key={item.key} className="legend-item">
                <span className={`legend-swatch ${item.swatchClass}`} />
                {item.label}
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
