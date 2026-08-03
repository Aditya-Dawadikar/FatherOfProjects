from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import create_engine

from agents.react_agent import _system_prompt
from integrations.mlflow import get_active_prompt
from tools import build_agent_tools
from utils.config import (
	DEFAULT_MODEL,
	GUARDRAIL_INJECTION_PATTERNS,
	GUARDRAIL_MAX_REASONING_CHARS,
	GUARDRAIL_TOOL_CALL_HEADROOM,
	GUARDRAIL_TOOL_CALLS_PER_JOB,
	PROMPT_FILE,
	load_match_threshold,
	load_max_jobs_per_cycle,
	load_resume,
)


router = APIRouter(prefix="/agent-topology", tags=["agent-topology"])


class AgentTopologyNode(BaseModel):
	id: str
	label: str
	kind: Literal["agent", "tool", "middleware", "guardrail", "prompt"]
	detail: str
	source: str


class AgentTopologyEdge(BaseModel):
	source: str
	target: str
	label: str | None = None


class AgentTopologyResponse(BaseModel):
	generated_at: str
	agent_name: str
	threshold: int
	max_jobs_per_cycle: int
	tool_call_limit: int
	nodes: list[AgentTopologyNode]
	edges: list[AgentTopologyEdge]


class _PromptVersionStub:
	version = "ui-inspector"
	template = ""


def _load_scoring_prompt() -> tuple[str, str]:
	try:
		active_prompt = get_active_prompt()
		return active_prompt.template, f"mlflow prompt alias production (version={active_prompt.version})"
	except Exception:
		# UI should still render if MLflow is unavailable; show local prompt template exactly as on disk.
		return PROMPT_FILE.read_text(encoding="utf-8"), "local prompt file fallback (prompts/job_match_v1.txt)"


def _build_tool_nodes() -> list[AgentTopologyNode]:
	get_jobs_tool, crawl_job_tool, evaluate_match_tool, record_result_tool, _ = build_agent_tools(
		engine=create_engine("sqlite+pysqlite:///:memory:"),
		order="newest",
		limit=1,
		threshold=70,
		prompt_name="job_match_prompt",
		prompt_version="ui-inspector",
		prompt_version_obj=_PromptVersionStub(),
		resume_text="",
		llm_client=object(),
		model_name=DEFAULT_MODEL,
		provider="gemini",
	)
	tools = [get_jobs_tool, crawl_job_tool, evaluate_match_tool, record_result_tool]
	return [
		AgentTopologyNode(
			id=f"tool:{tool.name}",
			label=tool.name,
			kind="tool",
			detail=tool.description,
			source="tools/agent_tools.py",
		)
		for tool in tools
	]


@router.get("", summary="Exact live agent topology and details")
def get_agent_topology() -> AgentTopologyResponse:
	threshold = load_match_threshold()
	max_jobs_per_cycle = load_max_jobs_per_cycle()
	tool_call_limit = max_jobs_per_cycle * GUARDRAIL_TOOL_CALLS_PER_JOB + GUARDRAIL_TOOL_CALL_HEADROOM
	resume_text = load_resume()
	agent_prompt = _system_prompt(resume_text, threshold)
	scoring_prompt, scoring_prompt_source = _load_scoring_prompt()
	tool_nodes = _build_tool_nodes()

	nodes: list[AgentTopologyNode] = [
		AgentTopologyNode(
			id="agent:react",
			label="ReAct Orchestrator Agent",
			kind="agent",
			detail=agent_prompt,
			source="agents/react_agent.py::_system_prompt",
		),
		AgentTopologyNode(
			id="middleware:guardrail",
			label="GuardrailMiddleware",
			kind="middleware",
			detail=(
				"Catches GuardrailBlockedError from tool execution, records guardrail trigger, and returns "
				"tool-shaped error feedback to the agent instead of crashing the run. Dict error format is "
				"applied for crawl_job/evaluate_match; string error format is applied for record_job_result."
			),
			source="guardrails/middleware.py",
		),
		AgentTopologyNode(
			id="middleware:tool-limit",
			label="ToolCallLimitMiddleware",
			kind="middleware",
			detail=(
				f"run_limit={tool_call_limit} (computed as max_jobs_per_cycle({max_jobs_per_cycle}) * "
				f"GUARDRAIL_TOOL_CALLS_PER_JOB({GUARDRAIL_TOOL_CALLS_PER_JOB}) + "
				f"GUARDRAIL_TOOL_CALL_HEADROOM({GUARDRAIL_TOOL_CALL_HEADROOM})); exit_behavior=error"
			),
			source="agents/react_agent.py",
		),
		AgentTopologyNode(
			id="prompt:scoring",
			label="Production Scoring Prompt",
			kind="prompt",
			detail=scoring_prompt,
			source=scoring_prompt_source,
		),
		AgentTopologyNode(
			id="guardrail:prompt-injection",
			label="prompt_injection",
			kind="guardrail",
			detail="\n".join(f"- {pattern}" for pattern in GUARDRAIL_INJECTION_PATTERNS),
			source="guardrails/injection.py + utils/config.py",
		),
		AgentTopologyNode(
			id="guardrail:empty-reasoning",
			label="empty_reasoning",
			kind="guardrail",
			detail="Blocks scoring output when reasoning is empty or whitespace.",
			source="guardrails/checks.py",
		),
		AgentTopologyNode(
			id="guardrail:oversized-reasoning",
			label="oversized_reasoning",
			kind="guardrail",
			detail=f"Blocks scoring output when reasoning exceeds {GUARDRAIL_MAX_REASONING_CHARS} characters.",
			source="guardrails/checks.py + utils/config.py",
		),
		AgentTopologyNode(
			id="guardrail:unknown-job-id",
			label="unknown_job_id",
			kind="guardrail",
			detail="Blocks crawl_job(job_id) when job_id was not returned by get_jobs_to_process.",
			source="tools/agent_tools.py",
		),
		AgentTopologyNode(
			id="guardrail:evaluate-before-crawl",
			label="evaluate_before_crawl",
			kind="guardrail",
			detail="Blocks evaluate_match(job_id) before crawl_job(job_id) has produced job detail.",
			source="tools/agent_tools.py",
		),
		AgentTopologyNode(
			id="guardrail:record-before-evaluate",
			label="record_before_evaluate",
			kind="guardrail",
			detail="Blocks record_job_result(job_id) before evaluate_match(job_id) has produced a score.",
			source="tools/agent_tools.py",
		),
		AgentTopologyNode(
			id="guardrail:tool-call-limit",
			label="tool_call_limit_exceeded",
			kind="guardrail",
			detail="Raised by ToolCallLimitMiddleware when run_limit is exceeded.",
			source="agents/react_agent.py",
		),
	]
	nodes.extend(tool_nodes)

	edges = [
		AgentTopologyEdge(source="middleware:guardrail", target="agent:react", label="middleware"),
		AgentTopologyEdge(source="middleware:tool-limit", target="agent:react", label="middleware"),
		AgentTopologyEdge(source="agent:react", target="prompt:scoring", label="evaluate_match uses"),
		AgentTopologyEdge(source="middleware:guardrail", target="guardrail:prompt-injection", label="enforces"),
		AgentTopologyEdge(source="middleware:guardrail", target="guardrail:empty-reasoning", label="enforces"),
		AgentTopologyEdge(source="middleware:guardrail", target="guardrail:oversized-reasoning", label="enforces"),
		AgentTopologyEdge(source="middleware:guardrail", target="guardrail:unknown-job-id", label="enforces"),
		AgentTopologyEdge(source="middleware:guardrail", target="guardrail:evaluate-before-crawl", label="enforces"),
		AgentTopologyEdge(source="middleware:guardrail", target="guardrail:record-before-evaluate", label="enforces"),
		AgentTopologyEdge(source="middleware:tool-limit", target="guardrail:tool-call-limit", label="enforces"),
	]
	for tool_node in tool_nodes:
		edges.append(AgentTopologyEdge(source="agent:react", target=tool_node.id, label="calls"))
		if tool_node.id == "tool:evaluate_match":
			edges.append(AgentTopologyEdge(source=tool_node.id, target="guardrail:prompt-injection", label="checks"))
			edges.append(AgentTopologyEdge(source=tool_node.id, target="guardrail:empty-reasoning", label="checks"))
			edges.append(AgentTopologyEdge(source=tool_node.id, target="guardrail:oversized-reasoning", label="checks"))
			edges.append(AgentTopologyEdge(source=tool_node.id, target="prompt:scoring", label="renders"))

	return AgentTopologyResponse(
		generated_at=datetime.now(timezone.utc).isoformat(),
		agent_name="JobManagerAgent ReAct orchestrator",
		threshold=threshold,
		max_jobs_per_cycle=max_jobs_per_cycle,
		tool_call_limit=tool_call_limit,
		nodes=nodes,
		edges=edges,
	)
