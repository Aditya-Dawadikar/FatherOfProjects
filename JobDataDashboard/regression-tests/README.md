# JobDataDashboard regression tests

Playwright checks that every endpoint of the deployed dashboard answers **200**:

- **server** – `/` and `/index.html` from Caddy.
- **api** – every GET endpoint the dashboard calls, through the Caddy proxy (`/api/*` → JobDataServer, `/agent-api/*` → JobManagerAgent). Mutating endpoints are skipped since this runs against production.
- **ui routes** – every route in `src/App.tsx` is loaded in Chromium; any same-origin response that isn't 200 (HTML, JS/CSS chunks, API calls the page fires), failed request, or uncaught page error fails the test. Third-party traffic (PostHog, Grafana iframe, Cloudflare `/cdn-cgi/`) is ignored.

When you add a route or a GET endpoint to the dashboard, add it to `UI_ROUTES` / `API_ENDPOINTS` in `tests/endpoints.spec.ts`.

## Run locally

```sh
npm install
npx playwright install chromium
npx playwright test                                      # against prod
DASHBOARD_URL=http://localhost:8080 npx playwright test  # against docker compose
```

## CI

`.github/workflows/dashboard-regression.yml` runs on every successful Railway deployment (`deployment_status`) and on manual dispatch. Set the `DASHBOARD_URL` repo variable to override the default prod domain. The failure report and traces are uploaded as the `playwright-report` artifact.
