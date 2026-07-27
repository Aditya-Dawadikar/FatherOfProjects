# Job Manager Agent

Reads scraped listings from the `job_listings` table (written by `WebScraper`), crawls each
job's full posting, scores it against a resume using a Groq-hosted Llama model, and writes
every evaluated job — score, reasoning, and whether it clears the bar — into a `job_matches`
table. Only jobs at/above `MATCH_THRESHOLD` are worth applying to; the rest are recorded so
they're never re-evaluated.

## How it runs

A persistent worker (not a cron job): on boot it runs one matching pass over any unevaluated
jobs, then listens on `WebScraper`'s `webscraper:events` Redis Stream (via a consumer group)
and re-runs the pass whenever a `pipeline_completed` event arrives from a fresh scrape.

```
WebScraper (cron) --xadd--> webscraper:events --xreadgroup--> JobManagerAgent
                                                                     |
                                                     job_listings ---+--- crawler.py (fetch job_url)
                                                                     |
                                                        resume.md ---+--- groq_client.py (Groq LLM call)
                                                                     |
                                                                     v
                                                              job_matches table
```

## Setup

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env`:
- `DATABASE_URL` / `REDIS_URL` — same Postgres/Redis instance `WebScraper` uses.
- `GROQ_API_KEY` — from console.groq.com.
- `MLFLOW_TRACKING_URI` — where prompt versions are tracked (local sqlite by default; point
  at a shared Postgres URL in production so versions survive redeploys).

Fill in `resume.md` with your real skills/experience/preferences — its full contents are sent
to the LLM as-is for every job evaluated, so keep it accurate.

Run locally:

```powershell
venv\Scripts\python main.py
```

## Prompt versioning

The prompt template lives in `prompts/job_match_v1.txt` (uses MLflow's `{{variable}}` syntax,
not Python's `str.format`). On every matching pass, `prompt_registry.py` checks whether that
file's content differs from the currently registered MLflow prompt version; if so, it
registers a new version and moves the `production` alias to it. `job_matches.prompt_version`
records which version produced each evaluation, so you can trace results back to a specific
prompt edit. Edit the template file directly to iterate — no manual registration step needed.

## Key files

- `crawler.py` — fetches a job's detail page and parses out the description/skills/interview
  process (same `data-page` JSON payload technique `WebScraper` uses for the listing page).
- `groq_client.py` — renders the active prompt and calls the Groq model, returning
  `{match_score, reasoning}`.
- `matcher.py` — orchestrates one evaluation pass; skips and retries next cycle on a
  per-job crawl/LLM failure rather than aborting the batch.
- `stream_consumer.py` / `stream_events.py` — Redis Stream consumer/publisher counterparts to
  `WebScraper`'s publisher.
- `shared/job_match_data.py` — the `job_matches` SQLAlchemy model and the "unevaluated jobs"
  query that makes re-runs idempotent.

## Environment variables

See `.env.example` for the full list, including `MATCH_THRESHOLD` (default 70) and
`MAX_JOBS_PER_CYCLE` (default 25, caps how many jobs one pass evaluates).
