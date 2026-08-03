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

  Each service reads its own secrets (DB/Redis/API keys) from its own `.env` file -- copy
  `.env.example` to `.env` in each service folder first if you don't have one. Those values stay
  whatever you've configured there (by default the same hosted Railway Postgres/Redis used in
  prod); `docker-compose.yml` only overrides the vars needed for containers to reach each other
  (e.g. `MLFLOW_TRACKING_URI`, the dashboard's API upstreams).

  ```powershell
  docker compose up --build                              # dashboard + both APIs + MLflow
  docker compose --profile scraper run --rm webscraper   # one-shot scrape, on demand
  ```

- **Prod mode** is Railway, driven by each service's own `railway.toml`. Unchanged by dev mode --
  the Dockerfiles Railway uses (JobDataDashboard) and the railpack build/start commands it uses
  for the rest are independent of the root `docker-compose.yml`.

## Notes

- JobManagerAgent uses MLflow for prompt versioning and eval tracking.
- WebScraper feeds job listings into the downstream matching pipeline.
- Observability services provide operational insights into the system.
