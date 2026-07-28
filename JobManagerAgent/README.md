# Job Manager Agent

Reads scraped listings from the `job_listings` table (written by `WebScraper`), crawls each
job's full posting, scores it against a resume using an LLM, and writes every evaluated job —
score, reasoning, and whether it clears the bar — into a `job_matches` table. Only jobs
at/above `MATCH_THRESHOLD` are worth applying to; the rest are recorded so they're never
re-evaluated.

The LLM call is behind a small provider abstraction (`llm_providers/`) — Gemini is the only
provider today; adding another means adding one more module. See "LLM provider" below.

## How it runs

A persistent worker (not a cron job), always doing one of two things: on boot, and whenever a
`pipeline_completed` event arrives on `WebScraper`'s `webscraper:events` Redis Stream, it runs a
**live** matching cycle over the newest unevaluated jobs; whenever that stream is idle, instead of
waiting doing nothing it runs a **backfill** cycle over the *oldest* unevaluated jobs, so the
historical backlog always keeps draining. Both modes share the same idempotent query/write path
(`tools/db_tools.py`) and the same LLM call budget (`rate_limiter.py`), so it's safe for either to
pick up a job the other left behind.

```
WebScraper (cron) --xadd--> webscraper:events --xreadgroup--> JobManagerAgent
                                                                     |
                                                     job_listings ---+--- crawler.py (fetch job_url)
                                                                     |
                                                        resume.md ---+--- llm_providers/ (Gemini)
                                                                     |
                                                        rate_limiter.py (per-model RPM budget)
                                                                     |
                                                                     v
                                                              job_matches table

event arrives  -> mode="live"     -> newest-unevaluated-first
stream idle    -> mode="backfill" -> oldest-unevaluated-first
```

## The entire flow, step by step

**1. Process boots (`main.py`).** `load_dotenv` reads `.env`, logging is configured, and a
`RedisStreamPublisher` is created (`stream_events.py`) — this is JobManagerAgent's own outbound
channel, `jobmanageragent:events`, separate from the stream it *listens* on. If `REDIS_URL`
isn't set, `from_env()` returns `None` and every publish becomes a no-op; the agent still runs,
it just can't announce what it did.

**2. Boot-time catch-up cycle.** Before touching Redis consumption at all, `main()` calls
`run_cycle_safely(publisher, reason="startup", mode="live")`, which immediately runs one full
matching cycle (see step 6). This guarantees that any jobs written by `WebScraper` while
JobManagerAgent was down (redeploys, crashes, etc.) get picked up on the next boot instead of
waiting for a live `pipeline_completed` event.

**3. Enter the listen loop (`stream_consumer.py`).** `RedisStreamConsumer.run_forever` first
calls `ensure_group()`, which does `XGROUP CREATE webscraper:events jobmanageragent-group $
MKSTREAM` — creating the stream/group if they don't exist, starting from "only new messages"
(`$`), or silently continuing if the group already exists (`BUSYGROUP` is swallowed). It then
loops forever on `XREADGROUP ... BLOCK 10000 COUNT 10`, i.e. "give me up to 10 new entries for
this consumer, and block for up to 10s waiting if there are none." A `TimeoutError`/
`ConnectionError` from that blocking read (e.g. a cloud provider silently dropping an idle
socket) is caught and just retried rather than crashing the process. **If the block times out
with nothing to read, the agent is not idle** — it calls `on_idle`, which runs one
`mode="backfill"` cycle over the oldest unevaluated jobs (step 6, oldest-first instead of
newest-first) before blocking again, so historical backlog keeps draining whenever there's no
live trigger to handle.

**4. An event arrives.** `WebScraper`'s own cron pipeline (`job_runner.py`) writes a sequence of
`stage_started`/`stage_completed` events and finally an `event_type=pipeline_completed` entry to
`webscraper:events` once it has scraped and upserted jobs into `job_listings`. Every entry
JobManagerAgent reads is dispatched to `_handle_entry`; only `event_type in
{"pipeline_completed"}` triggers `on_trigger`, everything else (the stage-level events) is
acknowledged (`XACK`) and ignored. Any exception raised while handling a triggering entry is
logged (not re-raised) and the entry is still ack'd in a `finally` — a bad/unexpected message
can't get the consumer stuck reprocessing it forever.

**5. `on_trigger` runs another matching cycle**, this time with `reason="pipeline_completed"`,
`mode="live"` — same code path as the boot-time one.

**6. Inside `run_matching_cycle_with_agent(mode=...)` (`react_agent.py`), per cycle:**
   - Opens a DB session against `DATABASE_URL`/`POSTGRES_URL` and ensures the ORM tables exist
     (`Base.metadata.create_all`).
   - Loads `resume.md` verbatim (this is the literal text sent to the LLM every time) and calls
     `get_active_prompt()` (`prompt_registry.py`): reads `prompts/job_match_v1.txt` off disk,
     compares it against the MLflow prompt version currently aliased `production`, and if the
     file changed (or nothing is registered yet), registers a new version and re-points the alias
     — so editing the prompt file is the entire versioning workflow, no manual step.
   - Builds the 4 tools for this one cycle (`tools/agent_tools.py`'s `build_agent_tools`), bound to
     this cycle's DB engine, `mode`-derived ordering, `MAX_JOBS_PER_CYCLE` limit, and
     `MATCH_THRESHOLD` — the agent doesn't get to choose any of those, only *which* job to work on
     next and *when* to call each tool:
     - `get_jobs_to_process` — same anti-join query as before (`tools/db_tools.py`): every
       `job_listings.job_id` with **no** row in `job_matches`, capped at `MAX_JOBS_PER_CYCLE`,
       newest-updated first for `mode="live"`, oldest-updated first for `mode="backfill"`. This is
       what makes cycles idempotent/resumable regardless of mode.
     - `crawl_job(job_id)` — `crawler.fetch_job_detail(job_url)`: GETs the job's detail page with a
       browser-like `User-Agent`, regexes out the `data-page="..."` attribute (a server-rendered
       JSON blob), HTML-unescapes and JSON-decodes it, and pulls `title`/`descriptionHtml`→text/
       `interviewProcessHtml`→text/`skills`/`minExperience`/`salaryRange`/etc. out of
       `payload.props.job`. A 404 is recorded immediately as a non-match (`reasoning` prefixed
       `not_found_404 ...`) and returned to the agent as an error to skip; any other crawl failure
       is also returned as an error rather than raised, so one bad job can't crash the cycle.
     - `evaluate_match(job_id)` — **not** the LLM's own judgment: it calls
       `llm_providers.score_job`, the exact same scoring pipeline the offline eval harness uses.
       That renders the active MLflow prompt template with the resume + crawled job fields, then
       `gemini_provider.py`'s `call_model` acquires a slot from `rate_limiter.py`'s per-model
       requests-per-minute budget (`LLM_RPM_CAP__<MODEL>`, a Redis sliding window shared with
       offline evals), calls the API with `temperature=0` and JSON-mode output, and
       `parse_match_response` extracts `{match_score, reasoning}` — tolerating a model that wraps
       the JSON in prose, but raising `MatchResponseError` if no valid score can be found.
     - `record_job_result(job_id)` — persists what `evaluate_match` already computed (the agent
       never retypes a score) as a `JobMatch` row with `is_match = match_score >= MATCH_THRESHOLD`,
       **committed immediately**, so a job that succeeds stays recorded even if a later job in the
       same cycle fails. A duplicate `job_id` (e.g. live and backfill both reaching the same job)
       is a safe no-op via the table's primary key, not an error.
   - Builds the orchestrator LLM (`build_llm`) and a LangGraph ReAct agent (`create_agent`) over
     those 4 tools, with a system prompt spelling out the exact call order (get_jobs_to_process
     once, then crawl → evaluate → record per job, skipping a job_id on any tool error) — then
     invokes it once per cycle with `recursion_limit = max_jobs * STEPS_PER_JOB +
     RECURSION_LIMIT_HEADROOM`, bounding how many turns a model that gets stuck reasoning in
     circles can burn before the cycle is cut off (`GraphRecursionError`, caught and treated as an
     incomplete-not-crashed cycle — whatever jobs weren't reached stay unevaluated for next time).
   - `RateLimitError`/`TransientProviderError`/`MatchResponseError` raised inside `evaluate_match`
     are already retried with backoff by `llm_providers.evaluate_match` itself (up to 2 rate-limit
     retries, up to 3 transient retries) before the tool ever returns; if still failing, the tool
     returns `{"error": ...}` to the agent instead of raising, so the agent just skips that job_id
     and moves on rather than the whole cycle aborting.
   - At the end, publishes `matching_cycle_completed` (or `matching_cycle_failed`, from
     `run_cycle_safely`'s outer `except`) to `jobmanageragent:events` with `mode` plus counts:
     `candidate_count`, `evaluated_count`, `matched_count`, `failed_count`, `not_found_count`,
     `incomplete`, plus `not_found_jobs_sample` (up to 10 structured entries with
     `job_id/job_url/job_role/company_name/reason`) for quick verification.

**7. Loop back to step 3** and block again — either for the next `pipeline_completed` event, or
another idle timeout that starts another backfill cycle.

```
WebScraper cron job
   └─ scrapes + upserts job_listings
   └─ XADD webscraper:events {event_type: pipeline_completed, ...}
                    │
                    ▼
JobManagerAgent (long-running process)
   ├─ boot: run one mode="live" matching cycle immediately (catch-up)
   └─ XREADGROUP (blocking, consumer group) on webscraper:events
        ├─ on pipeline_completed → run_matching_cycle_with_agent(mode="live")
        └─ on idle timeout       → run_matching_cycle_with_agent(mode="backfill")
             ├─ LangGraph ReAct agent, 4 tools, invoked once, recursion_limit-bounded:
             │     get_jobs_to_process (once)  → job_listings LEFT ANTI JOIN job_matches
             │                                    (capped; newest-first for live, oldest-first
             │                                    for backfill)
             │     crawl_job(job_id)            → fetch + parse job posting detail
             │     evaluate_match(job_id)       → score_job(): rate_limiter.acquire(model)
             │                                    [blocks under the RPM budget if needed] →
             │                                    render prompt → LLM call (Gemini) → parse
             │                                    {match_score, reasoning} -- not the agent's
             │                                    own judgment
             │     record_job_result(job_id)    → INSERT job_matches row → commit immediately
             ├─ any tool error (rate limit / crawl / parse failure, retried inline first) →
             │     that tool returns {"error": ...}, agent skips the job_id and continues
             ├─ GraphRecursionError (stuck reasoning) → cycle ends early, marked incomplete
             │     -- unreached jobs stay unevaluated for the next cycle, not lost
             └─ XADD jobmanageragent:events {event_type: matching_cycle_completed, mode, counts...}
```

## Setup

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env`:
- `DATABASE_URL` / `REDIS_URL` — same Postgres/Redis instance `WebScraper` uses.
- `LLM_PROVIDER` — `gemini` (the only supported value; see "LLM provider" below).
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

Job scoring goes through `llm_providers/`, a small dispatch layer rather than a direct SDK call.
Gemini is the only supported provider today — `load_provider_name()` reads `LLM_PROVIDER` (must
be `gemini`; anything else raises `ValueError`) and `_provider_module()` resolves it to
`gemini_provider`:

- `llm_providers/base.py` — provider-agnostic: `render_prompt` (fills the MLflow template),
  `parse_match_response` (extracts `{match_score, reasoning}` from a JSON reply, tolerant of a
  model that wraps it in prose), `MatchResponseError`, and two common exceptions the provider
  module raises instead of leaking the underlying SDK's exception type: `RateLimitError`
  (quota/429 — won't clear by retrying seconds later) and `TransientProviderError`
  (5xx/overloaded/timed out/connection dropped — often *does* clear within seconds).
- `llm_providers/gemini_provider.py` — implements `build_client()`, `load_model()`, and
  `call_model(client, *, model, prompt) -> str`. Maps Gemini's `ClientError` with `code == 429`
  into `RateLimitError` and its `ServerError` into `TransientProviderError`. Also owns two other
  things: a Redis-backed cooldown that switches to a fallback model (`GEMINI_MODEL` →
  `gemini-3.6-flash`) for a configurable window after the primary model errors, and — before
  every actual network call, primary or fallback — acquiring a slot from `rate_limiter.py`'s
  per-model requests-per-minute budget (see "Environment variables" below).
- `llm_providers/__init__.py` — the facade `tools/agent_tools.py`/`evals/run_offline_eval.py`
  actually import: `load_provider_name()`, and `build_client()`/`load_model_name()`/`evaluate_match()` all
  dispatch through `gemini_provider`, accepting an explicit `provider=` override (used by the
  eval harness's `--provider` flag, though `gemini` is currently the only accepted value there
  too). `evaluate_match()` also retries a `TransientProviderError` up to 3 times with exponential
  backoff (2s/4s/8s) before letting it propagate — callers only see one after retries are
  exhausted.

Adding a second provider would mean adding another `llm_providers/<name>_provider.py` with those
three functions and extending `_provider_module()`'s resolution — the shared exception/rendering
contract in `base.py` is already provider-agnostic, only the dispatch is currently hardcoded to
reject anything but `gemini`.

Both the live agent and the eval harness log which provider/model produced a run as MLflow
params/tags (`llm_provider`, `llm_model`) — so a provider or model swap shows up as a comparable
dimension in MLflow rather than being invisible.

**Rate limits are quota- and plan-specific**, and can be per-minute *or* per-day (token-based).
Every real Gemini call — the ReAct agent's `evaluate_match` tool and the offline eval harness
alike, since both go through the single `llm_providers.score_job`/`evaluate_match` pipeline — is
paced by the `LLM_RPM_CAP__<MODEL>` budget in `rate_limiter.py`, not a fixed sleep. The
orchestrator LLM driving the agent's own tool-call decisions (`build_llm` in `react_agent.py`)
draws from the same per-model Redis budget too, via `LangChainRedisRpmLimiter`.
Set it from your actual quota (e.g. https://aistudio.google.com/rate-limit for Gemini) rather than
the shipped default, especially if the API key is shared with another application. If you're still
seeing 429s despite that, check the actual error message (it names the limit type) and the
provider's usage dashboard.

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

For a deeper design write-up of the eval and MLflow flow, see [docs/evals-mlflow-design.md](docs/evals-mlflow-design.md).

Every call to `run_matching_cycle_with_agent(mode=...)` (`react_agent.py`) opens one MLflow run —
whether or not it finds any candidate jobs, since candidates aren't known until the agent's first
tool call, by which point the run has already started — under the experiment named by
`MLFLOW_EXPERIMENT_NAME` (default `job_matching`), against the same Tracking Server used for
prompt versioning:

- **Params** (logged once per run): `prompt_version`, `llm_provider`, `llm_model`,
  `match_threshold`, `max_jobs_per_cycle`.
- **Cycle-level metrics** (logged once, at the end of the run): `candidate_count`,
  `evaluated_count`, `matched_count`, `failed_count`, `not_found_count`, `incomplete` (the
  `GraphRecursionError` cutoff fired before every candidate was reached).

The run is tagged with `cycle_id` and `mode` (`live` or `backfill` — filter the MLflow runs table
by this to review either separately, and watch `candidate_count` trend downward on `backfill`
runs as evidence the historical backlog is draining), matching the id in structured logs and the
`matching_cycle_completed`/`matching_cycle_failed` Redis events, so a run can be cross-referenced
back to logs or dashboard data for the same cycle.

### Traces (end-to-end visibility)

Runs/metrics alone do **not** create MLflow Traces; traces only appear when the code creates
spans (`mlflow.start_span` / `@mlflow.trace`). The agent and eval harness now emit:

- Root span per run (`matching_cycle_agent` span_type=AGENT for the live agent, `offline_eval`
  span_type=EVALUATOR for evals) linked to the active MLflow run id.
- Child span per tool call for the live agent (`tools/agent_tools.py`): `tool:get_jobs_to_process`
  (once per cycle), then `tool:crawl_job` / `tool:evaluate_match` / `tool:record_job_result` per
  job — span_type=TOOL, inputs=the tool's arguments, outputs=its return value or `{"error": ...}`.
  For evals, one `eval_case` span_type=TASK per dataset row instead.
- Inputs/outputs on spans so each step's request/result shape is inspectable in Trace view — this
  is the place to check whether `evaluate_match` actually got a clean `{match_score, reasoning}`
  back or an `error` (e.g. from the Gemini truncation issue — see `gemini_provider.py`'s
  `MAX_OUTPUT_TOKENS`/`THINKING_LEVEL` comment).

Tracing env knobs:

- `MLFLOW_TRACE_SAMPLING_RATIO=1.0` to capture every trace.
- `MLFLOW_ENABLE_ASYNC_TRACE_LOGGING=true` (default). Code explicitly flushes trace buffers at
  cycle/eval boundaries via `mlflow.flush_trace_async_logging()`.

If you only saw experiment runs before, that's expected behavior without span instrumentation.

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
auto-promotes it via `prompt_registry.get_active_prompt()`. `--provider gemini` explicitly pins
the provider for one run regardless of `LLM_PROVIDER` — currently `gemini` is the only accepted
value. `--limit N` for a quick smoke test,
`--model`/`--threshold`/`--experiment-name`/`--run-name` to override the corresponding env var
for one run.

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
  event, start crawling a job, call the LLM, record a match, retry after a rate limit, skip
  a failed job, etc.);
- **deliberate pauses** — `sleeping seconds=... reason=...` for the RPM budget wait
  (`rate_limiter.py`) or a rate-limit retry backoff, so a quiet log stream during a cycle reads as
  "pacing" rather than "stuck".

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
- `agents/react_agent.py` — builds and invokes the LangGraph ReAct agent for one cycle, either
  `mode="live"` (newest-first) or `mode="backfill"` (oldest-first): loads the resume/prompt,
  builds the 4 tools and the orchestrator LLM, then runs the agent under a bounded
  `recursion_limit` so a model stuck reasoning in circles can't burn the RPM budget indefinitely.
- `tools/agent_tools.py` — the 4 tools themselves (`get_jobs_to_process`, `crawl_job`,
  `evaluate_match`, `record_job_result`), each traced as its own MLflow span. `evaluate_match`
  wraps `llm_providers.score_job` rather than letting the model score freeform; commits each
  job's `job_matches` row immediately after `record_job_result` (not once at the end of the
  batch), and returns `{"error": ...}` instead of raising on a per-job crawl/LLM-parsing/rate-limit
  failure, so the agent skips just that job_id and continues rather than the whole cycle aborting.
- `rate_limiter.py` — Redis-backed sliding-window requests-per-minute budget, one per LLM model,
  shared by live cycles, backfill cycles, and offline evals so none of them can push total usage
  past a self-imposed cap that's deliberately set below the provider's real quota.
- `tools/db_tools.py` — the two DB operations every cycle uses instead of inlining SQL:
  `get_jobs_to_process` (the anti-join query, newest- or oldest-first) and `record_job_result`
  (idempotent write — a duplicate `job_id` is a safe no-op via the table's primary key, not an
  error). This is also what makes live and backfill cycles safely interchangeable: both go through
  the same two functions, so "what counts as unevaluated" and "how a result gets persisted" are
  each defined in exactly one place.
- `stream_consumer.py` / `stream_events.py` — Redis Stream consumer/publisher counterparts to
  `WebScraper`'s publisher. `RedisStreamConsumer.run_forever` also takes an `on_idle` callback,
  invoked whenever the blocking read times out with nothing new — this is what drives backfill
  cycles during quiet periods.
- `shared/job_match_data.py` — the `job_matches` SQLAlchemy model. Its `unevaluated_job_ids_stmt`
  helper predates `tools/db_tools.py` and is no longer used by the live agent (superseded by
  `get_jobs_to_process`), but is left in place since it's part of `shared`'s public exports.
- `evals/` — offline eval harness against a labeled golden dataset. See "Offline evals" above.

## Environment variables

See `.env.example` for the full list, including `MATCH_THRESHOLD` (default 70),
`MAX_JOBS_PER_CYCLE` (default 5 — kept small because the RPM budget below, not batch size, is
what actually limits throughput; a big batch would just tie up one cycle for many minutes without
checking for new live-trigger events), `LLM_RPM_CAP__<MODEL>` (e.g.
`LLM_RPM_CAP__GEMINI_3_5_FLASH`, default 4 — the per-model requests-per-minute budget enforced by
`rate_limiter.py`; set this from your actual quota in the provider's console, not the default,
especially if the API key is shared with another application), and `LLM_PROVIDER` (`gemini` only —
see "LLM provider" above). Note some providers also enforce a *daily* token quota that the RPM
budget alone can't help with — see "LLM provider" above.
