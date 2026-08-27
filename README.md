# FatherOfProjects

An automated job-search pipeline: it scrapes engineering job postings from several job boards,
has an LLM agent score each one against a resume, and surfaces the results in a dashboard — so
the day-to-day job hunt is "review a ranked list of matches" instead of "manually rescan four
different career sites for anything new."

## What this actually does

1. **Scrape.** WebScraper pulls postings from Work at a Startup (YC), Greenhouse, Ashby, and
   Lever. YC's own search is already filtered to relevant roles; the other three have no
   server-side filter, so WebScraper applies its own before anything is stored: only postings
   from the last few hours (`SCRAPE_RECENCY_HOURS`), only titles that look like an engineering
   role (`SCRAPE_TITLE_KEYWORDS`), and a hard per-run cap per source (`SCRAPE_MAX_JOBS_PER_SOURCE`)
   as a backstop. Company slug lists are validated periodically (`WebScraper/scripts/
   validate_reference_slugs.py`) so dead/renamed boards don't keep getting hit for nothing.
   Anything from the three ATS sources older than a week gets purged automatically — this is a
   personal tool tracking live openings, not an archive.
2. **Score.** JobManagerAgent is a LangGraph ReAct agent: for each unscored job it crawls the full
   posting, runs it against a resume through Gemini using a versioned rubric prompt, and records a
   match score + reasoning. Because every one of those is a real, billed LLM call, the whole
   system is built around not scoring things that don't need scoring — the filtering in step 1,
   plus its own RPM budget, guardrails against prompt-injected postings, and a live/backfill split
   so a backlog never crowds out freshly scraped jobs.
3. **Iterate on the prompt safely.** The scoring prompt isn't hardcoded — it's a versioned,
   registered prompt in MLflow. Cutting over to a new version, backfilling old jobs under it, and
   comparing prompt versions against a golden eval dataset are all first-class, auditable
   operations (see the dashboard's Migration and Agent Evals tabs), not "edit a string and hope."
4. **Review.** JobDataDashboard is where the actual job hunt happens day to day: every scraped
   listing, every match with its score/reasoning, filterable by source; an ETL funnel chart
   showing what's scraped vs. processed vs. still-pending backlog per source; prompt-version and
   backfill controls; and live RPM/billing visibility so a runaway agent loop shows up immediately
   instead of as a surprise bill.

Everything above runs both as a local Docker Compose stack (for development, against its own
throwaway Postgres/Redis) and as the same set of services on Railway (production) — see
[Dev mode vs. prod mode](#dev-mode-vs-prod-mode) below.

## Services

- JobManagerAgent — the scoring agent: crawls postings, runs the resume-match prompt via Gemini,
  records results, and hosts the admin API (rate limits, prompt cutover, backfill, evals) the
  dashboard drives.
- JobDataDashboard — frontend for browsing scraped jobs and matches, the ETL funnel chart, prompt
  migrations, evals, and rate-limit/billing status.
- JobDataServer — CRUD/query API over job listings and match results that the dashboard and agent
  both read from.
- WebScraper — scrapes YC, Greenhouse, Ashby, and Lever on a schedule, filters what's actually
  worth storing, and purges what's gone stale.
- ObservabilityDashboard — dashboard for the Prometheus/Grafana metrics and logs covering the
  platform's operational health (separate concern from the ETL funnel chart above, which is about
  pipeline data, not infrastructure).
- ObservabilityServer — backend for observability data.
- MLflowServer — backs the prompt registry and eval-run tracking JobManagerAgent and the dashboard
  use for prompt versioning.
- SmokeTesting — lightweight smoke tests for the platform.

## Structure

Each service is organized as its own folder with its own code, dependencies, and deployment configuration.

## Getting started

1. Review the README in the service you want to run.
2. Set up the required environment variables for that service.
3. Start the services needed for your workflow.

## Dev mode vs. prod mode

- **Dev mode** runs the deployable services locally via Docker, orchestrated by the root
  `docker-compose.yml`. Covers JobManagerAgent, JobDataDashboard, JobDataServer, WebScraper, and
  MLflowServer. ObservabilityDashboard and ObservabilityServer are excluded (the `Observability/`
  folder has its own separate `docker-compose.yml` for Prometheus/Grafana), and SmokeTesting is a
  manual script, not a deployable service.

  `docker-compose.yml` also runs its own local Postgres and Redis containers, isolated from the
  hosted Railway instances prod uses -- dev runs never read or write prod data. Each service
  still reads its non-connection config (API keys, thresholds, etc.) from its own `.env` file --
  copy `.env.example` to `.env` in each service folder first if you don't have one --
  `docker-compose.yml` overrides `DATABASE_URL`/`REDIS_URL`/`MLFLOW_TRACKING_URI`/
  `MLFLOW_BACKEND_STORE_URI` to point at the local `postgres`/`redis`/`mlflowserver` containers
  instead of whatever's in those files. The local Postgres server holds two databases: `webscraper`
  (job_listings/job_matches, shared by JobDataServer/JobManagerAgent/WebScraper, same as prod) and
  `mlflow` (MLflowServer's backend store) -- both auto-create their schemas on first use, no
  migration step needed. Data persists in Docker volumes across restarts; `docker compose down -v`
  wipes it if you want a clean slate.

  ```powershell
  docker compose up --build                              # postgres, redis, both APIs, MLflow, dashboard
  docker compose --profile scraper run --rm webscraper   # one-shot scrape, on demand
  ```

  For an edit-and-see-it-immediately loop, use `docker compose watch` instead of `up`: it watches
  each buildable service's source and automatically syncs+restarts (Python services) or rebuilds
  (the dashboard's static build, and any service's `requirements.txt`) just the container that
  changed -- see the `develop.watch` block on each service in `docker-compose.yml`. (We tried
  Skaffold for this first, per an earlier ask -- its docker-compose deploy support is an
  unimplemented stub as of v2.24.0, confirmed by a real `skaffold run` failing with "docker
  compose not yet supported by skaffold". `docker compose watch` does the same job natively.)

  ```powershell
  docker compose watch
  ```

  Override local Postgres credentials (default `postgres`/`postgres`) via a root `.env` file next
  to `docker-compose.yml`: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`.

- **Prod mode** is Railway, driven by each service's own `railway.toml`. Unchanged by dev mode --
  the Dockerfiles Railway uses (JobDataDashboard) and the railpack build/start commands it uses
  for the rest are independent of the root `docker-compose.yml`.
