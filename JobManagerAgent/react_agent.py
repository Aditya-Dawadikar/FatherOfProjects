from __future__ import annotations

from typing import Any, Literal

import mlflow
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.errors import GraphRecursionError

from agent_logger import get_agent_logger, new_id
from env_utils import load_env_value
from llm_providers.gemini_provider import DEFAULT_MODEL, MAX_OUTPUT_TOKENS, THINKING_BUDGET
from matcher import load_match_threshold, load_max_jobs_per_cycle, load_resume
from mlflow_utils import ensure_tracking_uri_configured, get_tracking_uri, load_mlflow_experiment_name
from prompt_registry import PROMPT_NAME, get_active_prompt
from rate_limiter import LangChainRedisRpmLimiter
from shared.job_data import Base, create_db_engine, load_database_url
from stream_events import RedisStreamPublisher, publish_event
from tools import build_agent_tools


Mode = Literal["live", "backfill"]

LOGGER = get_agent_logger(__name__)
_ORDER_BY_MODE: dict[Mode, str] = {"live": "newest", "backfill": "oldest"}

# Bounds the ReAct loop: 1 turn to call get_jobs_to_process, up to max_jobs turns to call
# record_job_result (one per job), plus headroom for the model's own reasoning turns and a
# final "I'm done" turn. Without a cap, a model that gets stuck reasoning in circles could burn
# the RPM budget indefinitely on a single cycle.
_RECURSION_LIMIT_HEADROOM = 6


def build_llm(model: str) -> ChatGoogleGenerativeAI:
	"""Same safety properties as gemini_provider.py's non-agentic call path: the per-model RPM
	budget (rate_limiter.py) gates every real call via the `rate_limiter` hook, and the same
	thinking_budget/max_output_tokens values that fixed the response-truncation incident are
	reused here rather than re-derived. Not preserved from gemini_provider.py: the
	cooldown+fallback-to-gemini-3.6-flash behavior on repeated errors -- that's provider-module
	specific and isn't wired into this path yet.
	"""
	return ChatGoogleGenerativeAI(
		model=model,
		google_api_key=load_env_value("GEMINI_API_KEY"),
		temperature=0,
		max_output_tokens=MAX_OUTPUT_TOKENS,
		thinking_budget=THINKING_BUDGET,
		rate_limiter=LangChainRedisRpmLimiter(model=model),
	)


def _system_prompt(resume_text: str, threshold: int) -> str:
	return (
		"You are a job-matching assistant with two tools: get_jobs_to_process and "
		"record_job_result.\n\n"
		"Workflow:\n"
		"1. Call get_jobs_to_process exactly once to fetch this cycle's batch of jobs.\n"
		"2. For each job returned, compare it against the candidate's resume below and decide a "
		"match_score from 0 (no fit) to 100 (excellent fit), with a short reasoning covering the "
		"main factors (skills, experience level, role type, etc).\n"
		"3. Call record_job_result once per job with its job_id, your match_score, and your "
		"reasoning. Do not call it more than once for the same job_id, and do not call it for a "
		"job_id you were not given.\n"
		f"4. A job counts as a match at match_score >= {threshold}, but you don't need to compute "
		"that yourself -- just report the score.\n"
		"5. Once every job returned by get_jobs_to_process has been recorded, stop. Do not call "
		"get_jobs_to_process a second time in this session, and do not call any tool once you are "
		"finished -- just reply that you're done.\n\n"
		f"Candidate resume:\n{resume_text}"
	)


def run_matching_cycle_with_agent(
	publisher: RedisStreamPublisher | None = None,
	*,
	cycle_id: str | None = None,
	mode: Mode = "live",
) -> dict[str, Any]:
	cycle_id = cycle_id or new_id()
	log = LOGGER.bind(cycle_id=cycle_id, mode=mode, engine="react_agent")

	engine = create_db_engine(load_database_url())
	Base.metadata.create_all(engine)

	max_jobs = load_max_jobs_per_cycle()
	order = _ORDER_BY_MODE[mode]
	threshold = load_match_threshold()
	resume_text = load_resume()
	prompt_version_obj = get_active_prompt()
	prompt_version = str(prompt_version_obj.version)
	model_name = DEFAULT_MODEL

	ensure_tracking_uri_configured()
	experiment_name = load_mlflow_experiment_name()
	mlflow.set_experiment(experiment_name)
	log.action("mlflow_target", tracking_uri=get_tracking_uri(), experiment_name=experiment_name)

	get_jobs_tool, record_result_tool, stats = build_agent_tools(
		engine=engine,
		order=order,
		limit=max_jobs,
		threshold=threshold,
		prompt_name=PROMPT_NAME,
		prompt_version=prompt_version,
		model_name=model_name,
	)
	llm = build_llm(model_name)
	agent = create_agent(
		llm,
		tools=[get_jobs_tool, record_result_tool],
		system_prompt=_system_prompt(resume_text, threshold),
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
				"engine": "react_agent",
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

		recursion_limit = max_jobs * 2 + _RECURSION_LIMIT_HEADROOM
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
			except Exception as error:
				error_message = str(error)
				log.exception("Agent cycle raised an unexpected error")

			result: dict[str, Any] = {
				"candidate_count": stats["candidate_count"],
				"evaluated_count": stats["evaluated_count"],
				"matched_count": stats["matched_count"],
				"failed_count": len(stats["crawl_failed_job_ids"]),
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
			log.action("mlflow_trace_ready", trace_id=cycle_span.trace_id)

		mlflow.flush_trace_async_logging(terminate=False)

	log.action("cycle_complete", **result)
	publish_event(publisher, "matching_cycle_completed", cycle_id=cycle_id, mode=mode, engine="react_agent", **result)
	return result
