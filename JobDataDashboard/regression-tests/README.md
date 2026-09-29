# JobDataDashboard regression tests

Playwright checks that every page of the deployed dashboard loads. Each route in `src/App.tsx` is opened in Chromium and fails if:

- the HTML document isn't a 200,
- any of the page's own assets (JS/CSS chunks, images, fonts) isn't a 200 or never responds,
- the page throws an uncaught error or renders nothing into `#root`,
- the route redirects to `/` (i.e. it was removed from the router).

API calls the pages make (`/api/*`, `/agent-api/*`) are not checked, and neither is third-party traffic (PostHog, the Grafana iframe, Cloudflare `/cdn-cgi/`).

When you add a page to the dashboard, add its route to `PAGES` in `tests/pages.spec.ts`.

## Run locally

```sh
npm install
npx playwright install chromium
npx playwright test                                      # against prod
DASHBOARD_URL=http://localhost:8080 npx playwright test  # against docker compose
```

## CI

`.github/workflows/dashboard-regression.yml` runs on every successful Railway deployment (`deployment_status`) and on manual dispatch. Set the `DASHBOARD_URL` repo variable to override the default prod domain. The failure report and traces are uploaded as the `playwright-report` artifact.
