// Lighthouse CI config for the deployed dashboard -- run by .github/workflows/dashboard-regression.yml
// once Railway's deploy of the pushed commit is live. See README.md next to this file.
const baseUrl = (process.env.DASHBOARD_URL ?? 'https://projectycjobs.buildwithadi.dev').replace(/\/$/, '')

// HashRouter routes, each with its own ?page= query param: Lighthouse drops the #hash from a run's
// final URL, and LHCI's assertions group runs by that final URL -- without a distinct query string
// every hash route would be merged into one "/" page. The app ignores the param. The Overview goes
// through LandingGate, which otherwise waits on the landing-page PostHog flag before deciding where
// to send the visitor; ?landing=control skips that wait (and never reads the flag).
const PAGES = [
  ['welcome', '/welcome'],
  ['overview', '/', 'landing=control'],
  ['matches', '/etl-data/matches'],
  ['evals', '/evals/kpis'],
  ['rate-limits', '/admin/rate-limits'],
]
const URLS = PAGES.map(([name, route, extra]) => `${baseUrl}/?page=${name}${extra ? `&${extra}` : ''}#${route}`)

module.exports = {
  ci: {
    collect: {
      url: URLS,
      // Median of 3 runs per URL -- single Lighthouse runs against a live site are noisy.
      numberOfRuns: 3,
      settings: {
        // Mobile emulation (Lighthouse's default) -- the dashboard's only layout is mobile-first.
        // Keep these runs out of PostHog: they'd show up as real visitors and skew the
        // landing-page experiment's numbers.
        blockedUrlPatterns: ['*posthog.com*'],
      },
    },
    assert: {
      // Warnings only for now: the job reports scores without failing the build until there's a
      // baseline to hold the line on. Tighten to 'error' (and raise minScore) once scores settle.
      assertions: {
        'categories:performance': ['warn', { minScore: 0.7 }],
        'categories:accessibility': ['warn', { minScore: 0.9 }],
        'categories:best-practices': ['warn', { minScore: 0.9 }],
        'categories:seo': ['warn', { minScore: 0.8 }],
      },
    },
    upload: {
      // Reports are kept as a workflow artifact (see the workflow), not published anywhere public.
      target: 'filesystem',
      outputDir: './lhci-reports',
    },
  },
}
