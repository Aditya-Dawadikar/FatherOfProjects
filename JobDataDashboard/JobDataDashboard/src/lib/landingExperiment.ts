import posthog from 'posthog-js'
import { isAnalyticsEnabled } from './posthog'

// Landing page vs. straight-to-dashboard A/B test: do visitors who first see the landing page
// explore more of the dashboard? Like mobile-first-layout (see ./experiment.tsx), the experiment
// itself (variants, allocation, metrics) lives in PostHog Cloud -- this is the flag key both sides
// agree on. Multivariate "control" / "test" (a boolean flag also works: `true` means "test").
export const LANDING_FLAG_KEY = 'landing-page'
export const LANDING_PATH = '/welcome'

type Variant = 'control' | 'test'

// QA/screenshot override: ?landing=test|control. Unlike ?mobile_layout it isn't remembered --
// "test" shows the landing page on every root arrival that carries it, which is what you want
// while iterating on the page itself.
const OVERRIDE_PARAM = 'landing'
// Set once the landing page has been shown, so a test visitor sees it once, not on every visit.
const SEEN_STORAGE_KEY = 'landing_seen'
// How long a root arrival waits for PostHog's flags before falling back to the dashboard. Past
// this the visitor is treated as not enrolled (and the flag is never read, so no exposure gets
// logged for someone who in fact saw the control experience by default).
const FLAG_TIMEOUT_MS = 1500

// Captured at module load, before HashRouter's <Navigate>s rewrite the hash. Only visitors who
// arrive at the root are enrolled -- a deep link (e.g. someone sharing #/evals/kpis) means the
// visitor already knows where they're going, and bouncing them through a landing page would
// both be hostile and skew the exploration metric.
const initialHash = typeof window === 'undefined' ? '' : window.location.hash
export const arrivedAtRoot = initialHash === '' || initialHash === '#' || initialHash === '#/'

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function markLandingSeen() {
  try {
    window.localStorage.setItem(SEEN_STORAGE_KEY, '1')
  } catch {
    // Storage blocked (private mode etc.) -- they may just see the landing page again next time.
  }
}

function readOverride(): Variant | null {
  if (typeof window === 'undefined') {
    return null
  }
  const fromUrl = new URLSearchParams(window.location.search).get(OVERRIDE_PARAM)
  return fromUrl === 'test' || fromUrl === 'control' ? fromUrl : null
}

function waitForFlag(): Promise<Variant | null> {
  return new Promise((resolve) => {
    let settled = false
    const timeout = window.setTimeout(() => {
      settled = true
      resolve(null)
    }, FLAG_TIMEOUT_MS)

    posthog.onFeatureFlags(() => {
      if (settled) {
        return
      }
      settled = true
      window.clearTimeout(timeout)
      // Reading the flag here (and only here) is what makes posthog-js log the experiment
      // exposure -- so it's logged exactly for the root arrivals that were actually split.
      const flagValue = posthog.getFeatureFlag(LANDING_FLAG_KEY)
      resolve(flagValue === 'test' || flagValue === true ? 'test' : 'control')
    })
  })
}

// Module-level so StrictMode's double-invoked effect (and any remount) shares one resolution
// instead of reading the flag twice.
let variantPromise: Promise<Variant | null> | null = null

export function resolveLandingVariant(): Promise<Variant | null> {
  if (!variantPromise) {
    const override = readOverride()
    if (override) {
      variantPromise = Promise.resolve(override)
    } else if (readStorage(SEEN_STORAGE_KEY) || !isAnalyticsEnabled()) {
      variantPromise = Promise.resolve(null)
    } else {
      variantPromise = waitForFlag()
    }
  }
  return variantPromise
}
