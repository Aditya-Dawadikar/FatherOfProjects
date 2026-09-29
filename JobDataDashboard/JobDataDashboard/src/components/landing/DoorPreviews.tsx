import type { ReactNode } from 'react'

// Miniature wireframes of each dashboard section for the landing page's "Pick a door" cards --
// a stylized sketch of what's behind the door (graph, charts, table, controls), not a screenshot
// and not real data. Colors and hover motion come from the .dp-* rules in LandingPage.css.

const VIEW = '0 0 320 170'

function Window({ children }: { children: ReactNode }) {
  return (
    <svg className="dp" viewBox={VIEW} aria-hidden="true">
      <rect className="dp-window" x="1" y="1" width="318" height="168" rx="10" />
      <line className="dp-rule" x1="1" y1="22" x2="319" y2="22" />
      <circle className="dp-light" cx="14" cy="12" r="3" />
      <circle className="dp-light" cx="24" cy="12" r="3" />
      <circle className="dp-light" cx="34" cy="12" r="3" />
      {children}
    </svg>
  )
}

const GRAPH_NODES = [
  { x: 160, y: 96, r: 14, core: true },
  { x: 74, y: 58, r: 8 },
  { x: 82, y: 136, r: 8 },
  { x: 246, y: 56, r: 8 },
  { x: 252, y: 132, r: 8 },
  { x: 160, y: 42, r: 7 },
]

export function OverviewPreview() {
  const [core, ...tools] = GRAPH_NODES
  return (
    <Window>
      {tools.map((node, index) => (
        <line key={`edge-${index}`} className="dp-edge" x1={core.x} y1={core.y} x2={node.x} y2={node.y} style={{ animationDelay: `${index * 0.4}s` }} />
      ))}
      {tools.map((node, index) => (
        <circle key={`node-${index}`} className="dp-node" cx={node.x} cy={node.y} r={node.r} />
      ))}
      <circle className="dp-core-halo" cx={core.x} cy={core.y} r={core.r + 10} />
      <circle className="dp-core" cx={core.x} cy={core.y} r={core.r} />
    </Window>
  )
}

export function ObservabilityPreview() {
  return (
    <Window>
      <rect className="dp-tile" x="14" y="34" width="140" height="58" rx="6" />
      <rect className="dp-tile" x="166" y="34" width="140" height="58" rx="6" />
      <path className="dp-spark" d="M24 80 L44 72 L64 76 L84 60 L104 66 L124 50 L144 54" />
      <path className="dp-spark is-coral" d="M176 64 L196 70 L216 58 L236 66 L256 52 L276 60 L296 48" />
      <rect className="dp-tile" x="14" y="102" width="292" height="56" rx="6" />
      <path className="dp-area" d="M24 146 L60 136 L96 140 L132 124 L168 130 L204 114 L240 120 L276 106 L296 110 V150 H24 Z" />
      <path className="dp-spark" d="M24 146 L60 136 L96 140 L132 124 L168 130 L204 114 L240 120 L276 106 L296 110" />
    </Window>
  )
}

const EVAL_PAIRS = [
  [58, 70],
  [44, 62],
  [66, 64],
  [50, 74],
]

export function EvalsPreview() {
  return (
    <Window>
      {[0, 1, 2].map((index) => (
        <g key={index}>
          <rect className="dp-tile" x={14 + index * 100} y="32" width="92" height="36" rx="6" />
          <rect className={index === 1 ? 'dp-fill is-coral' : 'dp-fill'} x={24 + index * 100} y="42" width="40" height="6" rx="3" />
          <rect className="dp-muted" x={24 + index * 100} y="54" width="60" height="4" rx="2" />
        </g>
      ))}
      <line className="dp-rule" x1="14" y1="158" x2="306" y2="158" />
      {EVAL_PAIRS.map(([before, after], index) => {
        const x = 34 + index * 70
        return (
          <g key={index} className="dp-pair">
            <rect className="dp-bar" x={x} y={158 - before} width="18" height={before} rx="3" />
            <rect className="dp-bar is-coral" x={x + 22} y={158 - after} width="18" height={after} rx="3" />
          </g>
        )
      })}
    </Window>
  )
}

const TABLE_SCORES = [92, 81, 64, 47, 33]

export function EtlPreview() {
  return (
    <Window>
      <rect className="dp-muted" x="14" y="32" width="120" height="6" rx="3" />
      <rect className="dp-muted" x="200" y="32" width="50" height="6" rx="3" />
      {TABLE_SCORES.map((score, index) => {
        const y = 48 + index * 23
        const tone = score >= 70 ? 'is-coral' : score >= 40 ? 'is-soft' : 'is-dim'
        return (
          <g key={index} className="dp-row" style={{ animationDelay: `${index * 0.12}s` }}>
            <line className="dp-rule" x1="14" y1={y - 4} x2="306" y2={y - 4} />
            <rect className="dp-fill" x="14" y={y + 3} width={90 + ((index * 37) % 60)} height="6" rx="3" />
            <rect className="dp-muted" x="200" y={y + 4} width="44" height="4" rx="2" />
            <rect className={`dp-pill ${tone}`} x="266" y={y} width="40" height="13" rx="6.5" />
          </g>
        )
      })}
    </Window>
  )
}

export function AdminPreview() {
  return (
    <Window>
      {[0, 1, 2].map((index) => {
        const y = 36 + index * 30
        const isOn = index !== 2
        return (
          <g key={index} className={isOn ? 'dp-toggle is-on' : 'dp-toggle'}>
            <rect className="dp-muted" x="18" y={y + 7} width={70 + index * 18} height="6" rx="3" />
            <rect className="dp-toggle-track" x="258" y={y} width="40" height="20" rx="10" />
            <circle className="dp-toggle-knob" cx={isOn ? 288 : 268} cy={y + 10} r="7" />
          </g>
        )
      })}
      <rect className="dp-muted" x="18" y="134" width="60" height="6" rx="3" />
      <rect className="dp-slider-track" x="100" y="135" width="198" height="4" rx="2" />
      <rect className="dp-slider-fill" x="100" y="135" width="128" height="4" rx="2" />
      <circle className="dp-slider-knob" cx="228" cy="137" r="8" />
    </Window>
  )
}
