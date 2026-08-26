import { FiRefreshCw } from 'react-icons/fi'
import AlluvialChart, { sourceColor, sourceLabel } from '../AlluvialChart'
import { usePipelineFunnel } from '../../hooks'

const LEGEND_ITEMS = [
  { key: 'processed', label: 'Processed by Agent', swatchClass: 'legend-swatch-processed' },
  { key: 'pending', label: 'Not yet processed', swatchClass: 'legend-swatch-pending' },
  { key: 'good', label: 'Good match', swatchClass: 'legend-swatch-good' },
  { key: 'moderate', label: 'Moderate match', swatchClass: 'legend-swatch-moderate' },
  { key: 'bad', label: 'Bad match', swatchClass: 'legend-swatch-bad' },
  { key: 'failed', label: 'Failed (not found)', swatchClass: 'legend-swatch-failed' },
]

export default function OverviewDataOverviewTab() {
  const funnelQuery = usePipelineFunnel()
  const funnel = funnelQuery.data

  return (
    <div className="overview-tab-panel" role="tabpanel" aria-label="Data Overview">
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Scrape &rarr; agent &rarr; match quality</p>
          <h2>{funnelQuery.isLoading ? 'Loading Data Overview...' : 'Processed Data Distribution'}</h2>
        </div>
        <div className="toolbar-actions">
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={() => funnelQuery.refetch()}
            disabled={funnelQuery.isFetching}
          >
            <FiRefreshCw
              aria-hidden="true"
              className={funnelQuery.isFetching ? 'button-icon spin' : 'button-icon'}
            />
            {funnelQuery.isFetching ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* {funnel && (
        <div className="summary-grid">
          <article className="summary-card">
            <span>Jobs Scraped</span>
            <strong>{funnel.total_scraped}</strong>
          </article>
          <article className="summary-card">
            <span>Processed by Agent</span>
            <strong>{funnel.total_processed}</strong>
          </article>
          <article className="summary-card">
            <span>Good Matches</span>
            <strong>{funnel.good_matches}</strong>
          </article>
          <article className="summary-card">
            <span>Moderate Matches</span>
            <strong>{funnel.moderate_matches}</strong>
          </article>
          <article className="summary-card">
            <span>Bad Matches</span>
            <strong>{funnel.bad_matches}</strong>
          </article>
          <article className="summary-card">
            <span>Agent Failed (Job Not Found)</span>
            <strong>{funnel.failed_matches}</strong>
          </article>
        </div>
      )} */}

      {funnelQuery.error && <div className="banner banner-error">{funnelQuery.error.message}</div>}

      {funnel && (
        <>
          <AlluvialChart funnel={funnel} />
          <div className="alluvial-legend">
            {funnel.by_source
              .filter((slice) => slice.total_scraped > 0)
              .map((slice) => (
                <div key={slice.source} className="legend-item">
                  <span className="legend-swatch" style={{ background: sourceColor(slice.source) }} />
                  {sourceLabel(slice.source)} (scraped)
                </div>
              ))}
            {LEGEND_ITEMS.map((item) => (
              <div key={item.key} className="legend-item">
                <span className={`legend-swatch ${item.swatchClass}`} />
                {item.label}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
