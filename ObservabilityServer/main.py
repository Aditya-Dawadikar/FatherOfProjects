from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import deque
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError


LOGGER = logging.getLogger(__name__)
ENV_FILE = Path(__file__).with_name(".env")
load_dotenv(ENV_FILE)

DEFAULT_STREAMS = ("webscraper:events", "jobdataserver:events")
LOG_LIMIT = 20
EVENT_LIMIT = 10
WINDOW_SECONDS = 300
ERROR_WINDOW_SECONDS = 900
BLOCK_MS = 5_000

TRACKED_NODES = (
	"scrape-yc-script",
	"scraped-data-table",
	"data-server-backend",
	"redis-stream",
	"observability-server",
	"observability-dashboard",
)

TRACKED_EDGES = (
	"scraper-to-scraped-db",
	"data-server-to-scraped-db",
	"scraper-to-redis",
	"data-server-to-redis",
	"redis-to-observability-server",
	"observability-server-to-dashboard",
)


def utc_now() -> datetime:
	return datetime.now(timezone.utc)


def utc_now_iso() -> str:
	return utc_now().isoformat().replace("+00:00", "Z")


def parse_iso_timestamp(value: str | None) -> datetime | None:
	if not value:
		return None
	try:
		return datetime.fromisoformat(value.replace("Z", "+00:00"))
	except ValueError:
		return None


def to_time_label(value: str | None) -> str:
	parsed = parse_iso_timestamp(value)
	if parsed is None:
		return "--:--:--"
	return parsed.astimezone(timezone.utc).strftime("%H:%M:%S")


def humanize_event_type(event_type: str | None) -> str:
	if not event_type:
		return "unknown"
	return event_type.replace("_", " ")


def parse_stream_value(value: str) -> Any:
	if value == "":
		return ""
	if value in {"true", "false"}:
		return value == "true"
	if value[0] in "[{\"":
		with suppress(json.JSONDecodeError):
			return json.loads(value)
	with suppress(ValueError):
		if "." in value:
			return float(value)
		return int(value)
	return value


def parse_fields(fields: dict[str, str]) -> dict[str, Any]:
	return {key: parse_stream_value(value) for key, value in fields.items()}


def event_level(event_type: str, payload: dict[str, Any]) -> str:
	if event_type.endswith("failed") or payload.get("error_message"):
		return "error"
	if "warning" in event_type:
		return "warning"
	return "info"


def summarize_payload(payload: dict[str, Any]) -> str:
	parts: list[str] = []
	for key in ("stage", "job_id", "job_count", "written_count", "error_type", "error_message"):
		value = payload.get(key)
		if value in (None, ""):
			continue
		parts.append(f"{key}={value}")
	return " ".join(parts)


def build_log_message(stream_name: str, event_type: str, payload: dict[str, Any]) -> str:
	summary = summarize_payload(payload)
	message = f"{stream_name} · {humanize_event_type(event_type)}"
	if summary:
		message = f"{message} · {summary}"
	return message


def build_event_detail(payload: dict[str, Any]) -> str | None:
	summary = summarize_payload(payload)
	return summary or None


def dedupe_event_id(stream_name: str, entry_id: str) -> str:
	return f"{stream_name}:{entry_id}"


def trend_for_count(count: int) -> str:
	if count == 0:
		return "flat"
	if count < 3:
		return "down"
	return "up"


@dataclass
class NodeRuntimeState:
	last_seen_at: str | None = None
	last_event_type: str | None = None
	last_payload: dict[str, Any] = field(default_factory=dict)
	logs: deque[dict[str, str]] = field(default_factory=lambda: deque(maxlen=LOG_LIMIT))
	events: deque[dict[str, str]] = field(default_factory=lambda: deque(maxlen=EVENT_LIMIT))
	activity: deque[float] = field(default_factory=deque)
	warnings: deque[float] = field(default_factory=deque)
	errors: deque[float] = field(default_factory=deque)


@dataclass
class EdgeRuntimeState:
	last_seen_at: str | None = None
	activity: deque[float] = field(default_factory=deque)
	status: str = "idle"


class ObservabilityState:
	def __init__(self, redis_url: str | None, streams: list[str]):
		self._redis_url = redis_url
		self._stream_names = streams
		self._redis: Redis | None = None
		self._poller_task: asyncio.Task[None] | None = None
		self._lock = asyncio.Lock()
		self._subscribers: set[asyncio.Queue[str]] = set()
		self._last_ids = {stream_name: "$" for stream_name in streams}
		self._nodes = {node_id: NodeRuntimeState() for node_id in TRACKED_NODES}
		self._edges = {edge_id: EdgeRuntimeState() for edge_id in TRACKED_EDGES}
		self._stream_activity: deque[float] = deque()
		self._stream_errors: deque[float] = deque()
		self._events_seen_total = 0
		self._last_event_id: str | None = None
		self._last_event_at: str | None = None
		self._last_stream_name: str | None = None
		self._sse_dispatch_count = 0
		self._last_dispatch_at: str | None = None

	async def start(self) -> None:
		if not self._redis_url:
			LOGGER.warning("REDIS_URL was not provided; the observability server will start in idle mode")
			return

		self._redis = Redis.from_url(self._redis_url, decode_responses=True)
		await self._seed_from_recent_entries()
		self._poller_task = asyncio.create_task(self._poll_streams(), name="observability-stream-poller")

	async def stop(self) -> None:
		if self._poller_task is not None:
			self._poller_task.cancel()
			with suppress(asyncio.CancelledError):
				await self._poller_task
		if self._redis is not None:
			await self._redis.aclose()

	async def snapshot(self) -> dict[str, Any]:
		async with self._lock:
			node_snapshots = [self._build_node_snapshot(node_id, state) for node_id, state in self._nodes.items()]
			edge_snapshots = [self._build_edge_snapshot(edge_id, state) for edge_id, state in self._edges.items()]
			system_status, avg_health = self._build_system_health(node_snapshots)
			return {
				"nodes": node_snapshots,
				"edges": edge_snapshots,
				"system": {
					"status": system_status,
					"avgHealth": avg_health,
				},
				"stream": {
					"configured": bool(self._redis_url),
					"streams": self._stream_names,
					"lastEventAt": self._last_event_at,
					"lastEventId": self._last_event_id,
					"lastStreamName": self._last_stream_name,
					"eventsSeenTotal": self._events_seen_total,
					"sseClients": len(self._subscribers),
					"lastDispatchAt": self._last_dispatch_at,
				},
			}

	async def subscribe(self) -> asyncio.Queue[str]:
		queue: asyncio.Queue[str] = asyncio.Queue()
		async with self._lock:
			self._subscribers.add(queue)
			self._record_dashboard_connection()
		return queue

	async def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
		async with self._lock:
			self._subscribers.discard(queue)
			self._record_dashboard_connection()

	async def _seed_from_recent_entries(self) -> None:
		if self._redis is None:
			return

		for stream_name in self._stream_names:
			try:
				entries = await self._redis.xrevrange(stream_name, count=100)
			except RedisError:
				LOGGER.exception("Failed to seed entries from stream %s", stream_name)
				continue

			if not entries:
				self._last_ids[stream_name] = "$"
				continue

			self._last_ids[stream_name] = entries[0][0]
			for entry_id, fields in reversed(entries):
				await self._apply_entry(stream_name, entry_id, parse_fields(fields), broadcast=False)

	async def _poll_streams(self) -> None:
		if self._redis is None:
			return

		while True:
			try:
				response = await self._redis.xread(self._last_ids, count=100, block=BLOCK_MS)
			except asyncio.CancelledError:
				raise
			except RedisError:
				LOGGER.exception("Redis stream poll failed")
				await asyncio.sleep(2)
				continue

			for stream_name, entries in response:
				for entry_id, fields in entries:
					self._last_ids[stream_name] = entry_id
					await self._apply_entry(stream_name, entry_id, parse_fields(fields), broadcast=True)

	async def _apply_entry(
		self,
		stream_name: str,
		entry_id: str,
		payload: dict[str, Any],
		*,
		broadcast: bool,
	) -> None:
		event_type = str(payload.get("event_type") or "stream_event")
		emitted_at = str(payload.get("emitted_at") or utc_now_iso())
		timestamp = parse_iso_timestamp(emitted_at) or utc_now()
		node_id, edge_id = classify_source(stream_name, event_type, payload)
		level = event_level(event_type, payload)

		async with self._lock:
			self._events_seen_total += 1
			self._last_event_id = entry_id
			self._last_event_at = emitted_at
			self._last_stream_name = stream_name
			self._push_stream_activity(timestamp, level)

			message = build_log_message(stream_name, event_type, payload)
			detail = build_event_detail(payload)
			self._record_storage_activity(stream_name, entry_id, event_type, emitted_at, timestamp, level, detail, payload)
			self._record_node_activity(node_id, stream_name, entry_id, event_type, emitted_at, timestamp, level, message, detail, payload)
			self._record_node_activity(
				"redis-stream",
				stream_name,
				entry_id,
				event_type,
				emitted_at,
				timestamp,
				level,
				f"{stream_name} entry received · {humanize_event_type(event_type)}",
				detail,
				payload,
			)
			self._record_node_activity(
				"observability-server",
				stream_name,
				entry_id,
				event_type,
				emitted_at,
				timestamp,
				level,
				f"Consumed {humanize_event_type(event_type)} from {stream_name}",
				detail,
				payload,
			)

			self._record_edge_activity(edge_id, emitted_at, timestamp, level)
			self._record_edge_activity("redis-to-observability-server", emitted_at, timestamp, level)

			if broadcast:
				self._record_edge_activity("observability-server-to-dashboard", utc_now_iso(), utc_now(), "info")
				self._sse_dispatch_count += 1
				self._last_dispatch_at = utc_now_iso()
				await self._broadcast(
					{
						"type": "dashboard-update",
						"stream": stream_name,
						"entryId": entry_id,
						"eventType": event_type,
						"nodeId": node_id,
						"emittedAt": emitted_at,
					}
				)

	def _push_stream_activity(self, timestamp: datetime, level: str) -> None:
		now_ts = timestamp.timestamp()
		self._stream_activity.append(now_ts)
		trim_window(self._stream_activity, now_ts, WINDOW_SECONDS)
		trim_window(self._stream_errors, now_ts, ERROR_WINDOW_SECONDS)
		if level == "error":
			self._stream_errors.append(now_ts)

	def _record_node_activity(
		self,
		node_id: str,
		stream_name: str,
		entry_id: str,
		event_type: str,
		emitted_at: str,
		timestamp: datetime,
		level: str,
		message: str,
		detail: str | None,
		payload: dict[str, Any],
	) -> None:
		state = self._nodes[node_id]
		now_ts = timestamp.timestamp()
		state.last_seen_at = emitted_at
		state.last_event_type = event_type
		state.last_payload = payload
		state.activity.append(now_ts)
		trim_window(state.activity, now_ts, WINDOW_SECONDS)
		trim_window(state.warnings, now_ts, ERROR_WINDOW_SECONDS)
		trim_window(state.errors, now_ts, ERROR_WINDOW_SECONDS)
		if level == "warning":
			state.warnings.append(now_ts)
		if level == "error":
			state.errors.append(now_ts)
		state.logs.appendleft(
			{
				"id": dedupe_event_id(stream_name, entry_id),
				"timestamp": to_time_label(emitted_at),
				"level": level,
				"message": message,
			}
		)
		state.events.appendleft(
			{
				"id": dedupe_event_id(stream_name, entry_id),
				"timestamp": to_time_label(emitted_at),
				"label": humanize_event_type(event_type).title(),
				"detail": detail,
			}
		)

	def _record_storage_activity(
		self,
		stream_name: str,
		entry_id: str,
		event_type: str,
		emitted_at: str,
		timestamp: datetime,
		level: str,
		detail: str | None,
		payload: dict[str, Any],
	) -> None:
		stage = str(payload.get("stage") or "").strip().lower()
		if stream_name == "webscraper:events" and stage == "write":
			self._record_node_activity(
				"scraped-data-table",
				stream_name,
				entry_id,
				event_type,
				emitted_at,
				timestamp,
				level,
				f"Postgres write acknowledged from WebScraper · {humanize_event_type(event_type)}",
				detail,
				payload,
			)
			self._record_edge_activity("scraper-to-scraped-db", emitted_at, timestamp, level)

		if stream_name == "jobdataserver:events":
			self._record_node_activity(
				"scraped-data-table",
				stream_name,
				entry_id,
				event_type,
				emitted_at,
				timestamp,
				level,
				f"Postgres CRUD acknowledged from JobDataServer · {humanize_event_type(event_type)}",
				detail,
				payload,
			)
			self._record_edge_activity("data-server-to-scraped-db", emitted_at, timestamp, level)

	def _record_edge_activity(self, edge_id: str, emitted_at: str, timestamp: datetime, level: str) -> None:
		state = self._edges[edge_id]
		now_ts = timestamp.timestamp()
		state.last_seen_at = emitted_at
		state.activity.append(now_ts)
		trim_window(state.activity, now_ts, WINDOW_SECONDS)
		if level == "error":
			state.status = "error"
		elif level == "warning" and state.status != "error":
			state.status = "warning"
		else:
			state.status = "healthy"

	def _record_dashboard_connection(self) -> None:
		now_iso = utc_now_iso()
		state = self._nodes["observability-dashboard"]
		state.last_seen_at = now_iso
		state.last_event_type = "dashboard_connected" if self._subscribers else "dashboard_idle"
		state.last_payload = {"clients": len(self._subscribers)}
		self._edges["observability-server-to-dashboard"].last_seen_at = now_iso
		self._edges["observability-server-to-dashboard"].status = "healthy" if self._subscribers else "idle"

	def _build_node_snapshot(self, node_id: str, state: NodeRuntimeState) -> dict[str, Any]:
		status, health_score = self._derive_node_health(state)
		return {
			"id": node_id,
			"status": status,
			"healthScore": health_score,
			"lastSeenAt": to_time_label(state.last_seen_at),
			"metrics": self._build_node_metrics(node_id, state, status),
			"logs": list(state.logs),
			"events": list(state.events),
		}

	def _build_edge_snapshot(self, edge_id: str, state: EdgeRuntimeState) -> dict[str, Any]:
		throughput = f"{len(state.activity)} ev / 5m"
		status = state.status if state.last_seen_at else "idle"
		return {
			"id": edge_id,
			"status": status,
			"throughput": throughput,
			"lastEventAt": to_time_label(state.last_seen_at),
		}

	def _derive_node_health(self, state: NodeRuntimeState) -> tuple[str, int]:
		if state.last_seen_at is None:
			return "idle", 78

		now = utc_now()
		last_seen = parse_iso_timestamp(state.last_seen_at) or now
		age_seconds = max((now - last_seen).total_seconds(), 0)
		if state.errors:
			return "error", 42
		if state.warnings:
			return "warning", 74
		if age_seconds > ERROR_WINDOW_SECONDS:
			return "idle", 82
		return "healthy", 96

	def _build_node_metrics(self, node_id: str, state: NodeRuntimeState, status: str) -> list[dict[str, str]]:
		events_5m = len(state.activity)
		error_count = len(state.errors)
		warning_count = len(state.warnings)
		metrics = [
			{"label": "Events (5m)", "value": str(events_5m), "trend": trend_for_count(events_5m)},
			{"label": "Errors (15m)", "value": str(error_count), "trend": "up" if error_count else "flat"},
		]

		if node_id == "redis-stream":
			metrics = [
				{"label": "Events / min", "value": str(max(round(len(self._stream_activity) / 5), 0)), "trend": trend_for_count(len(self._stream_activity))},
				{"label": "Tracked streams", "value": str(len(self._stream_names)), "trend": "flat"},
				{"label": "Recent errors", "value": str(len(self._stream_errors)), "trend": "up" if self._stream_errors else "flat"},
			]
		elif node_id == "observability-server":
			metrics = [
				{"label": "SSE clients", "value": str(len(self._subscribers)), "trend": "flat"},
				{"label": "Dispatches", "value": str(self._sse_dispatch_count), "trend": trend_for_count(self._sse_dispatch_count)},
				{"label": "Last stream", "value": self._last_stream_name or "n/a", "trend": "flat"},
			]
		elif node_id == "observability-dashboard":
			metrics = [
				{"label": "SSE connected", "value": "Yes" if self._subscribers else "No", "trend": "flat"},
				{"label": "Active sessions", "value": str(len(self._subscribers)), "trend": "flat"},
				{"label": "Last dispatch", "value": to_time_label(self._last_dispatch_at), "trend": "flat"},
			]
		elif node_id == "scraped-data-table":
			metrics.append(
				{
					"label": "Last written", "value": str(state.last_payload.get("written_count") or state.last_payload.get("job_count") or "n/a"), "trend": "flat"
				}
			)
		else:
			metrics.append(
				{
					"label": "Warnings (15m)",
					"value": str(warning_count),
					"trend": "up" if warning_count and status != "error" else "flat",
				}
			)

		if state.last_event_type and node_id not in {"observability-server", "observability-dashboard", "redis-stream"}:
			metrics.append(
				{
					"label": "Last event",
					"value": humanize_event_type(state.last_event_type)[:24],
					"trend": "flat",
				}
			)
		return metrics

	def _build_system_health(self, node_snapshots: list[dict[str, Any]]) -> tuple[str, int]:
		statuses = [node["status"] for node in node_snapshots]
		if "error" in statuses:
			status = "error"
		elif "warning" in statuses:
			status = "warning"
		else:
			status = "healthy"
		avg_health = round(sum(node["healthScore"] for node in node_snapshots) / len(node_snapshots))
		return status, avg_health

	async def _broadcast(self, payload: dict[str, Any]) -> None:
		message = format_sse(payload, event="dashboard-update")
		stale_queues: list[asyncio.Queue[str]] = []
		for subscriber in self._subscribers:
			try:
				subscriber.put_nowait(message)
			except asyncio.QueueFull:
				stale_queues.append(subscriber)
		for subscriber in stale_queues:
			self._subscribers.discard(subscriber)


def trim_window(values: deque[float], now_ts: float, window_seconds: int) -> None:
	while values and now_ts - values[0] > window_seconds:
		values.popleft()


def classify_source(stream_name: str, event_type: str, payload: dict[str, Any]) -> tuple[str, str]:
	if stream_name == "jobdataserver:events":
		return "data-server-backend", "data-server-to-redis"
	return "scrape-yc-script", "scraper-to-redis"


def format_sse(payload: dict[str, Any], *, event: str) -> str:
	return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


def load_stream_names() -> list[str]:
	raw_value = os.getenv("OBSERVABILITY_REDIS_STREAMS", "")
	streams = [value.strip() for value in raw_value.split(",") if value.strip()]
	return streams or list(DEFAULT_STREAMS)


@asynccontextmanager
async def lifespan(app: FastAPI):
	state = ObservabilityState(os.getenv("REDIS_URL"), load_stream_names())
	app.state.observability_state = state
	await state.start()
	try:
		yield
	finally:
		await state.stop()


app = FastAPI(
	title="Observability Metrics Server",
	description="Consumes Redis Stream events and exposes live dashboard metrics.",
	version="0.1.0",
	lifespan=lifespan,
)

allowed_origins = [value.strip() for value in os.getenv("OBSERVABILITY_ALLOWED_ORIGINS", "*").split(",") if value.strip()]
app.add_middleware(
	CORSMiddleware,
	allow_origins=allowed_origins or ["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


def get_state(request: Request) -> ObservabilityState:
	return request.app.state.observability_state


@app.get("/")
async def root() -> dict[str, Any]:
	return {
		"service": "observability-metrics-server",
		"status": "ok",
		"streams": load_stream_names(),
	}


@app.get("/health")
async def health(request: Request) -> dict[str, Any]:
	state = get_state(request)
	snapshot = await state.snapshot()
	return {
		"status": "ok",
		"redisConfigured": snapshot["stream"]["configured"],
		"streamStatus": snapshot["system"]["status"],
		"streams": snapshot["stream"]["streams"],
	}


@app.get("/api/dashboard")
async def dashboard_snapshot(request: Request) -> dict[str, Any]:
	return await get_state(request).snapshot()


@app.get("/api/events/stream")
async def dashboard_events(request: Request) -> StreamingResponse:
	state = get_state(request)
	queue = await state.subscribe()

	async def event_generator():
		try:
			yield format_sse({"type": "connected", "connectedAt": utc_now_iso()}, event="ready")
			while True:
				if await request.is_disconnected():
					break
				try:
					message = await asyncio.wait_for(queue.get(), timeout=15)
				except TimeoutError:
					yield ": keep-alive\n\n"
					continue
				yield message
		finally:
			await state.unsubscribe(queue)

	return StreamingResponse(event_generator(), media_type="text/event-stream")
