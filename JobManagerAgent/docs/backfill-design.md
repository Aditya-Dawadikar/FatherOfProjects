# Backfill Design: Rescoring Existing Matches Under a New Prompt

## Scenario

Explainability feedback on the job-matching feature ("can you show *why* a job scored what it
scored?") looked like a small UI change -- add a breakdown card to the Matches page -- but the
data behind it didn't exist yet. `job_matches` only ever stored a single opaque
`{match_score, reasoning}` per job, decided entirely by the LLM in one shot. Getting a real
breakdown meant a new rubric-based prompt, and getting that breakdown onto *existing* matched
jobs (not just future ones) meant reprocessing the historical backlog without losing what was
already there, and doing the cutover itself as a controlled, observable sequence rather than a
single risky flag flip.

## Task

Reprocess every already-matched job under a new, rubric-based prompt version, without disrupting
live scoring, without blowing the shared LLM rate-limit budget, and without discarding the
original scores. Drive the actual cutover -- old prompt to new prompt, old backfill mechanism to
new one -- as a systematic, observable sequence with a real "test on a small subset first" step,
not a single irreversible action. Build it so the next time a backfill like this is needed (this
will not be the last prompt revision), it doesn't require re-deriving the same infrastructure.

## Challenges

1. **Job posting content is stale by the time you'd want to re-score it.** `description_text`,
   `skills`, `salary_range`, etc. are never persisted -- they're crawled fresh from `job_url` at
   scoring time (`services/crawler.py:fetch_job_detail`) and only ever held in memory for that one
   call (see [../shared/job_data.py](../shared/job_data.py), which only stores identity/metadata
   fields). Backfilling means re-crawling every candidate, and a meaningful fraction of old
   postings will 404 or have changed.
2. **Rate limits are real and shared.** The same Gemini API key/project serves live scoring, the
   offline eval harness, *and* the existing "unscored jobs" backfill (`mode="backfill"` in
   [../agents/react_agent.py](../agents/react_agent.py), documented in
   [evals-mlflow-design.md](./evals-mlflow-design.md)'s "Rate limiting and backfill" section) --
   and that key/project's quota is itself shared with another application outside this repo.
3. **A new, large backfill job must not compete with that shared budget.** Reprocessing years of
   historical matches is exactly the kind of workload that could otherwise fill the RPM window and
   starve live scoring of headroom for freshly scraped jobs.
4. **The old backfill mechanism and the new one look similar but aren't the same job -- and the
   cutover between them needs to be a controlled sequence, not an implicit side effect.** The old
   mechanism (`get_jobs_to_process` / `mode="backfill"`) only ever targets jobs that have **never**
   been scored, under whatever prompt happens to be `production`-aliased at the time. Rescoring
   *already-matched* jobs under a *specific target* prompt version is a fundamentally different
   selection query -- but during the actual cutover window, we still want the ability to pause the
   old mechanism, flip the active prompt, and resume it in a known order, rather than trusting an
   implicit background race to sort itself out.
5. **This will not be the only backfill this project ever needs.** Today it's "rescore under a new
   rubric prompt." Next time it might be "recompute `company_last_active_at` for every listing" or
   "re-run a different check against every historical match." A one-off script or a single-purpose
   endpoint would need to be rebuilt (threading, progress tracking, rate limiting, all of it) every
   time.
6. **A large backfill run needs a way to be validated cheaply before committing to the whole
   backlog.** The trigger for it is explicitly a dev-facing endpoint -- there's no reason it should
   only support "process everything or nothing."
7. **The eval harness and golden dataset were built for the old response shape.** `EvalCase` had no
   place to assert anything below the single overall score, and `run_offline_eval.py` only knew how
   to score one case at a time.

## Solution

### 1. Content staleness: re-crawl, and treat "gone" as data, not failure

`backfill/processes/rescore_with_prompt.py` re-crawls each candidate's `job_url` via the same
`fetch_job_detail` the live path uses. A `NotFoundCrawlError` (HTTP 404) is recorded as an explicit
non-match row (`match_score=0, is_match=False, reasoning="not_found_404..."`) under the target
prompt version -- mirroring the exact pattern `tools/agent_tools.py`'s `crawl_job` tool already
uses on the live path -- so a delisted posting gets a real, queryable answer instead of silently
vanishing from the candidate set on every rerun. A different `CrawlError` (timeout, unparseable
page) is left **unrecorded** on purpose: it's ambiguous whether the posting is actually gone or the
crawl just had a bad moment, and guessing a score for content that was never actually read would be
worse than leaving it for a later retry.

### 2 & 3. Rate limiting: a reserved bucket enforced at the one real choke point

Every actual network call to the model funnels through one function --
`gemini_provider.py:_generate_content` -- regardless of whether it was reached via live scoring,
an eval run, or a backfill batch. That's where the RPM budget is enforced
(`RedisRpmLimiter.acquire`), and it now takes a `bucket` argument ("live" or "backfill") that
selects an **independent Redis sliding-window counter and its own cap**
(`utils/config.py:BACKFILL_RPM_CAP`, `LLM_RPM_CAP__<MODEL>__BACKFILL`), rather than sharing the
counter live scoring uses. `bucket` is threaded top-to-bottom: `score_jobs_batch()` (the only
caller backfill ever uses) passes `bucket="backfill"` into `call_scoring_model()`, which passes it
into the provider's `call_model()`, which passes it into `_generate_content()`.

**Pitfall #1, found and fixed while building this:** the first pass had `rescore_with_prompt.py`
calling `RedisRpmLimiter.acquire(..., bucket="backfill")` itself, *before* calling
`score_jobs_batch()`. That looked correct but wasn't -- `_generate_content()` was still calling
`_rpm_limiter().acquire(model)` with the default `bucket="live"` underneath, since nothing had
threaded the bucket choice down to the actual network call. The result: a backfill call would
wait on a "backfill" gate that nothing else read, *and then still* draw from and count against
the shared "live" counter it was supposed to be isolated from -- the reserved budget wasn't
actually reserving anything. The fix was to push the bucket decision down to the one place a real
API call happens and delete the caller-side `acquire()` entirely, rather than trying to layer
protection on top of a shared choke point from the outside. **Lesson: rate limiting has to be
enforced where the network call actually happens, not wherever feels like the natural call site
in the business logic -- a second gate upstream of the real one only adds latency, not
isolation.**

`BACKFILL_RPM_CAP` and `DEFAULT_RPM_CAP` are both slices of the same real external quota (checked
in the provider's own console, not guessed), not additive on top of it -- see
[evals-mlflow-design.md](./evals-mlflow-design.md)'s existing rate-limiting section for how that
external ceiling was determined.

### 4. Old backfill vs. new backfill: kept orthogonal, and now pausable for a controlled cutover

Nothing about the never-scored-jobs backfill's *selection logic* changed. It keeps draining jobs
that have no `job_matches` row under **any** prompt version, using whatever prompt is currently
`production`-aliased. Rescoring the *already-matched* backlog under a new prompt is a separate,
explicitly-triggered concern with its own candidate query (`reprocess_candidates_stmt` in
[../shared/job_match_data.py](../shared/job_match_data.py)): jobs with a `job_matches` row under
*some* version but not yet under the *target* version. The two mechanisms never compete for the
same candidates and, per the rate-limiting fix above, never compete for the same RPM budget
either -- so *correctness*-wise, neither needs the other to be paused.

What *is* new: `utils/matching_controls.py` gives an operator explicit control over the
never-scored-jobs backfill specifically (`mode="backfill"` cycles only -- live cycles are never
affected), via `POST /admin/unscored-backfill/pause` / `.../resume` / `GET .../status`. This isn't
required for correctness (see Pitfall #2 below for why the automatic path already works), but it's
what makes "shut down the old backfill, flip the prompt, hand it back" an explicit, driveable
sequence instead of an implicit race the operator has to trust -- see "Migration sequence" below
for the exact order.

This is also what makes the rollout genuinely two-speed, matching the intuition that new and old
data should "travel in two directions simultaneously": once the new prompt is set active, brand
new jobs get the rubric breakdown immediately via the normal live/old-backfill path (fast lane),
while the historical backlog gets rescored asynchronously through the new backfill framework at a
deliberately throttled pace (slow lane) -- and both can run at the same time without interfering.

**Pitfall #2, found and fixed while building this:** `get_active_prompt()` (the function every
live/old-backfill cycle calls to resolve the current prompt) used to re-diff the `production`
alias's template against `job_match_v1.txt`'s on-disk content on **every single call**, and
silently re-register + re-point the alias whenever they didn't match. That was originally a
local-dev convenience ("edit v1.txt, next cycle picks it up"), but it meant an explicit
`set_active_prompt_version()` promotion to v4 got **silently reverted back to v1 on the very next
cycle** -- once anything else was aliased, v1.txt's on-disk content permanently stopped matching
it, so the "changed" branch re-triggered forever. The fix: `get_active_prompt()` is now read-only
except for a one-time bootstrap when nothing has ever been aliased at all;
`set_active_prompt_version()` (`POST /admin/active-prompt`) is the only thing that can change what
`production` points to after that. **Lesson: an "auto-sync convenience" and an "explicit promotion
API" cannot coexist against the same mutable pointer without one silently undoing the other --
the one that changed something behind the operator's back had to go.**

One useful side effect of this fix: since `get_active_prompt()` re-resolves the alias fresh on
*every* cycle (it's just not allowed to *change* it anymore), a `POST /admin/active-prompt` call
takes effect on the very next live or backfill cycle automatically -- no restart, no deploy, no
cache to bust.

### 5. A reusable framework, not a one-off script

`backfill/` is a small plugin system, not a single-purpose endpoint:

- `backfill/registry.py` -- `BackfillProcess` (name, description, `prepare`/`select_candidates`/
  `run_one_batch` callables) and a `BACKFILL_PROCESSES` registry.
- `backfill/engine.py` -- everything generic: background-thread execution, paging into batches,
  progress/run-id tracking (`GET /backfill/runs/{run_id}`). Has zero knowledge of prompts,
  crawling, or scoring.
- `backfill/processes/rescore_with_prompt.py` -- the first (and so far only) registered process.
  A future backfill need is a new module in `backfill/processes/` registered the same way, reusing
  the engine's threading/paging/progress-tracking rather than rebuilding it.
- `api/backfill.py` -- `GET /backfill/processes` (what's available), `POST /backfill/run`
  (`{process, params, limit}`), `GET /backfill/runs/{run_id}` / `GET /backfill/runs` (progress and
  history) -- the "dev endpoint that can trigger backfill based on the process of choice." No auth
  -- it's explicitly a dev/internal-only surface, not meant to be exposed publicly.

### 6. Testing on a small subset before committing to the full job

`POST /backfill/run`'s `limit` field is exactly this: pass `limit: 5` (or 10, or whatever) to
process only that many candidates, inspect the results for real via the Matches page's detail
card (or `GET /backfill/runs/{run_id}` for the raw counts), and only then re-trigger without a
`limit` for the rest. This is a real run, not a simulation -- the rows it writes are genuine
`job_matches` rows under the target `prompt_version` -- which is the point: you're validating
actual model output quality on real jobs, not a mocked dry-run. It composes safely with a later
full run because of the idempotency in section 8 below: `reprocess_candidates_stmt` excludes
anything that already has a row under the target version, so the small test batch is never
reprocessed by the larger run that follows it, and an interrupted large run can simply be
re-triggered to pick up where it left off.

### 7. Idempotency and "less data than it looks like," for free from the schema

`job_matches`' primary key was widened from `job_id` alone to `(job_id, prompt_version)`
(`scripts/migrate_job_matches_v2.py`), so a job can hold one row per prompt version it's been
scored under instead of a rescore overwriting history. Two things fall out of that for free:

- **Idempotent reruns.** `record_job_result`'s duplicate-key `IntegrityError` is caught as a
  no-op, same as it always was -- just keyed on `(job_id, prompt_version)` now instead of
  `job_id`. Interrupting and re-triggering `POST /backfill/run` with the same `prompt_version`
  never double-processes a job that already got a row written.
- **A naturally shrinking candidate set.** `reprocess_candidates_stmt` excludes any job that
  already has a row under the target version, so the candidate set only ever contains jobs
  genuinely still needing that version -- a resumed run's remaining work is strictly smaller than
  its first attempt, without any separate "already done" bookkeeping.

The candidate query also only ever looks at jobs with **at least one existing** `job_matches` row
(any version) -- it deliberately does not reach into `job_listings` for postings that were never
successfully scored in the first place. Those are the never-scored backfill's job (see #4), not
this one's; keeping the two selections disjoint is what keeps this backfill's data volume bounded
to "the matched backlog," not "everything ever scraped."

Within that candidate set, `reprocess_candidates_stmt` orders `is_match DESC` (already-matched
jobs first) then oldest-`evaluated_at`-first -- so a `limit`-bounded or interrupted run spends its
budget on the jobs most likely to matter first.

### 8. Logs as the source of truth for progress and for the handoff itself

`backfill/engine.py` logs `backfill_candidates_selected` (once) and `backfill_batch_complete`
(per batch: rescored / not_found_404 / crawl_error / errored counts, running totals) via the
existing structured `agent_logger`, the same logging convention live cycles and eval runs already
use. `GET /backfill/runs/{run_id}` exposes the same counters for polling without needing to read
logs, but the logs remain the detailed, ordered record of exactly where a run is or where it
stopped.

The prompt cutover itself is now captured the same way -- see "Capturing the handoff in logs"
below for the exact events.

## Addendum: feature flag, RPM accounting, and safe revert

A follow-up pass turned three implicit properties of the design above into explicit, durable,
UI-observable ones: "is the new prompt a feature flag we can safely revert," "what does the RPM
budget actually look like across every process sharing it, in real time," and "can we push
backfill code without it doing anything until we ask it to."

### The feature flag *is* the active prompt version -- nothing new needed on top

`POST /admin/active-prompt` already was this: pushing `job_match_v4.txt`/`v5.txt` and the
`backfill/` code in a deploy changes nothing about live behavior on its own -- `production` still
points at whatever it pointed at before, and new code only "takes effect" when an operator
explicitly calls `POST /admin/active-prompt` (to go live) or `POST /backfill/run` (to backfill).
Deliberately not adding a second, separate boolean flag on top of the version pointer -- that
would just be two sources of truth for the same underlying state to drift apart. What *was*
missing: a one-click, provably-safe revert.

- **`POST /admin/active-prompt/revert`** re-promotes whatever `production` pointed to immediately
  before the last change, read from a new durable history
  (`integrations/mlflow/prompt_registry.py:get_active_prompt_history`, Postgres-backed, survives
  redeploys). Revert is safe by construction, not by convention: `job_matches` rows are
  permanently tagged with the `prompt_version` that actually produced them (the composite PK from
  section 7), so nothing about rows written while the version being reverted away from was active
  needs to be purged, rolled back, or reconciled -- they just stay exactly as they are, correctly
  attributed to the version that scored them. This is the "if n rows were processed, we let them
  finish and don't need to purge" assumption, now load-bearing for revert specifically, not just
  for the backfill-cancellation case it was originally stated for.
- **`GET /admin/prompts`** lists every registered version (schema_mode, whether it's currently
  active) -- the source list a feature-flag selector UI is built from, distinct from the history
  endpoint (`GET /admin/active-prompt/history`), which is "what changed and when," not "what's
  available to change to."

### Rate-limit accounting: the x+y+z+w model is now real, not aspirational

Before this pass, the offline eval harness had no bucket of its own -- `score_job()` always
defaulted to `bucket="live"`, so a triggered eval run silently competed with real live traffic for
the same RPM counter, and `score_jobs_batch()`'s `--batch-size` eval path (added for exercising
the batch-scoring code, see the "Idempotency" section) silently drew from the *backfill* bucket
instead. Neither matched the intended model. Fixed by:

- A third bucket, `"eval"` (`EVAL_RPM_CAP`, `LLM_RPM_CAP__<MODEL>__EVAL`), with `score_job()` and
  `score_jobs_batch()` both taking an explicit `bucket` parameter now (`llm_providers/__init__.py`)
  instead of one of them hardcoding it. `evals/run_offline_eval.py` passes `bucket="eval"`
  explicitly on every call site.
- `PROVIDER_RPM_QUOTA` (`utils/config.py`), an operator-set constant (from the provider's own
  console -- never guessed, same policy as every other cap in this file) that lets headroom
  (`w = quota - x - y - z`) actually be computed and shown, rather than being a purely conceptual
  fourth term nothing displayed.
- **`GET /admin/rate-limits`**: a read-only peek (`RedisRpmLimiter.current_usage` -- trims the
  sliding window like `acquire()` does, but never reserves a slot, so polling it for a dashboard
  never itself consumes budget) at current count vs. cap for all three buckets, plus computed
  headroom. This is what answers "which process gets how much capacity during the handoff, right
  now" -- the exact question a stabilization effort without it would otherwise have to answer by
  reading Redis directly under time pressure.

### Only one backfill run at a time: enforced, not just documented

The rule "when we trigger a new backfill, we must stop the existing one, so only the y allocation
is reassigned to a new process" is now enforced in `backfill/engine.py`, not just an operational
convention: `start_backfill_run()` looks up every currently-`"running"` run and requests its
cancellation *before* starting the new one. Cancellation is cooperative -- checked between batches,
never mid-batch, so an in-flight LLM call always finishes and whatever it already wrote stays
written (the same revert-without-purge principle as above, applied to a superseded run instead of
a superseded prompt version). This never touches live or eval traffic -- "y" is the only
allocation that changes hands, and it changes hands cleanly because at most one process is ever
drawing from it. `POST /backfill/runs/{run_id}/cancel` exposes the same mechanism for a manual
stop, not just automatic supersession.

### Durability: history has to survive the deploy that's the whole point of triggering it, and belongs in Postgres

Both new histories -- backfill runs (`backfill/models.py:BackfillRunRecord`) and prompt-version
changes (`integrations/mlflow/models.py:PromptActiveHistoryRecord`) -- are Postgres tables, not
in-process memory and, after a second look, not Redis either. The first pass used Redis (it was
already in reach, and the immediate problem -- in-memory state wiped on every deploy -- is
real and had to be fixed regardless). Redis was the wrong final home for it, though: this is
*audit* data (when did production change, who triggered a backfill and why), which wants the same
durability/backup guarantees `job_matches` already gets, not the fast-but-disposable
characteristics Redis is actually used for elsewhere in this codebase (RPM sliding-window
counters, the unscored-backfill pause flag) -- state that's fine to lose on a Redis restart or
flush because it's either reconstructed automatically or explicitly operator-set again. History
that's supposed to answer "what happened, and when" months from now shouldn't share that risk
profile. `BackfillRunRecord`/`PromptActiveHistoryRecord` live on the same `Base`/engine as
`job_listings`/`job_matches` (`shared/job_data.py`), created automatically via
`Base.metadata.create_all` the first time `shared.job_data.get_shared_engine()` runs -- no manual
migration needed for a new table, only for altering an existing one (contrast
`scripts/migrate_job_matches_v2.py`). `GET /backfill/runs` and `GET /admin/active-prompt/history`
are durable across restarts, Redis flushes, and Redis outages alike as a result.

## Migration sequence: the smooth handoff, step by step

This is the systematic sequence the Challenges/Solution above build toward. Each step names the
exact API call and the log line(s) that confirm it took effect.

1. **Validate the new prompt on a small subset.** `POST /backfill/run
   {"process": "rescore_with_prompt", "params": {"prompt_version": "5"}, "limit": 5}` (v5 is the
   batch-mode rubric prompt). Watch `backfill_batch_complete` in the logs, then inspect the 5 new
   rows via the Matches page's detail card (filter by prompt version 5).
2. **(Optional but recommended) Pause the never-scored-jobs backfill** for a clean cutover window:
   `POST /admin/unscored-backfill/pause {"reason": "prompt v4 cutover"}`. Confirms via the
   `unscored_backfill_paused` log line and `GET /admin/unscored-backfill/status`. Live cycles keep
   running throughout this step -- only idle-triggered backfill cycles are skipped, each logging
   `cycle_skipped_unscored_backfill_paused`.
3. **Promote the new prompt for live scoring.** `POST /admin/active-prompt {"version": "4"}` (v4
   is the single-job live-mode twin of v5, same rubric). Confirms via the
   `prompt_active_version_changed` log line, which records `from_version`/`to_version` explicitly.
4. **Resume the never-scored-jobs backfill**, now implicitly using the new prompt:
   `POST /admin/unscored-backfill/resume`. Confirms via `unscored_backfill_resumed`, and the very
   next live or backfill cycle logs `cycle_prompt_resolved` with `prompt_version` reflecting v4 --
   that log line is the definitive confirmation the handoff actually took effect end to end, not
   just that the alias moved.
5. **Backfill the rest of the historical backlog** at leisure: `POST /backfill/run
   {"process": "rescore_with_prompt", "params": {"prompt_version": "5"}}` (no `limit`). Runs
   asynchronously against the reserved RPM budget, never competing with the live traffic now
   flowing through v4. Poll `GET /backfill/runs/{run_id}` or watch `backfill_batch_complete` for
   progress.
6. **Decommission v1-v3 (and v5, once the backlog is drained)** by doing nothing further -- they
   stay registered in MLflow, just unaliased. Nothing is ever deleted.

### Capturing the handoff in logs

Directly answering "do we capture this behavior through logs": yes, as of this pass. The specific
structured (`agent_logger`, grep/query-able) events, all new or fixed in this pass except where
noted:

| Event | Where | What it confirms |
|---|---|---|
| `prompt_active_version_changed` | `prompt_registry.py:set_active_prompt_version` | The exact moment `production` moved, with `from_version`/`to_version`/`schema_mode`/`reason` ("manual" or `"revert:<version>"`) -- also durably recorded, not just logged, in `get_active_prompt_history` |
| `cycle_prompt_resolved` | `react_agent.py`, every cycle | Which prompt version *actually scored* a given live/backfill cycle -- the proof the cutover reached real scoring, not just the alias |
| `unscored_backfill_paused` / `unscored_backfill_resumed` | `admin.py` | Start/end of the controlled cutover window |
| `cycle_skipped_unscored_backfill_paused` | `react_agent.py` | Confirms the pause actually suppressed a cycle, and when |
| `backfill_candidates_selected` / `backfill_batch_complete` / `backfill_run_complete` / `backfill_run_failed` | `backfill/engine.py` (pre-existing) | Progress and outcome of the new rescore-backfill -- also durably recorded (Postgres-backed, survives redeploys) in `GET /backfill/runs`, not just logged |
| `backfill_run_superseded` | `backfill/engine.py:start_backfill_run` | A prior running run was told to stop because a new one was triggered -- the "only one at a time" rule in action |
| `backfill_run_cancelled` | `backfill/engine.py:_execute` | A run stopped cleanly between batches, either from supersession or a manual `POST /backfill/runs/{run_id}/cancel` -- `cancel_reason` distinguishes which |
| `prompt_bootstrap_registering` / `prompt_bootstrap_complete` | `prompt_registry.py` (fixed) | First-ever registration only -- should appear once per fresh deploy, never again after |

Before this pass, `prompt_active_version_changed` and `cycle_prompt_resolved` didn't exist --
prompt version was only visible as an MLflow run *parameter*, not a structured application log
event, so there was no way to grep application logs for "when did the cutover actually reach live
scoring" without cross-referencing MLflow separately. That gap is what prompted the fix in
Pitfall #2 above to be paired with explicit logging, not just a behavior change.

## Observations

- **Migrations-as-a-process, not migrations-as-a-one-off, was the real design shift.** Before this,
  a prompt/schema change and its rollout were three tightly coupled things: edit the prompt file,
  ship a UI change, hand-run whatever one-off script reprocessed old data. Treating "reprocess
  existing data under a new definition" as a first-class, named, resumable, rate-limit-aware
  process (`backfill/registry.py` + `engine.py`), and treating "which prompt is active" as an
  explicit, logged, promotable state rather than a file-diff side effect, is what turns a prompt
  migration from a bespoke event into something reproducible -- start it, pause part of it, resume
  it, and repeat the whole sequence for whatever the next migration turns out to be.
- **The composite primary key is the load-bearing decision underneath almost everything else
  here.** Idempotency, "don't reprocess what's done," side-by-side old/new scores for comparison,
  small-subset testing composing safely with a full run, and the two-speed rollout all follow
  directly from `job_matches` being able to hold more than one row per job. Getting that schema
  change right mattered more than any of the scoring/rubric logic built on top of it.
- **Both pitfalls found while building this share the same shape: a second, well-intentioned
  control layered on top of a shared mutable resource (an RPM counter, an MLflow alias) without
  verifying what the *actual* enforcement/mutation point does underneath.** In both cases the fix
  was to push the real decision down to that one point and delete the redundant/conflicting logic
  above it, rather than trying to reconcile two sources of truth. Auditing "where does the real
  side effect happen, and does every caller's intent actually reach it" is the check that would
  have caught both before they shipped.
- **`schema_mode` metadata on the prompt files (`job_match_v4.meta.json` / `v5.meta.json`)** is
  what let a *batch-shaped* prompt (`job_match_v5.txt`, backfill-only) and a *single-job-shaped*
  prompt (`job_match_v4.txt`, live) share the same rubric and the same deterministic
  aggregation (`llm_providers/base.py:compute_match_result`) without the scoring code needing to
  guess which shape it's looking at from a filename or version number. `POST /admin/active-prompt`
  reads that same metadata to refuse aliasing a batch-mode prompt live, which is the kind of
  mistake that would otherwise only surface at 2am when the ReAct agent's single-job tool call
  gets back an array it doesn't know how to parse.
- **"In-memory is fine for now" is a trap specifically for operational history -- and so, one
  level up, is reaching for whatever durable store is already open in the file.** The original
  backfill run tracking (`_RUNS: dict[...] = {}`) was reasonable for a first pass -- it worked, it
  was simple -- but it was quietly incompatible with the actual intended workflow (push code,
  deploy, check the UI) from the start, because the one event guaranteed to happen between
  "trigger a backfill" and "check on it later" is a deploy, and a deploy wipes process memory.
  The fix's *first* draft moved it to Redis, which solved the deploy problem but was still the
  wrong resource for what this data actually is -- an audit trail, not fast operational state.
  Landing on Postgres wasn't more code, just the same amount of code aimed at the store that
  actually matches the durability the data needs.

## Reference

- [../scripts/migrate_job_matches_v2.py](../scripts/migrate_job_matches_v2.py) -- one-time PK
  widening + `score_breakdown` column, run once before deploying.
- [../shared/job_match_data.py](../shared/job_match_data.py) -- composite-PK model,
  `reprocess_candidates_stmt`.
- [../prompts/job_match_v4.txt](../prompts/job_match_v4.txt) /
  [job_match_v4.meta.json](../prompts/job_match_v4.meta.json) -- live, single-job rubric prompt.
- [../prompts/job_match_v5.txt](../prompts/job_match_v5.txt) /
  [job_match_v5.meta.json](../prompts/job_match_v5.meta.json) -- backfill-only, batch rubric
  prompt (same rubric/rules as v4, different call shape).
- [../integrations/mlflow/prompt_registry.py](../integrations/mlflow/prompt_registry.py) --
  `LoadedPrompt`, `get_active_prompt` (read-only after bootstrap), `set_active_prompt_version`
  (the explicit promote-to-production path, the only thing that changes `production`),
  `revert_active_prompt_version`, `get_active_prompt_history`, `list_registered_prompt_versions`.
  All four of the `engine`-taking functions read/write
  [integrations/mlflow/models.py](../integrations/mlflow/models.py)'s `PromptActiveHistoryRecord`.
- [../shared/job_data.py](../shared/job_data.py) -- `get_shared_engine()`, the cached engine every
  API-layer call site without one already in scope (admin.py, agent_topology.py,
  mlflow_summary.py, backfill's `api/backfill.py`) uses; also where `Base.metadata.create_all`
  picks up the migration-history tables automatically.
- [../utils/matching_controls.py](../utils/matching_controls.py) -- pause/resume/status for the
  never-scored-jobs backfill specifically (Redis -- this one genuinely is operational state, not
  history; see the Durability section above for the distinction).
- [../agents/react_agent.py](../agents/react_agent.py) -- the pause check and
  `cycle_prompt_resolved` logging, both at the top of `run_matching_cycle_with_agent`.
- [../llm_providers/base.py](../llm_providers/base.py) -- `compute_match_result` (the one place a
  0-100 score is derived from raw 0-10 criteria; the LLM never computes it itself).
- [../llm_providers/__init__.py](../llm_providers/__init__.py) -- `score_job` (live by default) vs
  `score_jobs_batch` (backfill by default), both taking an explicit `bucket` override now --
  `evals/run_offline_eval.py` passes `bucket="eval"` on every call site.
- [../llm_providers/gemini_provider.py](../llm_providers/gemini_provider.py) --
  `_generate_content`, the actual RPM-enforcement choke point; takes `bucket` end to end.
- [../utils/rate_limiter.py](../utils/rate_limiter.py) -- `RedisRpmLimiter.acquire`'s `bucket`
  param, `current_usage` (the read-only peek `GET /admin/rate-limits` is built on), `RPM_BUCKETS`;
  [../utils/config.py](../utils/config.py) -- the x+y+z+w model's constants
  (`DEFAULT_RPM_CAP`/`BACKFILL_RPM_CAP`/`EVAL_RPM_CAP`/`PROVIDER_RPM_QUOTA`), `BACKFILL_BATCH_SIZE`.
- [../backfill/](../backfill/) -- `registry.py`, `engine.py` (Postgres-backed run history via
  `models.py:BackfillRunRecord`, `request_cancel`, the "only one running" supersession in
  `start_backfill_run`),
  `processes/rescore_with_prompt.py`.
- [../api/backfill.py](../api/backfill.py) -- trigger/status/history/cancel; `/runs/{run_id}/cancel`.
- [../api/admin.py](../api/admin.py) -- promote/revert/history/list-prompts, unscored-backfill
  pause/resume/status, and `GET /rate-limits`.
- [evals-mlflow-design.md](./evals-mlflow-design.md) -- the pre-existing live-cycle /
  never-scored-jobs backfill design this document deliberately does not duplicate or replace.
