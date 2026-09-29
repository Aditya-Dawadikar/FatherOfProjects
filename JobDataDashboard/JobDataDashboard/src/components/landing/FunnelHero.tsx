import { useState, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import type { MatchedJobRecord } from '../../types'
import { sourceLabel } from '../AlluvialChart'
import FunnelCanvas from './FunnelCanvas'
import { FUNNEL_GEOMETRY } from './funnelGeometry'
import type { FunnelOrientation } from './funnelGeometry'

// Below this width the funnel flows top-to-bottom instead of left-to-right -- the horizontal
// layout's lane buttons and match cards get too cramped to read.
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

type FunnelHeroProps = {
  topMatches: MatchedJobRecord[] | null
  lensCaption: string
  onMatchClick: () => void
}

export default function FunnelHero({ topMatches, lensCaption, onMatchClick }: FunnelHeroProps) {
  const orientation = useOrientation()
  const [highlightedLane, setHighlightedLane] = useState<number | null>(null)
  const geometry = FUNNEL_GEOMETRY[orientation]
  const isHorizontal = orientation === 'horizontal'
  const cardCount = geometry.slots.length
  const cards = topMatches?.slice(0, cardCount) ?? null

  return (
    <div className={`funnel-hero is-${orientation}`} style={{ aspectRatio: `${geometry.width} / ${geometry.height}` }}>
      <FunnelCanvas orientation={orientation} highlightedLane={highlightedLane} lensCaption={lensCaption} />

      <div className="funnel-lanes" onMouseLeave={() => setHighlightedLane(null)}>
        {SOURCES.map((source, index) => (
          <button
            key={source}
            type="button"
            className={`funnel-lane${highlightedLane === index ? ' is-active' : ''}`}
            style={isHorizontal ? { top: `${(geometry.lanes[index] / geometry.height) * 100}%` } : undefined}
            aria-pressed={highlightedLane === index}
            onMouseEnter={() => setHighlightedLane(index)}
            onFocus={() => setHighlightedLane(index)}
            onBlur={() => setHighlightedLane(null)}
            onClick={() => setHighlightedLane((current) => (current === index ? null : index))}
          >
            <span className="funnel-lane-dot" aria-hidden="true" />
            {sourceLabel(source)}
          </button>
        ))}
      </div>

      <div className="funnel-matches">
        <div
          className="funnel-matches-label"
          style={isHorizontal ? { top: `${((geometry.slots[0] - 48) / geometry.height) * 100}%` } : undefined}
        >
          Top live matches
        </div>
        {cards && cards.length === 0 && <div className="funnel-matches-empty">No scored matches yet.</div>}
        {Array.from({ length: cards ? cards.length : cardCount }, (_, index) => {
          const match = cards?.[index]
          const style = isHorizontal ? { top: `${(geometry.slots[index] / geometry.height) * 100}%` } : undefined
          if (!match) {
            return <div key={index} className="funnel-match is-loading" style={style} aria-hidden="true" />
          }
          return (
            <Link key={match.id} to="/etl-data/matches" className="funnel-match" style={style} onClick={onMatchClick}>
              <span className="funnel-match-rank">{index + 1}</span>
              <span className="funnel-match-body">
                <span className="funnel-match-top">
                  <span className="funnel-match-role">{match.job_role}</span>
                  <span className="funnel-match-score">{match.match_score}</span>
                </span>
                <span className="funnel-match-meta">
                  {match.company_name} · {sourceLabel(match.source)}
                </span>
                <span className="funnel-match-bar">
                  <span style={{ width: `${Math.max(0, Math.min(100, match.match_score))}%` }} />
                </span>
              </span>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
