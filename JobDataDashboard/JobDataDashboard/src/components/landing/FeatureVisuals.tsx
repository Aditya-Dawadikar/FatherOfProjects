// Small illustrations for the landing page's "Why it matters" cards -- one per feature, each a
// stylized picture of the mechanism rather than a chart of real numbers. Colors and motion come
// from the .fv-* rules in LandingPage.css (animations pause under prefers-reduced-motion).

const VIEW = '0 0 320 150'

export function GuardrailVisual() {
  return (
    <svg className="fv" viewBox={VIEW} aria-hidden="true">
      <rect className="fv-panel" x="12" y="14" width="214" height="122" rx="10" />
      <rect className="fv-line" x="28" y="32" width="120" height="6" rx="3" />
      <rect className="fv-line" x="28" y="48" width="160" height="6" rx="3" />
      <rect className="fv-line" x="28" y="64" width="96" height="6" rx="3" />
      <rect className="fv-danger-bg" x="22" y="78" width="194" height="20" rx="5" />
      <text className="fv-danger-text" x="30" y="92">ignore previous instructions</text>
      <line className="fv-strike" x1="28" y1="88" x2="210" y2="88" />
      <rect className="fv-line" x="28" y="108" width="132" height="6" rx="3" />
      <rect className="fv-scan" x="12" y="14" width="214" height="10" />
      <path className="fv-shield" d="M270 38 l34 12 v24 c0 22 -16 36 -34 42 c-18 -6 -34 -20 -34 -42 v-24 z" />
      <path className="fv-check" d="M256 76 l10 10 l20 -22" />
      <text className="fv-caption" x="270" y="136" textAnchor="middle">blocked</text>
    </svg>
  )
}

const BUDGET_BARS = [34, 48, 42, 60, 56, 72, 66, 78, 70, 84, 90, 96, 88, 76, 64, 58]

export function BudgetVisual() {
  // Bars above the dashed budget line are what the RPM limiter holds back.
  const budgetY = 50
  return (
    <svg className="fv" viewBox={VIEW} aria-hidden="true">
      <text className="fv-caption" x="24" y="30">requests / min</text>
      <line className="fv-budget" x1="20" y1={budgetY} x2="300" y2={budgetY} />
      <text className="fv-caption is-coral" x="300" y={budgetY - 8} textAnchor="end">budget</text>
      {BUDGET_BARS.map((height, index) => {
        const x = 24 + index * 17
        const top = 132 - height
        return (
          <g key={index} className="fv-bar" style={{ animationDelay: `${index * 90}ms` }}>
            <rect className="fv-bar-under" x={x} y={Math.max(top, budgetY)} width="11" height={132 - Math.max(top, budgetY)} rx="2" />
            {top < budgetY && <rect className="fv-bar-over" x={x} y={top} width="11" height={budgetY - top} rx="2" />}
          </g>
        )
      })}
    </svg>
  )
}

const LIVE_PATH = 'M76 34 H200 C230 34 236 75 262 75'
const BACKFILL_PATH = 'M76 104 H200 C230 104 236 75 262 75'

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function SchedulingVisual() {
  // Live jobs stream in faster and more often than backfill ones -- the agent always takes fresh
  // postings first. SMIL <animateMotion> follows the curved track; under reduced motion the dots
  // are simply drawn in place along it.
  const isStill = prefersReducedMotion()
  const dot = (className: string, path: string, durationSeconds: number, index: number, stillX: number, stillY: number) =>
    isStill ? (
      <circle key={`${className}-${index}`} className={className} cx={stillX} cy={stillY} r="5" />
    ) : (
      <circle key={`${className}-${index}`} className={className} r="5">
        <animateMotion dur={`${durationSeconds}s`} repeatCount="indefinite" begin={`${-index * (durationSeconds / 4)}s`} path={path} />
      </circle>
    )
  return (
    <svg className="fv" viewBox={VIEW} aria-hidden="true">
      <text className="fv-caption is-coral" x="20" y="38">live</text>
      <text className="fv-caption" x="20" y="108">backfill</text>
      <path className="fv-track" d={LIVE_PATH} />
      <path className="fv-track" d={BACKFILL_PATH} />
      {[0, 1, 2, 3].map((index) => dot('fv-dot-live', LIVE_PATH, 2.4, index, 100 + index * 32, 34))}
      {[0, 1].map((index) => dot('fv-dot-backfill', BACKFILL_PATH, 6, index, 110 + index * 60, 104))}
      <circle className="fv-agent" cx="282" cy="75" r="20" />
      <text className="fv-caption" x="282" y="79" textAnchor="middle">agent</text>
    </svg>
  )
}

export function ObservabilityVisual() {
  return (
    <svg className="fv" viewBox={VIEW} aria-hidden="true">
      {[30, 62, 94, 126].map((y) => (
        <line key={y} className="fv-grid" x1="20" y1={y} x2="300" y2={y} />
      ))}
      <path className="fv-area" d="M20 104 L50 96 L80 100 L110 78 L140 84 L170 60 L200 70 L230 48 L260 56 L300 38 V126 H20 Z" />
      <path className="fv-series" d="M20 104 L50 96 L80 100 L110 78 L140 84 L170 60 L200 70 L230 48 L260 56 L300 38" />
      <path className="fv-series is-coral" d="M20 116 L50 114 L80 118 L110 110 L140 112 L170 104 L200 108 L230 100 L260 102 L300 96" />
      <circle className="fv-cursor" cx="230" cy="48" r="4" />
    </svg>
  )
}

const SWITCHES = [
  { label: 'scrape', on: true },
  { label: 'agent', on: true },
  { label: 'backfill', on: false },
]

export function KillSwitchVisual() {
  return (
    <svg className="fv" viewBox={VIEW} aria-hidden="true">
      {SWITCHES.map((toggle, index) => {
        const y = 22 + index * 40
        return (
          <g key={toggle.label} className={`fv-switch${toggle.on ? ' is-on' : ' is-flipping'}`}>
            <text className="fv-switch-label" x="40" y={y + 21}>{toggle.label}</text>
            <rect className="fv-switch-track" x="220" y={y + 4} width="56" height="26" rx="13" />
            <circle className="fv-switch-knob" cx={toggle.on ? 263 : 233} cy={y + 17} r="9" />
          </g>
        )
      })}
    </svg>
  )
}

const EVENTS = ['pipeline_started', 'stage_started', 'stage_completed', 'pipeline_completed']

export function EventStreamVisual() {
  // Two copies of the chip row side by side, so the marquee loops seamlessly.
  const chips = [...EVENTS, ...EVENTS]
  return (
    <svg className="fv" viewBox={VIEW} aria-hidden="true">
      <line className="fv-track" x1="0" y1="75" x2="320" y2="75" />
      <g className="fv-marquee">
        {chips.map((event, index) => {
          const x = 10 + index * 150
          return (
            <g key={index}>
              <rect className={index % 4 === 3 ? 'fv-chip is-coral' : 'fv-chip'} x={x} y="60" width="136" height="30" rx="15" />
              <text className="fv-chip-text" x={x + 68} y="79" textAnchor="middle">{event}</text>
            </g>
          )
        })}
      </g>
      <text className="fv-caption" x="20" y="130">redis stream · every service</text>
    </svg>
  )
}
