"""The first registered backfill process: re-scores jobs that already have a job_matches row
under some prompt version, but not yet under a target prompt version, using a schema_mode="batch"
prompt (e.g. job_match_v5.txt) to cut LLM call volume.

Job posting content (description, skills, salary, ...) is never persisted -- see
services/crawler.py -- so every candidate has to be re-crawled from its job_url before it can be
re-scored. These are historical, often-outdated postings, so a meaningful fraction will 404 or
fail to parse; that's handled per-job (see _run_one_batch) rather than failing the whole batch.
"""

from __future__ import annotations

from typing import Any

from integrations.mlflow import load_prompt_version
from llm_providers import score_jobs_batch
from services import CrawlError, NotFoundCrawlError, fetch_job_detail
from tools.db_tools import JobResult, ReprocessCandidate, get_reprocess_candidates, record_job_result
from utils.agent_logger import get_agent_logger
from utils.config import PROMPT_NAME

from ..registry import BackfillContext, BackfillProcess, BatchOutcome, register_process


LOGGER = get_agent_logger(__name__)

_DEFAULT_CANDIDATE_LIMIT = 500


def _prepare(*, prompt_version: str, **_ignored: Any) -> dict[str, Any]:
	"""Resolves prompt_version (a string, e.g. "5") to its MLflow prompt object + schema
	metadata once per run rather than once per batch, and fails the run fast if it isn't a
	batch-mode prompt -- score_jobs_batch would reject it per-batch anyway, but failing before
	any crawling/scoring happens is cheaper and clearer.
	"""
	loaded_prompt = load_prompt_version(prompt_version)
	if loaded_prompt.schema_mode != "batch":
		raise ValueError(
			f"rescore_with_prompt requires a schema_mode='batch' prompt version (e.g. job_match_v5.txt); "
			f"prompt_version={prompt_version!r} has schema_mode={loaded_prompt.schema_mode!r}"
		)
	return {"loaded_prompt": loaded_prompt}


def _select_candidates(
	session: Any, *, limit: int | None, prompt_version: str, **_ignored: Any
) -> list[ReprocessCandidate]:
	return get_reprocess_candidates(session, target_prompt_version=prompt_version, limit=limit or _DEFAULT_CANDIDATE_LIMIT)


def _run_one_batch(
	session: Any,
	batch: list[ReprocessCandidate],
	*,
	context: BackfillContext,
	prompt_version: str,
	loaded_prompt: Any,
	**_ignored: Any,
) -> BatchOutcome:
	crawled: list[tuple[int, dict[str, Any]]] = []
	not_found = 0
	crawl_error = 0

	for candidate in batch:
		if not candidate.job_url:
			LOGGER.action("backfill_no_job_url", job_id=candidate.job_id)
			crawl_error += 1
			continue
		try:
			detail = fetch_job_detail(candidate.job_url)
		except NotFoundCrawlError as error:
			# Mirrors tools/agent_tools.py's crawl_job NotFoundCrawlError handling: the posting is
			# gone, so it's recorded as an explicit non-match under the target prompt_version rather
			# than silently skipped -- a future backfill run won't keep re-selecting it as a
			# candidate once this row exists.
			record_job_result(
				session,
				JobResult(
					job_id=candidate.job_id,
					match_score=0,
					is_match=False,
					reasoning=f"not_found_404 job_url={candidate.job_url}; {error}",
					prompt_name=PROMPT_NAME,
					prompt_version=prompt_version,
					rubric_version=loaded_prompt.rubric_version,
					model_name=context.model,
				),
			)
			not_found += 1
			continue
		except CrawlError as error:
			# Transient/unparseable -- left uncrawled (no row written) so a later backfill run can
			# retry it, rather than guessing a score for content we couldn't actually read.
			LOGGER.action("backfill_crawl_failed", job_id=candidate.job_id, job_url=candidate.job_url, error=str(error))
			crawl_error += 1
			continue

		crawled.append((candidate.job_id, detail))

	if not crawled:
		return BatchOutcome(not_found_404=not_found, crawl_error=crawl_error)

	# No explicit RPM acquire here -- score_jobs_batch() itself makes the one LLM call this batch
	# needs with bucket="backfill" (see llm_providers/__init__.py), which is what actually gates
	# against the reserved backfill RPM counter at the real network-call choke point
	# (gemini_provider.py:_generate_content). Gating here too would be redundant, not additive.
	scores = score_jobs_batch(
		client=context.llm_client,
		model=context.model,
		provider=context.provider,
		loaded_prompt=loaded_prompt,
		resume=context.resume_text,
		jobs=crawled,
		threshold=context.threshold,
	)

	rescored = 0
	errored = 0
	for job_id, _detail in crawled:
		score = scores.get(job_id)
		if score is None:
			# Excluded from the batch response by score_jobs_batch (injection screen or output
			# guardrail) -- left unrecorded so a later run retries it, same reasoning as CrawlError.
			errored += 1
			continue
		written = record_job_result(
			session,
			JobResult(
				job_id=job_id,
				match_score=score.match_score,
				is_match=score.is_match,
				reasoning=score.reasoning,
				prompt_name=PROMPT_NAME,
				prompt_version=prompt_version,
				rubric_version=loaded_prompt.rubric_version,
				model_name=context.model,
				score_breakdown=score.score_breakdown,
			),
		)
		if written:
			rescored += 1

	return BatchOutcome(rescored=rescored, not_found_404=not_found, crawl_error=crawl_error, errored=errored)


register_process(
	BackfillProcess(
		name="rescore_with_prompt",
		description=(
			"Re-scores jobs that already have a job_matches row under some prompt version, but not "
			"yet under params.prompt_version, using a schema_mode='batch' prompt (e.g. "
			"job_match_v5.txt). Prioritizes previously-matched jobs first. Re-crawls each job's "
			"current posting (never persisted) and records a non-match for postings that have since "
			"been taken down (HTTP 404) instead of guessing a score. params: {prompt_version: str}."
		),
		prepare=_prepare,
		select_candidates=_select_candidates,
		run_one_batch=_run_one_batch,
	)
)
