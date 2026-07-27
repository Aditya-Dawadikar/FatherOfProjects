# Job Manager Agent

Reads scraped listings from the `job_listings` table (written by `WebScraper`), crawls each
job's full posting, scores it against a resume using an LLM, and writes every evaluated job —
score, reasoning, and whether it clears the bar — into a `job_matches` table. Only jobs
at/above `MATCH_THRESHOLD` are worth applying to; the rest are recorded so they're never
re-evaluated.

The LLM call is behind a small provider abstraction (`llm_providers/`) — a self-hosted Ollama
model (see sibling `OllamaServer/` service, the default), Groq, and Gemini are all supported
today; switching between them is a one-line env var change (`LLM_PROVIDER`), and adding another
provider means adding one more module. See "LLM provider" below.

## How it runs

A persistent worker (not a cron job): on boot it runs one matching pass over any unevaluated
jobs, then listens on `WebScraper`'s `webscraper:events` Redis Stream (via a consumer group)
and re-runs the pass whenever a `pipeline_completed` event arrives from a fresh scrape.

```
WebScraper (cron) --xadd--> webscraper:events --xreadgroup--> JobManagerAgent
                                                                     |
                                                     job_listings ---+--- crawler.py (fetch job_url)
                                                                     |
                                                        resume.md ---+--- llm_providers/ (Ollama, Groq, or Gemini)
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
   - For each candidate job, in order: sleep `LLM_REQUEST_DELAY_SECONDS` (except before the
     first) to pace LLM calls, then `_evaluate_one_job`:
     - `crawler.fetch_job_detail(job_url)` — GETs the job's detail page with a browser-like
       `User-Agent`, regexes out the `data-page="..."` attribute (a server-rendered JSON blob),
       HTML-unescapes and JSON-decodes it, and pulls `title`/`descriptionHtml`→text/
       `interviewProcessHtml`→text/`skills`/`minExperience`/`salaryRange`/etc. out of
       `payload.props.job`. Any failure here (network error, missing payload) raises
       `CrawlError`.
     - `llm_providers.render_prompt` fills the MLflow prompt template's `{{variable}}` placeholders
       with the resume text and every field pulled from the job detail.
     - `llm_providers.evaluate_match` dispatches to whichever provider module `LLM_PROVIDER`
       selects (`ollama_provider.py`, `groq_provider.py`, or `gemini_provider.py`), which calls
       that provider's API with
       `temperature=0` and JSON-mode output; `parse_match_response` then extracts
       `{match_score, reasoning}` from the reply, tolerating a model that wraps the JSON in prose
       (regex-extracts the first `{...}` block) but raising `MatchResponseError` if no valid score
       can be found.
     - A `JobMatch` row is added with `is_match = match_score >= MATCH_THRESHOLD`, the prompt
       name/version, and the model name — then **committed immediately**, before moving to the
       next job. This means a job that succeeds is permanently recorded even if a later job in
       the same cycle fails or the batch is cut short by a rate limit.
   - Error handling per job: a `RateLimitError` (each provider module maps its own SDK's
     rate-limit exception into this common one — see "LLM provider" below) stops the whole cycle
     early (`break`, preserving everything already committed) since retrying immediately would
     just burn quota against a limit that isn't going away. A `TransientProviderError` (5xx /
     overloaded / timed out / connection dropped — e.g. Gemini's "currently experiencing high
     demand" 503) is different: `evaluate_match` itself retries it up to 3 times with exponential
     backoff (2s/4s/8s) *before* it ever reaches this level, since that kind of failure often
     clears within seconds; only if it's still failing after those retries does it fall through
     to here. Both that and `CrawlError`/`MatchResponseError` roll back just that job's
     uncommitted state, count it as failed, and move on — it stays unevaluated and will be
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
             │            → LLM call (Ollama, Groq, or Gemini) → parse {match_score, reasoning}
             │            → INSERT job_matches row → commit immediately
             ├─ stop early on provider RateLimitError (progress so far stays committed)
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
- `LLM_PROVIDER` — `ollama` (default, self-hosted, see sibling `OllamaServer/`), `groq`, or
  `gemini`; only that provider's vars need filling in (see "LLM provider" below).
- `MLFLOW_TRACKING_URI` — the MLflow Tracking Server that prompt versions are registered
  against (see sibling `MLflowServer/` service). Locally, run `serve.py` in `MLflowServer/`
  and point this at its `http://localhost:5000`; in production point it at the deployed
  `MLflowServer` service's Railway internal address instead. This is required: sqlite
  tracking URIs are rejected so runs never silently land in a local file.

Fill in `resume.md` with your real skills/experience/preferences — its full contents are sent
to the LLM as-is for every job evaluated, so keep it accurate.

Run locally:

```powershell
venv\Scripts\python main.py
```

## LLM provider

Job scoring goes through `llm_providers/`, a small dispatch layer rather than a direct SDK call,
so switching which model does the scoring is a one-line env var change instead of a code change:

- `llm_providers/base.py` — provider-agnostic: `render_prompt` (fills the MLflow template),
  `parse_match_response` (extracts `{match_score, reasoning}` from a JSON reply, tolerant of a
  model that wraps it in prose), `MatchResponseError`, and two common exceptions every provider
  module raises instead of leaking its own SDK's exception type: `RateLimitError` (quota/429 —
  won't clear by retrying seconds later) and `TransientProviderError` (5xx/overloaded/timed
  out/connection dropped — often *does* clear within seconds).
- `llm_providers/ollama_provider.py` / `groq_provider.py` / `gemini_provider.py` — each
  implements `build_client()`, `load_model()`, and `call_model(client, *, model, prompt) -> str`,
  and maps its own SDK's/API's exceptions into the shared ones: rate limits
  (`groq.RateLimitError`, or Gemini's `ClientError` with `code == 429`) into `RateLimitError` —
  Ollama, self-hosted with no quota, never raises this one; server-side failures
  (`groq.InternalServerError`/`groq.APIConnectionError`, Gemini's `ServerError`, or a `requests`
  connection/timeout error or 5xx from Ollama — typically "still starting up" or "still loading
  the model into memory") into `TransientProviderError`.
- `llm_providers/__init__.py` — the facade `matcher.py`/`evals/run_offline_eval.py` actually
  import: `load_provider_name()` reads `LLM_PROVIDER` (`ollama`, `groq`, or `gemini`; defaults to
  `ollama`), and `build_client()`/`load_model_name()`/`evaluate_match()` all dispatch to whichever
  provider module that names, defaulting to it but accepting an explicit `provider=` override
  (used by the eval harness's `--provider` flag to score the same dataset through a different
  provider without touching `.env`). `evaluate_match()` also retries a `TransientProviderError` up
  to 3 times with exponential backoff (2s/4s/8s) before letting it propagate — callers only see
  one after retries are exhausted.

Adding a fourth provider means adding one more `llm_providers/<name>_provider.py` with those three
functions and registering it in `__init__.py`'s `_PROVIDERS` dict — no changes needed to
`matcher.py`, the eval harness, or anything else that calls through the facade.

Both the live agent and the eval harness log which provider/model produced a run as MLflow
params/tags (`llm_provider`, `llm_model`) — so a provider swap shows up as a comparable dimension
in MLflow rather than being invisible.

**Ollama is the default** since it has no per-request cost or rate limit — see sibling
`OllamaServer/` for the service that hosts it, including the RAM/CPU footprint of running an 8B
model on CPU (read that before deploying it). **Rate limits on the hosted providers are
provider- and plan-specific**, and can be per-minute *or* per-day (token-based).
`LLM_REQUEST_DELAY_SECONDS` only paces requests/minute — if you're seeing 429s from Groq/Gemini
despite a generous delay, check the actual error message (it names the limit type) and the
provider's usage dashboard rather than assuming pacing alone will fix it.

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

At startup and at each cycle/eval run, the agent logs the resolved MLflow target and run id,
for example: `MLflow startup target uri=...`, `action=mlflow_target ...`, and
`action=mlflow_run_started run_id=...`. If you don't see these in logs, the run never reached
MLflow logging code.

## Experiment tracking

Every call to `run_matching_cycle()` (`matcher.py`) opens one MLflow run, under the experiment
named by `MLFLOW_EXPERIMENT_NAME` (default `job_matching`), against the same Tracking Server used
for prompt versioning:

- **Params** (logged once per run): `prompt_version`, `llm_provider`, `llm_model`,
  `match_threshold`, `max_jobs_per_cycle`, `llm_request_delay_seconds`.
- **Per-job metrics** (logged with `step` = the job's index in the cycle, so a run's chart shows
  score progression across the cycle): `match_score`, `is_match`.
- **Cycle-level metrics** (logged once, at the end of the run): `candidate_count`,
  `evaluated_count`, `matched_count`, `failed_count`, `rate_limited`.

The run is tagged with `cycle_id` (matching the id in structured logs and the
`matching_cycle_completed`/`matching_cycle_failed` Redis events) so a run can be cross-referenced
back to logs or dashboard data for the same cycle.

## Offline evals

`evals/run_offline_eval.py` scores the job-match prompt/model against a fixed, labeled **golden
dataset** instead of live crawled jobs — so a prompt, model, or provider change can be checked for
regressions before it ever touches production traffic. It reuses the exact same rendering/scoring
path as the live agent (`llm_providers.render_prompt` / `evaluate_match`), so an eval result
reflects what production would actually do.

### Golden dataset schema

A JSONL file, one eval case per line:

| Field                | Type            | Required | Notes                                                                                  |
|-----------------------|-----------------|----------|-----------------------------------------------------------------------------------------|
| `id`                  | string          | yes      | Unique within the file.                                                                 |
| `job`                  | object          | yes      | Same shape `crawler.fetch_job_detail()` produces: `title`, `company_name`, `location`, `job_type`, `min_experience`, `salary_range`, `equity_range`, `sponsors_visa`, `skills` (list), `description_text`, `interview_process_text`. Inlined rather than a `job_url` so a case never depends on a live page still being reachable. |
| `expected_is_match`   | boolean         | yes      | Ground-truth pass/fail at the configured `MATCH_THRESHOLD`.                             |
| `expected_score_min`  | integer (0-100) | no       | Only if you also want to assert the score lands in a band, not just the pass/fail call. Must be set together with `expected_score_max`. |
| `expected_score_max`  | integer (0-100) | no       | See above.                                                                               |
| `resume`              | string          | no       | Overrides `resume.md` for this one case. Omit to use the real resume (the common case).  |
| `notes`                | string          | no       | Free-text rationale for the label; not used by the harness, just for maintainers.        |

See `evals/golden_dataset.example.jsonl` for a worked example (a strong match, a clear non-match,
and a borderline case scored on pass/fail only).

### Running it

```powershell
venv\Scripts\python evals\run_offline_eval.py --dataset evals\golden_dataset.jsonl
```

Useful flags: `--prompt-source local` scores `prompts/job_match_v1.txt` as it currently sits on
disk, without registering/promoting it in MLflow (the default, `production`, read-only-loads the
currently promoted alias) — use `local` to validate a prompt edit *before* the next live cycle
auto-promotes it via `prompt_registry.get_active_prompt()`. `--provider {groq,gemini}` scores the
same dataset through a specific provider regardless of `LLM_PROVIDER` — handy for comparing two
providers' MLflow runs on the exact same golden set. `--limit N` for a quick smoke test,
`--model`/`--threshold`/`--request-delay`/`--experiment-name`/`--run-name` to override the
corresponding env var for one run.

Each run logs to the `MLFLOW_EVAL_EXPERIMENT_NAME` experiment (default `job_matching_evals`,
deliberately separate from the live-cycle `job_matching` experiment since the metrics don't share
a shape): params (`prompt_version`, `llm_provider`, `llm_model`, `match_threshold`,
`dataset_case_count`), metrics (`accuracy`, `precision`, `recall`, `f1`, `score_in_range_rate`,
`mean_predicted_score`, plus raw confusion-matrix counts), the golden dataset file itself as an
artifact, and a per-case results table (`eval_results.json`) viewable in the MLflow UI for
drilling into any individual disagreement.

## Logging

All runtime logging goes through `agent_logger.py` instead of calling `logging.getLogger`
directly, so the codebase always logs three things consistently:
- **the input event** — every Redis stream entry read (`event_received`), whether or not it
  ends up triggering a cycle;
- **the action taken** — `action=...` lines for what the agent decided to do (ignore an
  event, start crawling a job, call the LLM, record a match, stop early on a rate limit, skip
  a failed job, etc.);
- **deliberate pauses** — `sleeping seconds=... reason=...` before the pacing delay between
  Groq calls, so a quiet log stream during a cycle reads as "pacing" rather than "stuck".

Every line is timestamped (stdlib `asctime`) and carries correlation ids: a `cycle_id`
(generated once per matching cycle, also included in the `matching_cycle_*` events published
to Redis) and, once a job is picked up, its `job_id` — so `grep cycle_id=<id>` pulls every log
line for one full cycle, per-job included.

The actual output destination is swappable via the `LOG_SINK` env var (`console` today,
default). To add a future sink — e.g. shipping to a Prometheus/Grafana log pipeline — add a
`LogSink` subclass in `agent_logger.py` and register it in `SINK_REGISTRY`; no call site
anywhere in the codebase needs to change.

## Key files

- `agent_logger.py` — structured logging facade (correlation ids, `event_received`/`action`/
  `sleeping` conventions) and the swappable console/future-sink configuration. See Logging
  above.
- `crawler.py` — fetches a job's detail page and parses out the description/skills/interview
  process (same `data-page` JSON payload technique `WebScraper` uses for the listing page).
- `llm_providers/` — renders the active prompt and calls whichever provider `LLM_PROVIDER`
  selects, returning `{match_score, reasoning}`. See "LLM provider" above.
- `matcher.py` — orchestrates one evaluation pass. Commits each job's `job_matches` row
  immediately after evaluating it (not once at the end of the batch), skips and retries next
  cycle on a per-job crawl/LLM-parsing failure, and stops the cycle early — without losing
  already-committed progress — if the provider returns a rate-limit error, rather than burning
  through the rest of the batch against a limit that will just keep rejecting it.
- `stream_consumer.py` / `stream_events.py` — Redis Stream consumer/publisher counterparts to
  `WebScraper`'s publisher.
- `shared/job_match_data.py` — the `job_matches` SQLAlchemy model and the "unevaluated jobs"
  query that makes re-runs idempotent.
- `evals/` — offline eval harness against a labeled golden dataset. See "Offline evals" above.

## Environment variables

See `.env.example` for the full list, including `MATCH_THRESHOLD` (default 70),
`MAX_JOBS_PER_CYCLE` (default 25, caps how many jobs one pass evaluates), `LLM_PROVIDER`
(`ollama`, `groq`, or `gemini`), and `LLM_REQUEST_DELAY_SECONDS` (default 20 — paced sleep between
consecutive LLM calls within a cycle; note some providers also enforce a *daily* token quota
that this can't help with — see "LLM provider" above).
