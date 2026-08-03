# FatherOfProjects

This workspace contains a multi-service job discovery and observability platform.

## Services

- JobManagerAgent — evaluates scraped jobs against a resume and writes match results.
- JobDataDashboard — frontend for viewing job data and matches.
- JobDataServer — backend service for job data access.
- WebScraper — scrapes and publishes job listing data.
- ObservabilityDashboard — dashboard for inspecting system observability data.
- ObservabilityServer — backend for observability data.
- MLflowServer — MLflow tracking server for prompt and eval experiments.
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

## Notes

- JobManagerAgent uses MLflow for prompt versioning and eval tracking.
- WebScraper feeds job listings into the downstream matching pipeline.
- Observability services provide operational insights into the system.
