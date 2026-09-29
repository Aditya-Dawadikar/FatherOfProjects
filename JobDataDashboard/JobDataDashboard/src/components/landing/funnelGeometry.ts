// Layout of the landing page's funnel graphic (FunnelCanvas), in a fixed design coordinate space
// per orientation that's scaled to the element's width -- shared with FunnelHero so its HTML
// overlays (lane buttons, match cards) can be positioned with the same numbers as percentages.

export type FunnelOrientation = 'horizontal' | 'vertical'

type Geometry = {
  width: number
  height: number
  // "along" is the flow axis (x when horizontal, y when vertical), "across" the lane axis.
  lanes: number[]
  alongStart: number
  alongLength: number
  squeezeStart: number
  squeezeLength: number
  center: number
  jitter: number
  gates: number[]
  lensAlong: number
  lensRadius: number
  slots: number[]
  matchEnd: number
  count: number
}

export const FUNNEL_GEOMETRY: Record<FunnelOrientation, Geometry> = {
  horizontal: {
    width: 1440,
    height: 540,
    lanes: [70, 200, 340, 470],
    alongStart: 200,
    alongLength: 860,
    squeezeStart: 220,
    squeezeLength: 560,
    center: 270,
    jitter: 70,
    gates: [420, 530, 640],
    lensAlong: 860,
    lensRadius: 86,
    slots: [155, 227, 299, 371, 443],
    matchEnd: 1040,
    count: 260,
  },
  vertical: {
    width: 390,
    height: 600,
    lanes: [57, 146, 244, 333],
    alongStart: 40,
    alongLength: 420,
    squeezeStart: 60,
    squeezeLength: 230,
    center: 195,
    jitter: 40,
    gates: [110, 160, 210],
    lensAlong: 300,
    lensRadius: 52,
    slots: [80, 195, 310],
    matchEnd: 440,
    count: 150,
  },
}
