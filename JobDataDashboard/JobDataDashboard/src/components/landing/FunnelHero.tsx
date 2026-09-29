import { useState, useSyncExternalStore } from 'react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import type { PipelineFunnel } from '../../types'
import { sourceLabel } from '../AlluvialChart'
import FunnelCanvas from './FunnelCanvas'
import type { FunnelHighlight } from './FunnelCanvas'
import { BUCKETS, FUNNEL_GEOMETRY } from './funnelGeometry'
import type { FunnelOrientation } from './funnelGeometry'

// Below this width the funnel flows top-to-bottom -- sources on top, buckets the particles fall
// into at the bottom -- instead of left-to-right.
const VERTICAL_QUERY = '(max-width: 959px)'

function subscribeToVerticalQuery(onChange: () => void) {
  const query = window.matchMedia(VERTICAL_QUERY)
  query.addEventListener('change', onChange)
  return () => query.removeEventListener('change', onChange)
}

function useOrientation(): FunnelOrientation {
  const isVertical = useSyncExternalStore(subscribeToVerticalQuery, () => window.matchMedia(VERTICAL_QUERY).matches)
  return isVertical ? 'vertical' : 'horizontal'
}

// Same order as FUNNEL_GEOMETRY's lanes.
const SOURCES = ['ycombinator', 'greenhouse', 'ashby', 'lever']

function bucketCountsOf(funnel: PipelineFunnel | undefined) {
  return funnel ? [funnel.good_matches, funnel.moderate_matches, funnel.bad_matches, funnel.failed_matches] : null
}

type FunnelHeroProps = {
  funnel: PipelineFunnel | undefined
  lensCaption: string
  onBucketClick: (bucketId: string) => void
}

export default function FunnelHero({ funnel, lensCaption, onBucketClick }: FunnelHeroProps) {
  const orientation = useOrientation()
  const [highlight, setHighlight] = useState<FunnelHighlight>(null)
  const geometry = FUNNEL_GEOMETRY[orientation]
  const isHorizontal = orientation === 'horizontal'
  const bucketCounts = bucketCountsOf(funnel)
  // Horizontal only: each overlay sits on its lane, as a percentage of the design height.
  const laneStyle = (index: number): CSSProperties | undefined =>
    isHorizontal ? { top: `${(geometry.lanes[index] / geometry.height) * 100}%` } : undefined
  const isHighlighted = (side: 'source' | 'bucket', index: number) => highlight?.side === side && highlight.index === index

  return (
    <div className={`funnel-hero is-${orientation}`} style={{ aspectRatio: `${geometry.width} / ${geometry.height}` }}>
      <FunnelCanvas orientation={orientation} highlight={highlight} lensCaption={lensCaption} bucketCounts={bucketCounts} />

      <div className="funnel-sources" onMouseLeave={() => setHighlight(null)}>
        {SOURCES.map((source, index) => (
          <button
            key={source}
            type="button"
            className={`funnel-source${isHighlighted('source', index) ? ' is-active' : ''}`}
            style={laneStyle(index)}
            aria-pressed={isHighlighted('source', index)}
            onMouseEnter={() => setHighlight({ side: 'source', index })}
            onFocus={() => setHighlight({ side: 'source', index })}
            onBlur={() => setHighlight(null)}
            onClick={() => setHighlight(isHighlighted('source', index) ? null : { side: 'source', index })}
          >
            <span className="funnel-dot" aria-hidden="true" />
            {sourceLabel(source)}
          </button>
        ))}
      </div>

      <div className="funnel-buckets" onMouseLeave={() => setHighlight(null)}>
        {BUCKETS.map((bucket, index) => (
          <Link
            key={bucket.id}
            to="/etl-data/matches"
            className={`funnel-bucket${isHighlighted('bucket', index) ? ' is-active' : ''}`}
            style={{ ...laneStyle(index), '--bucket-color': bucket.color } as CSSProperties}
            onMouseEnter={() => setHighlight({ side: 'bucket', index })}
            onFocus={() => setHighlight({ side: 'bucket', index })}
            onBlur={() => setHighlight(null)}
            onClick={() => onBucketClick(bucket.id)}
          >
            <span className="funnel-bucket-head">
              <span className="funnel-dot" aria-hidden="true" />
              <span className="funnel-bucket-label is-long">{bucket.label}</span>
              <span className="funnel-bucket-label is-short">{bucket.shortLabel}</span>
            </span>
            <span className="funnel-bucket-count">{bucketCounts ? bucketCounts[index].toLocaleString() : '—'}</span>
            <span className="funnel-bucket-range">{bucket.range}</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
