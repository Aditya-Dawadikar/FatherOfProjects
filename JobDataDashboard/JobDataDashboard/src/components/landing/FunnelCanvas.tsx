import { useEffect, useRef } from 'react'
import { FUNNEL_GEOMETRY } from './funnelGeometry'
import type { FunnelOrientation } from './funnelGeometry'

// The landing page's hero graphic: postings stream in from the four job boards, most get dropped
// at WebScraper's filter gates, the survivors pass through the scoring agent, and a few come out
// as ranked matches. Purely illustrative (particles aren't real jobs -- the counts and match cards
// around it are the live data). Drawn on a <canvas> rather than as SVG/React elements because it's
// a few hundred moving particles redrawn every frame.

const GATE_LABELS = ['recent', 'eng title', 'per-source cap']

const COLORS = {
  accent: '#A9B3FF',
  coral: '#FF9B7A',
  dropped: '#4A4D6E',
  lane: '#1E2140',
  gate: '#3B3F66',
  gateLabel: '#7D7C98',
  lensFill: '#0D0F22',
  text: '#ECEBF5',
  caption: '#7D7C98',
}

// Timestamp used for the single still frame drawn under prefers-reduced-motion -- far enough in
// that the particles are spread along the whole funnel rather than bunched at the start.
const STILL_FRAME_SECONDS = 20

function hash(i: number, k: number) {
  const v = Math.sin(i * 12.9898 + k * 78.233) * 43758.5453
  return v - Math.floor(v)
}

function clamp01(v: number) {
  return Math.max(0, Math.min(1, v))
}

function smooth(v: number) {
  return v * v * (3 - 2 * v)
}

type DrawOptions = {
  orientation: FunnelOrientation
  t: number
  highlightedLane: number | null
  lensCaption: string
}

function drawFrame(ctx: CanvasRenderingContext2D, { orientation, t, highlightedLane, lensCaption }: DrawOptions) {
  const g = FUNNEL_GEOMETRY[orientation]
  const horizontal = orientation === 'horizontal'
  // Maps (along, across) design coords to canvas (x, y).
  const point = (along: number, across: number): [number, number] => (horizontal ? [along, across] : [across, along])

  ctx.clearRect(0, 0, g.width, g.height)

  // Lane guides from each source into the first gate.
  ctx.strokeStyle = COLORS.lane
  ctx.lineWidth = 1
  for (const lane of g.lanes) {
    ctx.beginPath()
    ctx.moveTo(...point(g.alongStart, lane))
    ctx.lineTo(...point(g.gates[0], lane))
    ctx.stroke()
  }

  // Filter gates.
  ctx.setLineDash([3, 6])
  ctx.strokeStyle = COLORS.gate
  ctx.fillStyle = COLORS.gateLabel
  ctx.font = "11px 'JetBrains Mono', ui-monospace, monospace"
  g.gates.forEach((gate, index) => {
    ctx.beginPath()
    if (horizontal) {
      ctx.moveTo(gate, 40)
      ctx.lineTo(gate, g.height - 40)
    } else {
      ctx.moveTo(16, gate)
      ctx.lineTo(g.width - 16, gate)
    }
    ctx.stroke()
    ctx.textAlign = horizontal ? 'center' : 'right'
    if (horizontal) {
      ctx.fillText(GATE_LABELS[index], gate, 28)
    } else {
      ctx.fillText(GATE_LABELS[index], g.width - 16, gate - 6)
    }
  })
  ctx.setLineDash([])

  // The agent "lens": soft glow, solid rim, two counter-rotating dashed rings.
  const [lx, ly] = point(g.lensAlong, g.center)
  const r = g.lensRadius
  ctx.fillStyle = COLORS.accent
  ctx.globalAlpha = 0.035
  ctx.beginPath()
  ctx.arc(lx, ly, r * 1.5, 0, Math.PI * 2)
  ctx.fill()
  ctx.globalAlpha = 0.05
  ctx.beginPath()
  ctx.arc(lx, ly, r * 1.2, 0, Math.PI * 2)
  ctx.fill()
  ctx.globalAlpha = 1
  ctx.fillStyle = COLORS.lensFill
  ctx.strokeStyle = COLORS.accent
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.arc(lx, ly, r, 0, Math.PI * 2)
  ctx.fill()
  ctx.stroke()

  const dash = (t * 30) % 1000
  ctx.lineWidth = 1
  ctx.globalAlpha = 0.7
  ctx.setLineDash([2, 8])
  ctx.lineDashOffset = -dash
  ctx.beginPath()
  ctx.arc(lx, ly, r * 0.84, 0, Math.PI * 2)
  ctx.stroke()
  ctx.globalAlpha = 0.5
  ctx.strokeStyle = COLORS.coral
  ctx.setLineDash([14, 10])
  ctx.lineDashOffset = dash * 0.7
  ctx.beginPath()
  ctx.arc(lx, ly, r * 0.67, 0, Math.PI * 2)
  ctx.stroke()
  ctx.setLineDash([])
  ctx.lineDashOffset = 0
  ctx.globalAlpha = 1

  // Particles.
  const matchTravel = g.matchEnd - g.lensAlong
  for (let i = 0; i < g.count; i++) {
    const lane = i % 4
    const u = (hash(i, 1) + t * (0.045 + hash(i, 2) * 0.04)) % 1
    const along = g.alongStart + u * g.alongLength
    const squeeze = smooth(clamp01((along - g.squeezeStart) / g.squeezeLength))
    let across = g.lanes[lane] + (g.center - g.lanes[lane]) * squeeze + (hash(i, 3) - 0.5) * g.jitter * (1 - squeeze * 0.9)
    let alpha = 0.85
    let color = COLORS.accent
    let radius = 1.4 + hash(i, 7) * 1.6

    // ~40% survive the three gates; of those, ~45% come out of the agent as matches.
    const fate = hash(i, 4)
    const droppedAt = fate < 0.3 ? 0 : fate < 0.5 ? 1 : fate < 0.6 ? 2 : -1
    if (droppedAt >= 0 && along > g.gates[droppedAt]) {
      const d = along - g.gates[droppedAt]
      across += horizontal ? d * d * 0.03 : (lane < 2 ? -1 : 1) * d * d * 0.03
      alpha = Math.max(0, 0.7 - d / 60)
      color = COLORS.dropped
    } else if (along > g.lensAlong) {
      if (hash(i, 5) > 0.55) {
        const k = smooth(clamp01((along - g.lensAlong) / matchTravel))
        across = g.center + (g.slots[Math.floor(hash(i, 6) * g.slots.length)] - g.center) * k
        color = COLORS.coral
        radius = 3
        alpha = along > g.matchEnd ? Math.max(0, 1 - (along - g.matchEnd) / 20) : 1
      } else {
        color = COLORS.dropped
        alpha = Math.max(0, 0.6 - (along - g.lensAlong) / (matchTravel * 0.45))
      }
    }
    if (highlightedLane !== null && lane !== highlightedLane) {
      alpha *= 0.12
    }
    if (alpha <= 0.01) {
      continue
    }
    const [x, y] = point(along, across)
    // Hidden while inside the lens, so particles read as passing through the agent rather than
    // piling up on top of its label.
    if (Math.hypot(x - lx, y - ly) < r - 4) {
      continue
    }
    ctx.globalAlpha = alpha
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.arc(x, y, radius, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.globalAlpha = 1

  // Lens label, drawn last so particles pass behind it.
  ctx.textAlign = 'center'
  ctx.fillStyle = COLORS.text
  ctx.font = `700 ${horizontal ? 17 : 13}px 'Bricolage Grotesque', system-ui, sans-serif`
  ctx.fillText('ReAct agent', lx, ly + (horizontal ? -4 : 4))
  if (horizontal) {
    ctx.fillStyle = COLORS.caption
    ctx.font = "11px 'JetBrains Mono', ui-monospace, monospace"
    ctx.fillText(lensCaption, lx, ly + 16)
  }
}

type FunnelCanvasProps = {
  orientation: FunnelOrientation
  highlightedLane: number | null
  lensCaption: string
}

export default function FunnelCanvas({ orientation, highlightedLane, lensCaption }: FunnelCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  // Read by the animation loop every frame -- kept in refs so hovering a lane doesn't tear down
  // and restart the loop.
  const highlightedLaneRef = useRef(highlightedLane)
  const lensCaptionRef = useRef(lensCaption)

  useEffect(() => {
    highlightedLaneRef.current = highlightedLane
    lensCaptionRef.current = lensCaption
  }, [highlightedLane, lensCaption])

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) {
      return
    }
    const g = FUNNEL_GEOMETRY[orientation]
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let frame = 0
    let isVisible = true
    const startedAt = performance.now()

    const draw = (seconds: number) =>
      drawFrame(ctx, { orientation, t: seconds, highlightedLane: highlightedLaneRef.current, lensCaption: lensCaptionRef.current })

    const resize = () => {
      const dpr = window.devicePixelRatio || 1
      const cssWidth = canvas.clientWidth
      const scale = cssWidth / g.width
      canvas.width = Math.round(cssWidth * dpr)
      canvas.height = Math.round(g.height * scale * dpr)
      ctx.setTransform(dpr * scale, 0, 0, dpr * scale, 0, 0)
      if (reducedMotion) {
        draw(STILL_FRAME_SECONDS)
      }
    }

    const tick = () => {
      frame = 0
      if (!isVisible || document.hidden) {
        return
      }
      draw((performance.now() - startedAt) / 1000)
      frame = requestAnimationFrame(tick)
    }

    const start = () => {
      if (!reducedMotion && !frame) {
        frame = requestAnimationFrame(tick)
      }
    }

    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(canvas)
    resize()

    // Stop drawing while scrolled out of view or in a background tab.
    const intersectionObserver = new IntersectionObserver(([entry]) => {
      isVisible = entry.isIntersecting
      if (isVisible) {
        start()
      }
    })
    intersectionObserver.observe(canvas)
    const onVisibilityChange = () => start()
    document.addEventListener('visibilitychange', onVisibilityChange)
    start()

    return () => {
      cancelAnimationFrame(frame)
      resizeObserver.disconnect()
      intersectionObserver.disconnect()
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [orientation])

  return <canvas ref={canvasRef} className="funnel-canvas" aria-hidden="true" />
}
