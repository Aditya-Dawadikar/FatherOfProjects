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

## The entire flow, step by step

**1. Process boots (`main.py`).** `load_dotenv` reads `.env`, logging is configured, and a
`RedisStreamPublisher` is created (`stream_events.py`) — this is JobManagerAgent's own outbound
channel, `jobmanageragent:events`, separate from the stream it *listens* on. If `REDIS_URL`
isn't set, `from_env()` returns `None` and every publish becomes a no-op; the agent still runs,
it just can't announce what it did.

**2. Boot-time catch-up cycle.** Before touching Redis consumption at all, `main()` calls
`run_cycle_safely(publisher, reason="startup")`, which immediately runs one full matching cycle
(see step 4). This guarantees that any jobs written by `WebScraper` while JobManagerAgent was
down (redeploys, crashes, etc.) get picked up on the next boot instead of waiting for a live
`pipeline_completed` event.

**3. Enter the listen loop (`stream_consumer.py`).** `RedisStreamConsumer.run_forever` first
calls `ensure_group()`, which does `XGROUP CREATE webscraper:events jobmanageragent-group $
MKSTREAM` — creating the stream/group if they don't exist, starting from "only new messages"
(`$`), or silently continuing if the group already exists (`BUSYGROUP` is swallowed). It then
loops forever on `XREADGROUP ... BLOCK 10000 COUNT 10`, i.e. "give me up to 10 new entries for
this consumer, and block for up to 10s waiting if there are none." A `TimeoutError`/
`ConnectionError` from that blocking read (e.g. a cloud provider silently dropping an idle
socket) is caught and just retried rather than crashing the process.

**4. An event arrives.** `WebScraper`'s own cron pipeline (`job_runner.py`) writes a sequence of
`stage_started`/`stage_completed` events and finally an `event_type=pipeline_completed` entry to
`webscraper:events` once it has scraped and upserted jobs into `job_listings`. Every entry
JobManagerAgent reads is dispatched to `_handle_entry`; only `event_type in
{"pipeline_completed"}` triggers `on_trigger`, everything else (the stage-level events) is
acknowledged (`XACK`) and ignored. Any exception raised while handling a triggering entry is
logged (not re-raised) and the entry is still ack'd in a `finally` — a bad/unexpected message
can't get the consumer stuck reprocessing it forever.

**5. `on_trigger` runs another matching cycle**, this time with `reason="pipeline_completed"` —
same code path as the boot-time one.

**6. Inside `run_matching_cycle` (`matcher.py`), per cycle:**
   - Opens a DB session against `DATABASE_URL`/`POSTGRES_URL` and ensures the ORM tables exist
     (`Base.metadata.create_all`).
   - Loads `resume.md` verbatim (this is the literal text sent to the LLM every time).
   - Calls `get_active_prompt()` (`prompt_registry.py`): reads `prompts/job_match_v1.txt` off
     disk, compares it against the MLflow prompt version currently aliased `production`, and if
     the file changed (or nothing is registered yet), registers a new version and re-points the
     alias — so editing the prompt file is the entire versioning workflow, no manual step.
   - Runs `unevaluated_job_ids_stmt(max_jobs)` (`shared/job_match_data.py`): every
     `job_listings.job_id` that has **no** row in `job_matches`, newest-updated first, capped at
     `MAX_JOBS_PER_CYCLE`. This is what makes cycles idempotent/resumable — a job is only ever
     evaluated once, ever, regardless of how many cycles run.
   - For each candidate job, in order: sleep `GROQ_REQUEST_DELAY_SECONDS` (except before the
     first) to pace Groq calls, then `_evaluate_one_job`:
     - `crawler.fetch_job_detail(job_url)` — GETs the job's detail page with a browser-like
       `User-Agent`, regexes out the `data-page="..."` attribute (a server-rendered JSON blob),
       HTML-unescapes and JSON-decodes it, and pulls `title`/`descriptionHtml`→text/
       `interviewProcessHtml`→text/`skills`/`minExperience`/`salaryRange`/etc. out of
       `payload.props.job`. Any failure here (network error, missing payload) raises
       `CrawlError`.
     - `groq_client.render_prompt` fills the MLflow prompt template's `{{variable}}` placeholders
       with the resume text and every field pulled from the job detail.
     - `groq_client.evaluate_match` calls the Groq chat-completions API
       (`temperature=0`, `response_format=json_object`) and `parse_match_response` extracts
       `{match_score, reasoning}` from the JSON reply, tolerating a model that wraps the JSON in
       prose (regex-extracts the first `{...}` block) but raising `MatchResponseError` if no
       valid score can be found.
     - A `JobMatch` row is added with `is_match = match_score >= MATCH_THRESHOLD`, the prompt
       name/version, and the model name — then **committed immediately**, before moving to the
       next job. This means a job that succeeds is permanently recorded even if a later job in
       the same cycle fails or the batch is cut short by a rate limit.
   - Error handling per job: `RateLimitError` from Groq stops the whole cycle early (`break`,
     preserving everything already committed) since retrying immediately would just burn quota
     against a limit that isn't going away; `CrawlError`/`MatchResponseError` roll back just that
     job's uncommitted state, count it as failed, and move on — it stays unevaluated and will be
     retried on the next cycle (startup or next `pipeline_completed`).
   - At the end, publishes `matching_cycle_completed` (or `matching_cycle_failed`, from
     `run_cycle_safely`'s outer `except`) to `jobmanageragent:events` with counts:
     `candidate_count`, `evaluated_count`, `matched_count`, `failed_count`, `rate_limited`. No
     other service in this repo currently consumes that stream — it's there for a future
     notifier/dashboard, or for manual inspection via `XRANGE`.

**7. Loop back to step 3** and block again until the next `pipeline_completed` event.

```
WebScraper cron job
   └─ scrapes + upserts job_listings
   └─ XADD webscraper:events {event_type: pipeline_completed, ...}
                    │
                    ▼
JobManagerAgent (long-running process)
   ├─ boot: run one matching cycle immediately (catch-up)
   └─ XREADGROUP (blocking, consumer group) on webscraper:events
        └─ on pipeline_completed → run_matching_cycle()
             ├─ query job_listings LEFT ANTI JOIN job_matches → unevaluated jobs (capped, newest first)
             ├─ per job: sleep(pacing) → crawl job_url → render prompt (resume + job fields)
             │            → Groq chat completion → parse {match_score, reasoning}
             │            → INSERT job_matches row → commit immediately
             ├─ stop early on Groq RateLimitError (progress so far stays committed)
             ├─ skip+continue on CrawlError / MatchResponseError (retried next cycle)
             └─ XADD jobmanageragent:events {event_type: matching_cycle_completed, counts...}
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
- `MLFLOW_TRACKING_URI` — the MLflow Tracking Server that prompt versions are registered
  against (see sibling `MLflowServer/` service). Locally, run `serve.py` in `MLflowServer/`
  and point this at its `http://localhost:5000`; in production point it at the deployed
  `MLflowServer` service's Railway internal address instead.

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

Prompt versions are tracked by an MLflow Tracking Server — see the sibling `MLflowServer/`
service. Run it locally (`serve.py`, served at `http://localhost:5000`) for dev, and point
`MLFLOW_TRACKING_URI` at its deployed Railway internal address in production, so versions are
tracked centrally instead of in a per-instance local file that wouldn't survive a redeploy or
be visible from anywhere else. The client-side calls are identical either way; only the URI
changes.

## Key files

- `crawler.py` — fetches a job's detail page and parses out the description/skills/interview
  process (same `data-page` JSON payload technique `WebScraper` uses for the listing page).
- `groq_client.py` — renders the active prompt and calls the Groq model, returning
  `{match_score, reasoning}`.
- `matcher.py` — orchestrates one evaluation pass. Commits each job's `job_matches` row
  immediately after evaluating it (not once at the end of the batch), skips and retries next
  cycle on a per-job crawl/LLM-parsing failure, and stops the cycle early — without losing
  already-committed progress — if Groq returns a rate-limit error, rather than burning through
  the rest of the batch against a limit that will just keep rejecting it.
- `stream_consumer.py` / `stream_events.py` — Redis Stream consumer/publisher counterparts to
  `WebScraper`'s publisher.
- `shared/job_match_data.py` — the `job_matches` SQLAlchemy model and the "unevaluated jobs"
  query that makes re-runs idempotent.

## Environment variables

See `.env.example` for the full list, including `MATCH_THRESHOLD` (default 70),
`MAX_JOBS_PER_CYCLE` (default 25, caps how many jobs one pass evaluates), and
`GROQ_REQUEST_DELAY_SECONDS` (default 20 — paced sleep between consecutive Groq calls within a
cycle, capping throughput at 3 calls/minute to match a 3-requests-per-minute Groq plan; adjust
to match your actual plan's limit).
