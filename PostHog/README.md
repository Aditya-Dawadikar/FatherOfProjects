# PostHog

Product analytics for JobDataDashboard: how far recruiters explore it (which tabs they reach,
how deep, where they drop off), plus session recordings. Running on **PostHog Cloud's free
tier**, not self-hosted -- see [History](#history) below for why.

## Wiring into JobDataDashboard

| Variable | Value |
| --- | --- |
| `VITE_POSTHOG_KEY` | Project API key from PostHog Cloud (Project Settings -> Project API Key) |
| `VITE_POSTHOG_HOST` | `https://us.i.posthog.com` or `https://eu.i.posthog.com`, matching the project's region |

Leave `VITE_POSTHOG_KEY` unset to disable analytics entirely -- `src/lib/posthog.ts` no-ops every
call when it's blank, so the app behaves exactly as it did before PostHog existed. Both are baked
in at build time (Vite's `import.meta.env`), not read at runtime, so where you set them depends on
where the build happens:

- **Local dev**: `JobDataDashboard/JobDataDashboard/.env` (gitignored).
- **Railway**: set both as variables on the **JobDataDashboard** service itself (Railway dashboard
  -> that service -> Variables). `JobDataDashboard/Dockerfile` declares matching `ARG`s so Railway's
  build forwards them into the Vite build -- setting them alone doesn't take effect until the
  service redeploys and rebuilds.

## What's instrumented

- **`src/lib/posthog.ts`** -- `initAnalytics()` (called once from `main.tsx`), `trackPageview()`,
  `trackEvent()`. Session recordings are on, with `maskAllInputs: true`.
- **Pageviews** -- fired manually from `src/components/Layout.tsx` on every route change (a
  `useEffect` keyed on `location.pathname`). Necessary because the app uses `HashRouter`; a
  hash-only navigation never triggers a real page load, so posthog-js's own autocapture pageview
  tracking (disabled via `capture_pageview: false`) would miss every tab switch. Every tab already
  becomes a distinct `$pageview` pathname (`/`, `/observability`, `/evals/kpis`, `/etl-data/jobs`,
  `/admin/feature-flags`, ...), so exploration-depth funnels are just PostHog insights over
  pathname -- no custom "depth" code needed.
- **Autocapture** -- on by default (posthog-js default), covers clicks/inputs across the app.
- **Custom events** -- `feature_flag_toggled` (`pages/admin/FeatureFlagsTab.tsx`) and
  `rate_limit_distribution_updated` (`pages/admin/RateLimitsTab.tsx`), the two places the
  dashboard's *operator* changes real system state; plus the landing-page experiment's events
  (below).

## Experiment: `landing-page`

Does seeing a landing page first make visitors explore more of the dashboard? The test variant
gets `#/welcome` (`src/pages/LandingPage.tsx`, a lazy-loaded chunk), control gets the Overview tab
as before. Gating lives in `src/lib/landingExperiment.ts` + `src/components/LandingGate.tsx`:

- **Who's enrolled**: only visitors arriving at the root (no hash, or `#/`). Deep links
  (`#/evals/kpis`, ...) skip the landing page and never read the flag, so they log no exposure.
- **Every root arrival**: for test visitors `/welcome` is the front door -- each visit to the
  root lands there, not just the first. "Open the dashboard" (or any door) goes into the app.
- **Revisits from the dashboard**: the brand link in the top nav opens `/welcome` from any page, for
  both variants. Filter `landing_viewed` on `entry = experiment` when comparing variants, so control
  visitors who chose to open it don't count as exposed to the landing page.
- **Phones are included** -- the landing page is responsive on its own.
- **Flag timeout**: a root arrival waits up to 1.5s for flags, then falls back to the dashboard
  without reading the flag (no exposure logged).
- **QA override**: `?landing=test` or `?landing=control` (not remembered across page loads).

Events:

| Event | Where | Properties |
| --- | --- | --- |
| `dashboard_section_reached` | `Layout.tsx`, both variants | `section` (first path segment, `overview` for `/`), `sections_reached_count` -- once per section per browser session |
| `landing_viewed` | landing page mount | `entry`: `experiment` (the test variant's redirect), `dashboard-nav` (brand link in the dashboard's top nav), or `direct` |
| `landing_section_viewed` | landing page, section scrolled into view | `section` (`stats`, `how`, `under-the-hood`, `doors`, `cta`, `footer`) |
| `landing_link_clicked` | brand link in the dashboard's top nav (every page) | `from` (pathname it was clicked on) |
| `landing_profile_link_clicked` | landing page footer | `kind` (`github`, `leetcode`, `linkedin`, `email`, `phone`) |
| `landing_cta_clicked` | every link out of the landing page | `target` (route), `position` (`header`, `door`, `step-score`, `hero-bucket-high`, ...) |

Set up in PostHog Cloud (the code only reads the flag): create an experiment with feature flag
key `landing-page`, variants `control` / `test` at 50/50, and metrics:

- **Primary**: mean count of `dashboard_section_reached` per user.
- **Secondary**: distinct `$pageview` pathnames per user (excluding `/welcome`); funnel from
  exposure to any `$pageview` under `/evals` or `/admin`.
- **Guardrail**: share of test users with no dashboard `$pageview` at all (landing drop-off).

Portfolio-level traffic is low, so expect it to need weeks rather than days to reach significance.

## Suggested PostHog insights

- **Exploration depth / funnel** -- distinct `$pageview` pathnames per session across
  Overview (`/`) -> Observability -> Evals -> ETL Data -> Admin.
- **Session recordings** filtered to first-time visitors.
- **Time-on-page** per tab, and scroll depth on the Overview page.

## History

This started as a self-hosted deployment: three Railway services (a PostHog app container,
ClickHouse, Kafka) backed by Railway's managed Postgres/Redis and a bucket for recordings, each
component its own `Dockerfile` + `railway.toml`, matching this repo's usual per-service
convention. It got the app fully migrated and past ClickHouse cluster/Keeper/named-collection
config, Kafka KRaft setup, and a persons-database wiring gap -- real, working infrastructure --
but the process took a long chain of one-off fixes (ClickHouse version mismatches with PostHog's
vendored config, `ON CLUSTER` DDL needing an embedded Keeper, a users.xml grants conflict, missing
`PERSONS_DB_WRITER_URL`/`PERSONS_DB_READER_URL` vars) with no end clearly in sight. Given this is
a portfolio project, not a system that needs to own its own analytics infrastructure, the call was
made to stop and switch to PostHog Cloud's free tier instead -- same product, same events, same
instrumentation code, none of the ClickHouse/Kafka operational surface. The Railway services
(and the object-storage bucket) created during that attempt have been deleted.
