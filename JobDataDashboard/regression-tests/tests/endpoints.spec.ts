import { expect, test, type Page } from '@playwright/test'

// Every GET endpoint the dashboard reads, through the same Caddy proxy the browser uses
// (/api/* -> JobDataServer, /agent-api/* -> JobManagerAgent). Mutating endpoints (POST/PATCH/
// DELETE) are deliberately left out -- this runs against production on every deploy.
const API_ENDPOINTS = [
  '/api/health',
  '/api/jobs?limit=5&offset=0',
  '/api/jobs/count',
  '/api/jobs/search?query=engineer&limit=5&offset=0',
  '/api/jobs/matched?limit=5&offset=0',
  '/api/jobs/matched/count',
  '/api/matches/funnel',
  '/api/matches/prompt-versions',
  '/agent-api/evals',
  '/agent-api/evals/tool-selection',
  '/agent-api/evals/guardrails',
  '/agent-api/evals/datasets',
  '/agent-api/agent-topology',
  '/agent-api/mlflow-summary',
  '/agent-api/admin/prompts',
  '/agent-api/admin/active-prompt/history',
  '/agent-api/admin/unscored-backfill/status',
  '/agent-api/admin/rate-limits',
  '/agent-api/admin/billing-status',
  '/agent-api/admin/feature-flags',
  '/agent-api/backfill/processes',
  '/agent-api/backfill/runs',
]

// Every leaf route in src/App.tsx (HashRouter, so they live after the #). Index routes that only
// <Navigate> to a child are covered by that child.
const UI_ROUTES = [
  '/',
  '/welcome',
  '/observability',
  '/etl-data/jobs',
  '/etl-data/matches',
  '/admin/billing',
  '/admin/rate-limits',
  '/admin/feature-flags',
  '/admin/migrations/prompt-version',
  '/admin/migrations/backfill-handoff',
  '/admin/migrations/prompt-catalog',
  '/evals/kpis',
  '/evals/prompt',
  '/evals/prompt-versions',
  '/evals/datasets',
  '/evals/behavior',
  '/evals/guardrails',
  '/evals/history',
]

test.describe('server', () => {
  // Caddy's try_files serves index.html for any path, so these just have to come back 200.
  for (const path of ['/', '/index.html']) {
    test(`GET ${path}`, async ({ request }) => {
      const response = await request.get(path)
      expect(response.status(), `${path} status`).toBe(200)
      expect(response.headers()['content-type']).toContain('text/html')
    })
  }
})

test.describe('api', () => {
  for (const path of API_ENDPOINTS) {
    test(`GET ${path}`, async ({ request }) => {
      const response = await request.get(path)
      expect(response.status(), `${path} -> ${await response.text().catch(() => '')}`.slice(0, 500)).toBe(200)
    })
  }

  test('GET /agent-api/evals/datasets/:name', async ({ request }) => {
    const list = await request.get('/agent-api/evals/datasets')
    expect(list.status()).toBe(200)
    const datasets = (await list.json()) as { name: string }[]
    test.skip(datasets.length === 0, 'no eval datasets to fetch')
    const path = `/agent-api/evals/datasets/${encodeURIComponent(datasets[0].name)}`
    const response = await request.get(path)
    expect(response.status(), path).toBe(200)
  })
})

// Loads a route in a real browser and fails on any same-origin response that isn't 200 (the
// HTML, JS/CSS chunks, and every /api + /agent-api call the page fires) or any request that never
// got a response. Third-party traffic (PostHog, the Grafana iframe, fonts) is out of scope.
async function collectFailures(page: Page, baseURL: string) {
  const origin = new URL(baseURL).origin
  const failures: string[] = []

  // Cloudflare (in front of the custom domain) injects its own RUM beacon under /cdn-cgi/ -- not
  // part of the app, and it answers 204.
  const isAppRequest = (url: string) => url.startsWith(origin) && !url.startsWith(`${origin}/cdn-cgi/`)

  page.on('response', (response) => {
    const url = response.url()
    if (!isAppRequest(url)) {
      return
    }
    // Only judge the end of a redirect chain.
    if (response.status() >= 300 && response.status() < 400) {
      return
    }
    if (response.status() !== 200) {
      failures.push(`${response.status()} ${response.request().method()} ${url}`)
    }
  })
  page.on('requestfailed', (request) => {
    if (isAppRequest(request.url())) {
      failures.push(`FAILED ${request.method()} ${request.url()} (${request.failure()?.errorText})`)
    }
  })
  page.on('pageerror', (error) => {
    failures.push(`page error: ${error.message}`)
  })

  return failures
}

test.describe('ui routes', () => {
  for (const route of UI_ROUTES) {
    test(`#${route}`, async ({ page, baseURL }) => {
      const failures = await collectFailures(page, baseURL!)

      // ?landing=control pins the root arrival to the dashboard instead of waiting on the
      // landing-page PostHog flag; /welcome is still reachable directly.
      const response = await page.goto(`/?landing=control#${route}`)
      expect(response?.status(), 'document status').toBe(200)

      // Pages keep polling (refetchInterval), so networkidle may never settle -- give the initial
      // queries a bounded window instead.
      await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})

      expect(failures, `non-200 responses on #${route}`).toEqual([])
      // Redirect-to-root catch-all means a route vanished from App.tsx.
      if (route !== '/') {
        expect(new URL(page.url()).hash, 'route still exists').toBe(`#${route}`)
      }
    })
  }
})
