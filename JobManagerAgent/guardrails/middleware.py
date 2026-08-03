from __future__ import annotations

import json
from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from sqlalchemy import Engine

from .errors import GuardrailBlockedError
from .report import record_guardrail_trigger


# Tools whose established return shape on failure is a JSON {"error": ...} object (crawl_job,
# evaluate_match) vs. record_job_result, the one real tool that returns a bare status string
# (tools/agent_tools.py's _record_job_result_impl) -- a guardrail-blocked call keeps whichever
# shape the tool would have used on its own error path, so the agent's "if error key present,
# skip" contract from the system prompt still holds no matter which layer raised the block.
_DICT_ERROR_TOOLS = {"crawl_job", "evaluate_match"}


class GuardrailMiddleware(AgentMiddleware):
	"""LangGraph-native guardrail enforcement for the ReAct agent's tool layer.

	Wraps every tool call so a GuardrailBlockedError raised from inside a tool -- score_job()'s
	output-validation/injection checks running during evaluate_match, or a tool-usage-contract
	violation raised directly by tools/agent_tools.py (evaluate before crawl, record before
	evaluate, an unknown/hallucinated job_id) -- is recorded (Prometheus counter + guardrail_
	triggers audit row, see report.py) and converted into the same {"error": ...}-shaped feedback
	the agent already knows how to react to, instead of crashing the run.

	This is the single custom middleware in the stack; the separate runaway-loop guardrail is
	enforced at the graph level by the built-in ToolCallLimitMiddleware (see agents/react_agent.py),
	not here -- wrap_tool_call only ever sees calls the graph already decided to make.
	"""

	def __init__(self, *, engine: Engine) -> None:
		super().__init__()
		self._engine = engine

	def wrap_tool_call(
		self,
		request: ToolCallRequest,
		handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
	) -> ToolMessage | Command[Any]:
		try:
			return handler(request)
		except GuardrailBlockedError as error:
			record_guardrail_trigger(
				engine=self._engine,
				guardrail=error.guardrail,
				category=error.category,
				job_id=error.job_id,
				reason=error.reason,
			)
			tool_name = request.tool_call["name"]
			content = json.dumps({"error": error.reason}) if tool_name in _DICT_ERROR_TOOLS else error.reason
			return ToolMessage(content=content, tool_call_id=request.tool_call["id"], status="error")
