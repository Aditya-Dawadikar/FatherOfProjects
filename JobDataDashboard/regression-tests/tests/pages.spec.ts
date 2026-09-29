import { expect, test, type Page } from '@playwright/test'

// Every leaf route in src/App.tsx (HashRouter, so they live after the #). Index routes that only
// <Navigate> to a child are covered by that child.
const PAGES = [
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

// Collects everything that means the page itself didn't load: a non-200 for the HTML or any of
// its own assets (JS/CSS chunks, images, fonts), an asset request that never got a response, or
// an uncaught error. Data calls (fetch/XHR to /api, /agent-api) and third-party traffic (PostHog,
// the Grafana iframe, Cloudflare's /cdn-cgi/ beacon) are out of scope.
function collectFailures(page: Page, baseURL: string) {
  const origin = new URL(baseURL).origin
  const failures: string[] = []

  const isPageAsset = (url: string, resourceType: string) =>
    url.startsWith(origin) &&
    !url.startsWith(`${origin}/cdn-cgi/`) &&
    resourceType !== 'fetch' &&
    resourceType !== 'xhr'

  page.on('response', (response) => {
    const request = response.request()
    if (!isPageAsset(response.url(), request.resourceType())) {
      return
    }
    // Only judge the end of a redirect chain.
    if (response.status() >= 300 && response.status() < 400) {
      return
    }
    if (response.status() !== 200) {
      failures.push(`${response.status()} ${request.method()} ${response.url()}`)
    }
  })
  page.on('requestfailed', (request) => {
    if (isPageAsset(request.url(), request.resourceType())) {
      failures.push(`FAILED ${request.method()} ${request.url()} (${request.failure()?.errorText})`)
    }
  })
  page.on('pageerror', (error) => {
    failures.push(`page error: ${error.message}`)
  })

  return failures
}

for (const route of PAGES) {
  test(`#${route} loads`, async ({ page, baseURL }) => {
    const failures = collectFailures(page, baseURL!)

    // ?landing=control pins the root arrival to the dashboard instead of waiting on the
    // landing-page PostHog flag; /welcome is still reachable directly.
    const response = await page.goto(`/?landing=control#${route}`)
    expect(response?.status(), 'document status').toBe(200)

    // Pages keep polling (refetchInterval), so networkidle may never settle -- give lazy chunks
    // a bounded window instead.
    await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})

    // React rendered something into #root (a crash leaves it empty).
    await expect(page.locator('#root')).not.toBeEmpty()
    expect(failures, `#${route} failed to load`).toEqual([])
    // The catch-all redirects unknown routes to /, so landing elsewhere means the page vanished.
    if (route !== '/') {
      expect(new URL(page.url()).hash, 'route still exists').toBe(`#${route}`)
    }
  })
}
