import posthog from 'posthog-js'

// Self-hosted PostHog (see PostHog/README.md at the repo root for how to stand one up and what
// gets tracked). Entirely optional: leave VITE_POSTHOG_KEY unset and every function below
// silently no-ops, so the dashboard behaves exactly as it did before this file existed whenever
// no instance is configured (e.g. most local dev).
const POSTHOG_KEY = import.meta.env.VITE_POSTHOG_KEY
const POSTHOG_HOST = import.meta.env.VITE_POSTHOG_HOST || 'http://localhost'
const enabled = Boolean(POSTHOG_KEY)

// Exposed so other modules (see src/lib/experiment.tsx) can tell whether it's safe to call into
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
