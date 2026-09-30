import posthog from 'posthog-js'

// PostHog Cloud (see PostHog/README.md at the repo root for how to stand one up and what
// gets tracked). Entirely optional: leave VITE_POSTHOG_KEY unset and every function below
// silently no-ops, so the dashboard behaves exactly as it did before this file existed whenever
// no instance is configured (e.g. most local dev).
const POSTHOG_KEY = import.meta.env.VITE_POSTHOG_KEY
const POSTHOG_HOST = import.meta.env.VITE_POSTHOG_HOST || 'http://localhost'
const enabled = Boolean(POSTHOG_KEY)

// Exposed so other modules (see src/lib/landingExperiment.ts) can tell whether it's safe to call into
// the posthog-js singleton at all -- same "no configured instance" case initAnalytics/trackEvent/
// trackPageview already no-op on above.
export function isAnalyticsEnabled() {
  return enabled
}

export function initAnalytics() {
  if (!enabled) return
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    person_profiles: 'always',
    // Fired manually on route change instead -- HashRouter navigation never triggers a real page
    // load, so posthog-js's own history-based autocapture would miss every tab switch. See
    // trackPageview, called from Layout.tsx.
    capture_pageview: false,
    session_recording: {
      // Nothing in this dashboard's inputs holds anything worth capturing, but masking is the
      // safe default regardless -- visitor session replays are the point, not what they typed.
      maskAllInputs: true,
    },
  })
}

export function trackPageview(pathname: string) {
  if (!enabled) return
  posthog.capture('$pageview', { $current_url: `${window.location.origin}${window.location.pathname}#${pathname}` })
}

export function trackEvent(name: string, properties?: Record<string, unknown>) {
  if (!enabled) return
  posthog.capture(name, properties)
}

// Primary metric of the landing-page experiment (see src/lib/landingExperiment.ts): fired the
// first time each top-level dashboard section is reached in a browser session, in both variants,
// so "sections reached per person" is a plain event-count metric in PostHog. The landing page
// itself (/welcome) is deliberately not a section -- it'd inflate the test variant's count.
const SECTIONS_STORAGE_KEY = 'dashboard_sections_reached'

export function trackSectionReached(pathname: string) {
  if (!enabled) return
  const section = pathname.split('/')[1] || 'overview'
  if (section === 'welcome') return

  let reached: string[]
  try {
    reached = JSON.parse(window.sessionStorage.getItem(SECTIONS_STORAGE_KEY) ?? '[]')
  } catch {
    reached = []
  }
  if (reached.includes(section)) return

  reached.push(section)
  try {
    window.sessionStorage.setItem(SECTIONS_STORAGE_KEY, JSON.stringify(reached))
  } catch {
    // Storage blocked -- worst case the same section is counted again later in this session.
  }
  posthog.capture('dashboard_section_reached', { section, sections_reached_count: reached.length })
}
