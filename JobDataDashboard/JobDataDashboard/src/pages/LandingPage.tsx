import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { IconType } from 'react-icons'
import { FiActivity, FiArrowRight, FiBarChart2, FiDatabase, FiLayout, FiSettings } from 'react-icons/fi'
import FunnelHero from '../components/landing/FunnelHero'
import { useMatchedJobs, useMlflowSummary, usePipelineFunnel } from '../hooks'
import { LANDING_PATH, markLandingSeen } from '../lib/landingExperiment'
import { trackEvent, trackPageview } from '../lib/posthog'
import './LandingPage.css'

// The test variant of the landing-page experiment (see src/lib/landingExperiment.ts). Rendered
// outside Layout -- no top nav or billing banner -- and lazy-loaded from App.tsx so visitors in
// the control variant never download it. Every link out of here is tracked as
// landing_cta_clicked, and each section scrolling into view as landing_section_viewed, so PostHog
// can tell which doors people actually used and how far down they read.

const FONTS_LINK_ID = 'landing-fonts'
const FONTS_HREF =
  'https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap'

// Only the matched jobs the API returns first (newest evaluations) are ranked for the hero --
// enough to surface strong recent matches without paging the whole table.
const TOP_MATCHES_QUERY = { searchText: '', matchFilter: 'matched' as const, minScore: null, promptVersion: null, limit: 50, offset: 0 }

type Step = { n: string; tech: string; title: string; body: string; to: string; linkLabel: string }

const STEPS: Step[] = [
  {
    n: '01',
    tech: 'WebScraper',
    title: 'Scrape',
    body: 'Pulls Work at a Startup, Greenhouse, Ashby and Lever. It keeps only recent engineering roles, caps each source per run, and purges anything older than a week.',
    to: '/etl-data/jobs',
    linkLabel: 'ETL Data › Jobs',
  },
  {
    n: '02',
    tech: 'LangGraph · Gemini',
    title: 'Score',
    body: 'A ReAct agent crawls the full posting and scores it against a resume with a versioned rubric prompt. It records a score and its reasoning.',
    to: '/',
    linkLabel: 'Agent Overview',
  },
  {
    n: '03',
    tech: 'MLflow',
    title: 'Iterate',
    body: 'Prompts are registered, not hardcoded. New versions are compared on a golden eval set, then cut over and backfilled. Every step is auditable.',
    to: '/evals',
    linkLabel: 'Agent Evals',
  },
  {
    n: '04',
    tech: 'React dashboard',
    title: 'Review',
    body: 'Every match with its score and reasoning, filterable by source. The funnel shows what was scraped, what was scored, and what is still pending.',
    to: '/etl-data/matches',
    linkLabel: 'ETL Data › Matches',
  },
]

type Feature = { tag: string; title: string; body: string; spark: string; to: string }

const FEATURES: Feature[] = [
  {
    tag: 'Guardrails',
    title: 'Postings are untrusted input',
    body: 'Checks for prompt-injected job descriptions, evaluated like everything else.',
    spark: 'M0 40 L20 36 L40 38 L60 20 L80 24 L100 10 L120 12',
    to: '/evals/guardrails',
  },
  {
    tag: 'Cost control',
    title: 'RPM budget + billing alarm',
    body: 'A per-minute request budget. If Gemini billing runs out, every tab shows it right away.',
    spark: 'M0 24 L20 24 L40 24 L60 8 L80 24 L100 24 L120 24',
    to: '/admin/rate-limits',
  },
  {
    tag: 'Scheduling',
    title: 'Live vs backfill split',
    body: 'Fresh jobs always get scored first. A backlog cannot crowd them out.',
    spark: 'M0 44 L30 30 L60 30 L90 14 L120 6',
    to: '/admin/migrations/backfill-handoff',
  },
  {
    tag: 'Observability',
    title: 'Prometheus + Grafana',
    body: 'Operational health tracked apart from the pipeline data.',
    spark: 'M0 30 L15 22 L30 34 L45 18 L60 26 L75 12 L90 28 L105 16 L120 20',
    to: '/observability',
  },
  {
    tag: 'Kill switches',
    title: 'Feature-flag registry',
    body: 'Scrape, agent and backfill can each be switched off from Admin.',
    spark: 'M0 10 L40 10 L40 38 L80 38 L80 10 L120 10',
    to: '/admin/feature-flags',
  },
  {
    tag: 'Events',
    title: 'Redis stream of every stage',
    body: 'Pipeline start, stage and completion events for the whole system.',
    spark: 'M0 24 L10 24 L14 8 L18 40 L22 24 L60 24 L64 8 L68 40 L72 24 L120 24',
    to: '/',
  },
]

type Door = { title: string; body: string; to: string; icon: IconType; bars: number[]; tone: 'accent' | 'coral' | 'muted' }

const DOORS: Door[] = [
  { title: 'Agent Overview', body: 'The live agent graph, ETL architecture and data overview.', to: '/', icon: FiLayout, bars: [30, 60, 44, 80, 52, 70, 40], tone: 'accent' },
  { title: 'Observability', body: 'Grafana boards for throughput, latency and errors.', to: '/observability', icon: FiBarChart2, bars: [50, 54, 48, 70, 66, 90, 84], tone: 'accent' },
  { title: 'Agent Evals', body: 'KPIs, prompt comparisons, datasets, guardrails and run history.', to: '/evals', icon: FiActivity, bars: [80, 72, 86, 64, 90, 76, 88], tone: 'coral' },
  { title: 'ETL Data', body: 'Every scraped job and every scored match.', to: '/etl-data', icon: FiDatabase, bars: [90, 70, 56, 40, 30, 20, 14], tone: 'accent' },
  { title: 'Admin', body: 'Billing, rate limits, feature flags and prompt migrations.', to: '/admin', icon: FiSettings, bars: [40, 40, 40, 90, 40, 40, 40], tone: 'muted' },
]

function trackCta(target: string, position: string) {
  trackEvent('landing_cta_clicked', { target, position })
}

function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

// Counts up from 0 to `target` once `active` flips true (the stats strip scrolling into view).
function useCountUp(target: number | null, active: boolean) {
  const [value, setValue] = useState(0)

  useEffect(() => {
    if (target === null || !active) {
      return
    }
    if (prefersReducedMotion()) {
      setValue(target)
      return
    }
    const startedAt = performance.now()
    const durationMs = 1200
    let frame = requestAnimationFrame(function step(now) {
      const progress = Math.min(1, (now - startedAt) / durationMs)
      setValue(Math.round(target * (1 - Math.pow(1 - progress, 3))))
      if (progress < 1) {
        frame = requestAnimationFrame(step)
      }
    })
    return () => cancelAnimationFrame(frame)
  }, [target, active])

  return target === null ? null : value
}

function StatValue({ target, active }: { target: number | null; active: boolean }) {
  const value = useCountUp(target, active)
  return <span className="landing-stat-value">{value === null ? '—' : value.toLocaleString()}</span>
}

function ArrowIcon() {
  return <FiArrowRight aria-hidden="true" className="landing-arrow" />
}

type SectionProps = {
  name: string
  id?: string
  className: string
  revealed: boolean
  register: (name: string, element: HTMLElement | null) => void
  children: ReactNode
}

function Section({ name, id, className, revealed, register, children }: SectionProps) {
  return (
    <section
      id={id}
      ref={(element) => register(name, element)}
      data-landing-section={name}
      className={`${className} landing-reveal${revealed ? ' is-revealed' : ''}`}
    >
      {children}
    </section>
  )
}

export default function LandingPage() {
  const funnelQuery = usePipelineFunnel()
  const mlflowQuery = useMlflowSummary()
  const matchesQuery = useMatchedJobs(TOP_MATCHES_QUERY)
  const [revealed, setRevealed] = useState<Set<string>>(() => new Set())
  const observerRef = useRef<IntersectionObserver | null>(null)
  const sectionsRef = useRef(new Map<string, HTMLElement>())

  useEffect(() => {
    markLandingSeen()
    trackPageview(LANDING_PATH)
    trackEvent('landing_viewed')

    if (!document.getElementById(FONTS_LINK_ID)) {
      const link = document.createElement('link')
      link.id = FONTS_LINK_ID
      link.rel = 'stylesheet'
      link.href = FONTS_HREF
      document.head.appendChild(link)
    }
  }, [])

  useEffect(() => {
    const seen = new Set<string>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const name = (entry.target as HTMLElement).dataset.landingSection
          if (!entry.isIntersecting || !name || seen.has(name)) {
            continue
          }
          seen.add(name)
          observer.unobserve(entry.target)
          trackEvent('landing_section_viewed', { section: name })
          setRevealed((current) => new Set(current).add(name))
        }
      },
      { threshold: 0.2 },
    )
    observerRef.current = observer
    sectionsRef.current.forEach((element) => observer.observe(element))
    return () => observer.disconnect()
  }, [])

  // Callback ref for each <Section>: remembers the element and starts observing it (sections
  // mount before the observer effect above runs, which then picks up whatever's registered).
  const registerSection = (name: string, element: HTMLElement | null) => {
    if (!element) {
      sectionsRef.current.delete(name)
      return
    }
    sectionsRef.current.set(name, element)
    observerRef.current?.observe(element)
  }

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'start' })
  }

  const topMatches = matchesQuery.data ? [...matchesQuery.data].sort((a, b) => b.match_score - a.match_score) : matchesQuery.isError ? [] : null
  const productionPrompt = mlflowQuery.data?.production_prompt_version
  const lensCaption = productionPrompt
    ? `Gemini · prompt ${productionPrompt.startsWith('v') ? productionPrompt : `v${productionPrompt}`}`
    : 'Gemini · versioned rubric'
  const statsActive = revealed.has('stats')

  return (
    <div className="landing">
      <header className="landing-header">
        <Link to="/" className="landing-brand" onClick={() => trackCta('/', 'header-brand')}>
          <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
            <circle cx="14" cy="14" r="12" fill="none" stroke="var(--l-accent)" strokeWidth="2" />
            <circle cx="14" cy="14" r="4" fill="var(--l-coral)" />
          </svg>
          FatherOfProjects
        </Link>
        <nav className="landing-nav" aria-label="Landing page">
          <button type="button" onClick={() => scrollTo('how')}>How it works</button>
          <button type="button" onClick={() => scrollTo('under-the-hood')}>Under the hood</button>
          <button type="button" onClick={() => scrollTo('doors')}>Tour the dashboard</button>
          <Link to="/" className="landing-button is-primary" onClick={() => trackCta('/', 'header')}>
            <span className="landing-label-long">Open the dashboard</span>
            <span className="landing-label-short">Open app</span>
            <ArrowIcon />
          </Link>
        </nav>
      </header>

      <section className="landing-intro">
        <div className="landing-eyebrow">An autonomous job-search pipeline</div>
        <h1>
          Four job boards in.{' '}
          <br />
          <span className="landing-highlight">One ranked list</span> out.
        </h1>
        <p>
          It scrapes engineering roles every four hours, has an LLM agent read and score each one against a resume, and
          puts the results in one dashboard. Nobody has to rescan four career sites by hand.
        </p>
      </section>

      <FunnelHero topMatches={topMatches} lensCaption={lensCaption} onMatchClick={() => trackCta('/etl-data/matches', 'hero-match')} />

      <Section name="stats" className="landing-stats" revealed={statsActive} register={registerSection}>
        <div className="landing-stat">
          <StatValue target={funnelQuery.data?.total_scraped ?? null} active={statsActive} />
          <span className="landing-stat-label">postings scraped</span>
        </div>
        <div className="landing-stat">
          <StatValue target={funnelQuery.data?.total_processed ?? null} active={statsActive} />
          <span className="landing-stat-label">scored by the agent</span>
        </div>
        <div className="landing-stat">
          <StatValue target={mlflowQuery.data?.registered_prompt_versions ?? null} active={statsActive} />
          <span className="landing-stat-label">prompt versions in MLflow</span>
        </div>
        <div className="landing-stat">
          <StatValue target={4} active={statsActive} />
          <span className="landing-stat-label">job boards, checked every 4 hours</span>
        </div>
      </Section>

      <Section name="how" id="how" className="landing-section" revealed={revealed.has('how')} register={registerSection}>
        <div className="landing-section-head">
          <h2>Four stages. Each one is a tab you can open.</h2>
          <p>Every card links to the part of the dashboard where that stage runs.</p>
        </div>
        <div className="landing-steps">
          {STEPS.map((step) => (
            <article key={step.n} className="landing-card landing-step">
              <div className="landing-step-top">
                <span className="landing-mono is-accent">{step.n}</span>
                <span className="landing-mono">{step.tech}</span>
              </div>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
              <Link to={step.to} className="landing-step-link" onClick={() => trackCta(step.to, `step-${step.title.toLowerCase()}`)}>
                <span>{step.linkLabel}</span>
                <ArrowIcon />
              </Link>
            </article>
          ))}
        </div>
      </Section>

      <Section name="under-the-hood" id="under-the-hood" className="landing-section" revealed={revealed.has('under-the-hood')} register={registerSection}>
        <div className="landing-section-head is-stacked">
          <div className="landing-eyebrow is-coral">Why it matters</div>
          <h2 className="is-wide">Every score is a billed LLM call, so the system is built to avoid wasting them.</h2>
        </div>
        <div className="landing-features">
          {FEATURES.map((feature) => (
            <Link
              key={feature.tag}
              to={feature.to}
              className="landing-card landing-feature"
              onClick={() => trackCta(feature.to, `feature-${feature.tag.toLowerCase().replace(/\s+/g, '-')}`)}
            >
              <svg className="landing-feature-spark" width="120" height="48" viewBox="0 0 120 48" aria-hidden="true">
                <path d={feature.spark} />
              </svg>
              <span className="landing-mono is-upper">{feature.tag}</span>
              <h3>{feature.title}</h3>
              <p>{feature.body}</p>
            </Link>
          ))}
        </div>
      </Section>

      <Section name="doors" id="doors" className="landing-section" revealed={revealed.has('doors')} register={registerSection}>
        <div className="landing-section-head">
          <h2>Pick a door.</h2>
          <p>Five sections, all running on live data. Each door opens its tab directly.</p>
        </div>
        <div className="landing-doors">
          {DOORS.map((door) => (
            <Link key={door.to} to={door.to} className="landing-card landing-door" onClick={() => trackCta(door.to, 'door')}>
              <div className={`landing-door-preview is-${door.tone}`} aria-hidden="true">
                <door.icon className="landing-door-icon" />
                <div className="landing-door-bars">
                  {door.bars.map((height, index) => (
                    <span key={index} style={{ height: `${height}%` }} />
                  ))}
                </div>
              </div>
              <span className="landing-door-title">{door.title}</span>
              <span className="landing-door-body">{door.body}</span>
              <span className="landing-mono is-accent">#{door.to}</span>
            </Link>
          ))}
        </div>
      </Section>

      <Section name="footer" className="landing-footer" revealed={revealed.has('footer')} register={registerSection}>
        <div>
          <h2>See it running.</h2>
          <p>Real data, a real agent, real evals.</p>
        </div>
        <Link to="/" className="landing-button is-primary is-large" onClick={() => trackCta('/', 'footer')}>
          Open the dashboard
          <ArrowIcon />
        </Link>
      </Section>
    </div>
  )
}
