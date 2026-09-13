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
  dashboard's *operator* changes real system state.

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
