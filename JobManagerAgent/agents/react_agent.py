from __future__ import annotations

from typing import Any, Literal

import mlflow
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.errors import GraphRecursionError

from guardrails.middleware import GuardrailMiddleware
from guardrails.report import record_guardrail_trigger
from integrations.mlflow import PROMPT_NAME, get_active_prompt
from integrations.streaming import RedisStreamPublisher, publish_event
from llm_providers import build_client, load_provider_name
from shared.job_data import Base, create_db_engine, load_database_url
from tools import build_agent_tools
from utils.agent_logger import get_agent_logger, new_id
from utils.config import (
	DEFAULT_MODEL,
	GUARDRAIL_TOOL_CALL_HEADROOM,
	GUARDRAIL_TOOL_CALLS_PER_JOB,
	MAX_OUTPUT_TOKENS,
	RECURSION_LIMIT_HEADROOM,
	STEPS_PER_JOB,
	THINKING_LEVEL,
	load_match_threshold,
	load_max_jobs_per_cycle,
	load_resume,
)
from utils.env_utils import load_env_value
from utils.mlflow_utils import (
	ensure_tracking_uri_configured,
	get_tracking_uri,
	load_mlflow_experiment_name,
	set_experiment_safely,
)
from utils.rate_limiter import LangChainRedisRpmLimiter


Mode = Literal["live", "backfill"]

LOGGER = get_agent_logger(__name__)
_ORDER_BY_MODE: dict[Mode, str] = {"live": "newest", "backfill": "oldest"}


def build_llm(model: str) -> ChatGoogleGenerativeAI:
	"""The model driving the ReAct loop's own orchestration decisions (which tool to call next).
	Actual job scoring happens through the evaluate_match tool instead, which calls
	llm_providers.score_job -- the single scoring definition the offline eval harness also uses,
	inheriting its full safety net (RPM limiter, cooldown+fallback-to-gemini-3.6-flash, the
	thinking_level/max_output_tokens truncation fix, rate-limit retries) without re-deriving any
	of it here.

	This orchestration model still needs its own RPM protection and truncation fix, since it
	makes its own real calls to decide each tool call -- reused here rather than re-derived, but
	NOT covered by gemini_provider.py's cooldown+fallback (that's evaluate_match's job).
	"""
	return ChatGoogleGenerativeAI(
		model=model,
		google_api_key=load_env_value("GEMINI_API_KEY"),
		temperature=0,
		max_output_tokens=MAX_OUTPUT_TOKENS,
		thinking_level=THINKING_LEVEL,
		rate_limiter=LangChainRedisRpmLimiter(model=model),
	)


def _system_prompt(resume_text: str, threshold: int) -> str:
	return (
		"You are a job-matching orchestrator with four tools: get_jobs_to_process, crawl_job, "
		"evaluate_match, and record_job_result. You do not score jobs yourself -- evaluate_match "
		"runs the production job-matching model and prompt for you. Your job is deciding which "
		"job to work on next and calling the right tool in the right order.\n\n"
		"Workflow, for the batch returned by get_jobs_to_process:\n"
		"1. Call get_jobs_to_process exactly once to fetch this cycle's batch of jobs (job_id, "
		"job_role, company_name only -- no posting detail yet).\n"
		"2. For each job_id returned, call crawl_job(job_id) to fetch its full posting detail. "
		"If the result contains an \"error\" key, that job is already handled (or unfetchable) -- "
		"skip straight to the next job_id, do not call evaluate_match for it.\n"
		"3. Otherwise, call evaluate_match(job_id). It returns {\"match_score\", \"reasoning\"} "
		"computed by the production model -- if it contains an \"error\" key instead, skip that "
		"job_id, do not call record_job_result for it.\n"
		"4. Otherwise, call record_job_result(job_id) to persist that evaluation. You do not need "
		"to pass match_score or reasoning yourself -- record_job_result uses what evaluate_match "
		"already computed. Do not call it more than once for the same job_id.\n"
		f"5. A job counts as a match at match_score >= {threshold}; this is handled for you.\n"
		"6. Once every job_id from get_jobs_to_process has gone through this (crawl, evaluate, "
		"record -- or been skipped on error), stop. Do not call get_jobs_to_process a second time "
		"in this session, and do not call any tool once you are finished -- just reply that "
		"you're done.\n\n"
		f"Candidate resume (for your own context; evaluate_match already has it):\n{resume_text}"
	)


def run_matching_cycle_with_agent(
	publisher: RedisStreamPublisher | None = None,
	*,
	cycle_id: str | None = None,
	mode: Mode = "live",
) -> dict[str, Any]:
	cycle_id = cycle_id or new_id()
	log = LOGGER.bind(cycle_id=cycle_id, mode=mode)

	engine = create_db_engine(load_database_url())
	Base.metadata.create_all(engine)

	max_jobs = load_max_jobs_per_cycle()
	order = _ORDER_BY_MODE[mode]
	threshold = load_match_threshold()
	resume_text = load_resume()
	prompt_version_obj = get_active_prompt()
	prompt_version = str(prompt_version_obj.version)
	model_name = DEFAULT_MODEL
	provider = load_provider_name()
	# Separate from the ChatGoogleGenerativeAI instance below: this is the raw google-genai
	# client llm_providers.evaluate_match expects, used only inside the evaluate_match tool so
	# that job scoring goes through gemini_provider.py's real call path (RPM limiter,
	# cooldown+fallback, truncation fix) instead of the ReAct model's own generation.
	llm_client = build_client(provider)

	ensure_tracking_uri_configured()
	experiment_name = load_mlflow_experiment_name()
	set_experiment_safely(experiment_name)
	log.action("mlflow_target", tracking_uri=get_tracking_uri(), experiment_name=experiment_name)

	get_jobs_tool, crawl_job_tool, evaluate_match_tool, record_result_tool, stats = build_agent_tools(
		engine=engine,
		order=order,
		limit=max_jobs,
		threshold=threshold,
		prompt_name=PROMPT_NAME,
		prompt_version=prompt_version,
		prompt_version_obj=prompt_version_obj,
		resume_text=resume_text,
		llm_client=llm_client,
		model_name=model_name,
		provider=provider,
	)
	llm = build_llm(model_name)
	# Runaway-loop guardrail: caps total real tool calls this cycle, independent of the graph-step
	# recursion_limit below (which also bounds pure reasoning turns that make no tool call at all).
	# exit_behavior="error" raises ToolCallLimitExceededError instead of silently truncating the
	# cycle, so it's caught and recorded the same way GraphRecursionError already is.
	tool_call_limit = max_jobs * GUARDRAIL_TOOL_CALLS_PER_JOB + GUARDRAIL_TOOL_CALL_HEADROOM
	agent = create_agent(
		llm,
		tools=[get_jobs_tool, crawl_job_tool, evaluate_match_tool, record_result_tool],
		system_prompt=_system_prompt(resume_text, threshold),
		middleware=[
			GuardrailMiddleware(engine=engine),
			ToolCallLimitMiddleware(run_limit=tool_call_limit, exit_behavior="error"),
		],
	)

	with mlflow.start_run(run_name=f"cycle-{cycle_id}"):
		run = mlflow.active_run()
		if run is not None:
			log.action("mlflow_run_started", run_id=run.info.run_id)
		run_id = run.info.run_id if run is not None else None
		mlflow.set_tags(
			{
				"cycle_id": cycle_id,
				"mode": mode,
				"prompt_name": PROMPT_NAME,
				"llm_provider": "gemini",
			}
		)
		mlflow.log_params(
			{
				"prompt_version": prompt_version,
				"llm_provider": "gemini",
				"llm_model": model_name,
				"match_threshold": threshold,
				"max_jobs_per_cycle": max_jobs,
			}
		)

		recursion_limit = max_jobs * STEPS_PER_JOB + RECURSION_LIMIT_HEADROOM
		incomplete = False
		error_message: str | None = None
		with mlflow.start_span(
			name="matching_cycle_agent",
			span_type="AGENT",
			attributes={"cycle_id": cycle_id, "mode": mode, "llm_model": model_name},
			run_id=run_id,
		) as cycle_span:
			cycle_span.set_inputs(
				{
					"cycle_id": cycle_id,
					"mode": mode,
					"max_jobs_per_cycle": max_jobs,
					"match_threshold": threshold,
					"recursion_limit": recursion_limit,
				}
			)
			try:
				agent.invoke(
					{"messages": [HumanMessage(content="Begin.")]},
					config={"recursion_limit": recursion_limit},
				)
			except GraphRecursionError:
				incomplete = True
				log.action("agent_recursion_limit_hit", recursion_limit=recursion_limit, **stats)
			except ToolCallLimitExceededError as error:
				incomplete = True
				record_guardrail_trigger(
					engine=engine,
					guardrail="tool_call_limit_exceeded",
					category="tool_usage",
					reason=str(error),
				)
				log.action("agent_tool_call_limit_hit", tool_call_limit=tool_call_limit, **stats)
			except Exception as error:
				error_message = str(error)
				log.exception("Agent cycle raised an unexpected error")

			result: dict[str, Any] = {
				"candidate_count": stats["candidate_count"],
				"evaluated_count": stats["evaluated_count"],
				"matched_count": stats["matched_count"],
				"failed_count": len(stats["crawl_failed_job_ids"]) + len(stats["evaluate_failed_job_ids"]),
				"not_found_count": len(stats["not_found_jobs"]),
				"not_found_jobs_sample": stats["not_found_jobs"][:10],
				"incomplete": incomplete,
			}
			if error_message:
				result["error"] = error_message
			mlflow.log_metrics(
				{
					"candidate_count": result["candidate_count"],
					"evaluated_count": result["evaluated_count"],
					"matched_count": result["matched_count"],
					"failed_count": result["failed_count"],
					"not_found_count": result["not_found_count"],
					"incomplete": int(incomplete),
				}
			)
			cycle_span.set_outputs(result)
			# Persisted as a run tag (not just logged) so a future consumer can read it back to
			# link out to this cycle's trace in the MLflow UI -- the span object itself only lives
			# for the duration of this process (see the matching fix for offline eval runs in
			# evals/run_offline_eval.py).
			mlflow.set_tag("trace_id", cycle_span.trace_id)
			log.action("mlflow_trace_ready", trace_id=cycle_span.trace_id)

		mlflow.flush_trace_async_logging(terminate=False)

	log.action("cycle_complete", **result)
	publish_event(publisher, "matching_cycle_completed", cycle_id=cycle_id, mode=mode, **result)
	return result
