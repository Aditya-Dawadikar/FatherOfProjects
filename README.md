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

## Notes

- JobManagerAgent uses MLflow for prompt versioning and eval tracking.
- WebScraper feeds job listings into the downstream matching pipeline.
- Observability services provide operational insights into the system.
