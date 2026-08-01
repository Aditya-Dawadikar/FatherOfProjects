from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from integrations.mlflow import register_prompt_variants
from integrations.streaming import RedisStreamPublisher
from utils.agent_logger import configure_logging, get_agent_logger
from utils.env_utils import ENV_FILE
from utils.mlflow_utils import get_tracking_uri

from .agent_worker import run_agent_worker
from .eval_runs import router as eval_runs_router


load_dotenv(ENV_FILE)
configure_logging()
LOGGER = get_agent_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
	publisher = RedisStreamPublisher.from_env()
	tracking_uri = get_tracking_uri()
	LOGGER.info("MLflow startup target uri=%s", tracking_uri)

	try:
		register_prompt_variants()
	except Exception:
		# Eval tooling (evals/run_offline_eval.py --prompt-version) degrades gracefully if a
		# variant is missing from the registry -- it's not worth failing the whole deploy (and
		# taking down live matching with it) over the MLflow server being briefly unreachable.
		LOGGER.exception("Failed to register prompt variants; continuing startup")

	# The agent (boot catch-up cycle, then the Redis stream consumer loop forever) is a
	# synchronous, blocking piece of code -- it predates this API and nothing about it needed to
	# change to live inside a server process. Running it on its own daemon thread instead of
	# porting it to asyncio means the HTTP server is available immediately rather than blocked
	# behind the boot cycle, and lets the agent keep working exactly as it did as a standalone
	# process.
	worker_thread = threading.Thread(
		target=run_agent_worker,
		args=(publisher,),
		daemon=True,
		name="agent-worker",
	)
	worker_thread.start()
	LOGGER.info("Agent worker thread started")

	yield

	LOGGER.info("Server shutting down (agent worker thread is a daemon; it exits with the process)")


def create_app() -> FastAPI:
	app = FastAPI(
		title="JobManagerAgent",
		description=(
			"The live matching agent runs on a background thread and isn't controlled through "
			"this API. **/evals** triggers the offline eval harness -- use the 'Try it out' "
			"button below; the default example scores 1 case from the tiny example dataset "
			"(cheap/fast). Omitting `limit` on a real request scores the full golden dataset: "
			"real, billed Gemini calls, 10+ minutes."
		),
		lifespan=lifespan,
	)
	app.add_middleware(
		CORSMiddleware,
		allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
		allow_credentials=True,
		allow_methods=["*"],
		allow_headers=["*"],
	)
	app.include_router(eval_runs_router)

	@app.get("/health")
	def health() -> dict[str, str]:
		return {"status": "ok"}

	return app
