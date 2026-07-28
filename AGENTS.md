# AGENTS.md

## Repository overview
- This workspace contains multiple services and dashboards for job matching, scraping, observability, and UI tooling.
- The JobManagerAgent package is the main background worker for processing scraped jobs, scoring matches, and publishing events.

## Working conventions
- Prefer small, focused changes that preserve existing behavior.
- Keep imports explicit and avoid introducing redundant wrapper modules.
- When reorganizing code, preserve package boundaries by concern:
  - core for orchestration logic
  - services for external fetch/process integration
  - agents for agent-style execution paths
  - integrations for external platform adapters such as MLflow and Redis streams
  - utils for shared helpers
- Verify Python imports after structural changes with:
  - `python -c "import sys; sys.path.insert(0, '.'); import main"`
  - Run from the JobManagerAgent directory.

## Key paths
- JobManagerAgent/main.py: entry point for the worker process
- JobManagerAgent/core/: deterministic matching orchestration
- JobManagerAgent/agents/: ReAct agent execution path
- JobManagerAgent/services/: crawler and other service integrations
- JobManagerAgent/integrations/: MLflow and streaming integrations
- JobManagerAgent/utils/: shared helper modules

## Notes
- Keep environment-dependent configuration in the existing `.env`-based flow.
- Avoid introducing new top-level modules when a package already exists for the same responsibility.
