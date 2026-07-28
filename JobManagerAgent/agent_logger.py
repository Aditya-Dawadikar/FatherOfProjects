from __future__ import annotations

import logging
import os
import sys
import uuid
from abc import ABC, abstractmethod
from typing import Any


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def new_id() -> str:
	"""Short id used to correlate every log line emitted for one matching cycle."""
	return uuid.uuid4().hex[:12]


class LogSink(ABC):
	"""A destination for log records. `configure_logging` picks one sink (by name, via the
	LOG_SINK env var) and installs it as the only handler on the root logger, so every module
	that logs through the stdlib `logging` package - including third-party libraries like
	google-genai/urllib3/sqlalchemy - is routed through it uniformly.

	To add a future sink (e.g. shipping structured logs to a Prometheus/Grafana log pipeline
	or Loki), add a subclass here and register it in SINK_REGISTRY below. No call site
	anywhere in the codebase needs to change - only the LOG_SINK env var.
	"""

	@abstractmethod
	def build_handler(self) -> logging.Handler: ...


class ConsoleLogSink(LogSink):
	"""Default sink for local dev and the current Railway deployment: plain stdout, one line
	per record, human-readable."""

	def build_handler(self) -> logging.Handler:
		handler = logging.StreamHandler(sys.stdout)
		handler.setFormatter(logging.Formatter(LOG_FORMAT))
		return handler


SINK_REGISTRY: dict[str, type[LogSink]] = {
	"console": ConsoleLogSink,
	# "prometheus": PrometheusLogSink,  # future: push/expose metrics+logs for Grafana
}


def configure_logging(level: int = logging.INFO) -> None:
	sink_name = os.getenv("LOG_SINK", "console").strip().lower()
	sink_cls = SINK_REGISTRY.get(sink_name, ConsoleLogSink)

	root = logging.getLogger()
	root.setLevel(level)
	root.handlers = [sink_cls().build_handler()]


def _format_fields(fields: dict[str, Any]) -> str:
	return " ".join(f"{key}={value!r}" for key, value in fields.items())


class AgentLogger(logging.LoggerAdapter):
	"""Structured logging facade used across JobManagerAgent instead of calling
	`logging.getLogger` directly. Two things it gives every call site for free:

	1. Correlation ids/context (cycle_id, job_id, entry_id, ...) bound once via `.bind()` and
	   then automatically prefixed onto every subsequent message from that logger, so a single
	   matching cycle's log lines - and, per job, that job's crawl/LLM/commit steps - can be
	   grepped/traced together.
	2. Consistent verbs for the three things we always want visible: an incoming event
	   (`event_received`), what the agent decided to do about it (`action`), and any
	   deliberate pause (`sleeping`) - so "is it processing or stuck" is always answerable
	   from the log stream alone.

	The actual output destination is controlled separately by `configure_logging`/LOG_SINK;
	this class only shapes the message, it never touches handlers/sinks itself.
	"""

	def bind(self, **context: Any) -> "AgentLogger":
		return AgentLogger(self.logger, {**self.extra, **context})

	def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
		if self.extra:
			prefix = " ".join(f"{key}={value}" for key, value in self.extra.items())
			msg = f"{prefix} {msg}"
		return msg, kwargs

	def event_received(self, *, event_type: str, entry_id: str, **fields: Any) -> None:
		self.info("event_received event_type=%s entry_id=%s %s", event_type, entry_id, _format_fields(fields))

	def action(self, action_name: str, **fields: Any) -> None:
		self.info("action=%s %s", action_name, _format_fields(fields))

	def sleeping(self, seconds: float, *, reason: str, **fields: Any) -> None:
		self.info("sleeping seconds=%.1f reason=%s %s", seconds, reason, _format_fields(fields))


def get_agent_logger(name: str, **context: Any) -> AgentLogger:
	return AgentLogger(logging.getLogger(name), context)
