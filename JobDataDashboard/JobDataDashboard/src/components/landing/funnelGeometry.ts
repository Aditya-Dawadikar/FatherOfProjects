// Layout of the landing page's funnel graphic (FunnelCanvas), in a fixed design coordinate space
// per orientation that's scaled to the element's width -- shared with FunnelHero so its HTML
// overlays (source buttons, score buckets) can be positioned with the same numbers as percentages.
//
// The layout is symmetric around the agent: sources on one side (left, or top on phones), the four
// score buckets mirrored on the other (right, or bottom), and the agent's lens exactly halfway.

export type FunnelOrientation = 'horizontal' | 'vertical'

type Geometry = {
  width: number
  height: number
  // "along" is the flow axis (x when horizontal, y when vertical), "across" the lane axis.
  // Source lanes and bucket lanes share these positions -- that's what makes it mirror.
  lanes: number[]
  alongStart: number
  alongEnd: number
  gates: number[]
  lensAlong: number
  lensRadius: number
  center: number
  // Where particles converge from their source lanes into the lens...
  squeezeStart: number
  squeezeEnd: number
  // ...and where they fan back out from it to their bucket.
  spreadStart: number
  spreadEnd: number
  jitter: number
  count: number
}

export const FUNNEL_GEOMETRY: Record<FunnelOrientation, Geometry> = {
  horizontal: {
    width: 1440,
    height: 540,
    lanes: [70, 200, 340, 470],
    alongStart: 200,
    alongEnd: 1240,
    gates: [330, 420, 510],
    lensAlong: 720,
    lensRadius: 86,
    center: 270,
    squeezeStart: 220,
    squeezeEnd: 620,
    spreadStart: 820,
    spreadEnd: 1180,
    jitter: 70,
    count: 280,
  },
  vertical: {
    width: 390,
    height: 660,
    lanes: [57, 146, 244, 333],
    alongStart: 44,
    alongEnd: 556,
    gates: [110, 150, 190],
    lensAlong: 300,
    lensRadius: 52,
    center: 195,
    squeezeStart: 60,
    squeezeEnd: 250,
    spreadStart: 360,
    spreadEnd: 520,
    jitter: 40,
    count: 180,
  },
}

// The four outcomes of scoring, in bucket-lane order -- same thresholds and not-found rule
// JobDataServer's /matches/funnel counts them by (see _GOOD_MATCH_MIN_SCORE / _MODERATE_MATCH_MIN_SCORE
// in JobDataServer/main.py).
export const BUCKETS = [
  { id: 'high', label: 'High alignment', shortLabel: 'High', range: 'score 70+', color: '#FF9B7A' },
  { id: 'medium', label: 'Medium', shortLabel: 'Medium', range: 'score 40–69', color: '#FFD6C7' },
  { id: 'low', label: 'Low', shortLabel: 'Low', range: 'score < 40', color: '#8C8BA8' },
  { id: 'gone', label: 'Posting gone', shortLabel: 'Gone', range: '404 at crawl', color: '#565A80' },
] as const
