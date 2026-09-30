# JobDataDashboard Lighthouse CI

[Lighthouse CI](https://github.com/GoogleChrome/lighthouse-ci) runs against the deployed dashboard after every deploy. It gives each page a performance, accessibility, best-practices and SEO score, plus FCP, LCP, TBT and CLS timings. Config lives in `lighthouserc.cjs`.

- **Pages:** `#/welcome`, `#/` (Overview), `#/etl-data/matches`, `#/evals/kpis` and `#/admin/rate-limits`. Each URL gets its own `?page=` param because Lighthouse drops the `#hash` from a run's final URL, and LHCI would otherwise merge every route into one page. When you add a page to the dashboard that's worth tracking, add it to `PAGES`.
- **Runs:** each URL is loaded 3 times on Lighthouse's default mobile emulation, and the median run is reported.
- **PostHog:** requests to `*posthog.com*` are blocked, so these runs don't show up as visitors or skew the landing-page experiment.
- **Assertions are warn-only.** The job reports scores but never fails because of them. Once scores have settled, switch the ones worth holding to `'error'` in `lighthouserc.cjs`.

## Results

Each workflow run's summary page has a score table. The full HTML reports are in the run's `lighthouse-reports` artifact, which is kept for 30 days. Nothing is uploaded anywhere public.

## Run locally

```sh
npm ci
npx lhci autorun                                        # against prod
DASHBOARD_URL=http://localhost:8080 npx lhci autorun    # against docker compose
npx lhci autorun --collect.numberOfRuns=1               # quicker, noisier
node summarize.cjs                                      # score table from lhci-reports/
```

Needs a local Chrome.

## CI

This is the `lighthouse` job in `.github/workflows/dashboard-regression.yml`. It runs in parallel with the Playwright page-load tests, once the `deploy` job has seen Railway's deployment of the pushed commit go live.
