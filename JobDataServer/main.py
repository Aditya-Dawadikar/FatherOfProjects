from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import func


ENV_FILE = Path(__file__).with_name(".env")
load_dotenv(ENV_FILE)

SERVICE_ROOT = Path(__file__).resolve().parent
if str(SERVICE_ROOT) not in sys.path:
	sys.path.insert(0, str(SERVICE_ROOT))

from shared.job_data import (  # noqa: E402
	Base,
	JOB_FIELD_NAMES,
	JobListing,
	apply_job_delta,
	create_db_engine,
	load_database_url,
	normalize_job_payload,
)
from shared.job_match_data import JobMatch  # noqa: E402
from stream_events import RedisStreamPublisher, publish_server_event


LOGGER = logging.getLogger(__name__)

# Score bands the /matches/funnel endpoint and the dashboard's alluvial chart agree on --
# match_score >= GOOD is "good", [MODERATE, GOOD) is "moderate", below MODERATE is "bad". Kept
# here as the single source of truth instead of letting the frontend duplicate these cutoffs
# across several /matches/count calls with different min_score/max_score combinations.
_GOOD_MATCH_MIN_SCORE = 70
_MODERATE_MATCH_MIN_SCORE = 40

# JobManagerAgent's crawl_job tool (tools/agent_tools.py) records a 404'd posting as a job_matches
# row (match_score=0, is_match=False) tagged with this reasoning prefix instead of leaving it
# unevaluated -- it's an agent/crawl failure, not a genuine low-scoring match, so /matches/funnel
# breaks it out of the "bad" bucket instead of conflating "scored poorly" with "couldn't even be
# evaluated". Every other failure mode (rate limits, timeouts, unparseable LLM responses) is NOT
# persisted anywhere -- the agent just skips the job for retry next cycle -- so only this one is
# distinguishable from "not yet processed" today.
_NOT_FOUND_REASON_PREFIX = "not_found_404"


app = FastAPI(
	title="Job Data Server",
	description="CRUD API for the WebScraper job_listings table, plus read-only query APIs over "
	"job_matches (JobManagerAgent's LLM scoring output).",
	version="0.1.0",
)

app.add_middleware(
	CORSMiddleware,
	allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


def get_resolved_table_name() -> str:
	return os.getenv("JOB_TABLE_NAME", JobListing.__tablename__).strip() or JobListing.__tablename__


def get_resolved_match_table_name() -> str:
	return os.getenv("JOB_MATCH_TABLE_NAME", JobMatch.__tablename__).strip() or JobMatch.__tablename__


class JobBase(BaseModel):
	company_name: str
	company_batch: str | None = None
	company_url: str | None = None
	company_one_liner: str | None = None
	company_logo_url: str | None = None
	company_last_active_at: str | None = None
	job_role: str
	job_url: str | None = None
	application_link: str | None = None
	location: str | None = None
	job_type: str | None = None
	role_type: str | None = None
	salary_range: str | None = None


class JobCreate(JobBase):
	job_id: int


class JobPatch(BaseModel):
	company_name: str | None = None
	company_batch: str | None = None
	company_url: str | None = None
	company_one_liner: str | None = None
	company_logo_url: str | None = None
	company_last_active_at: str | None = None
	job_role: str | None = None
	job_url: str | None = None
	application_link: str | None = None
	location: str | None = None
	job_type: str | None = None
	role_type: str | None = None
	salary_range: str | None = None

	model_config = ConfigDict(extra="forbid")


class JobRead(JobBase):
	job_id: int
	updated_at: datetime

	model_config = ConfigDict(from_attributes=True)


class JobMatchRead(BaseModel):
	job_id: int
	match_score: int
	is_match: bool
	reasoning: str | None = None
	prompt_name: str
	prompt_version: str
	model_name: str
	evaluated_at: datetime

	model_config = ConfigDict(from_attributes=True)


class JobWithMatchRead(JobRead):
	match_score: int
	is_match: bool
	reasoning: str | None = None
	prompt_name: str
	prompt_version: str
	model_name: str
	evaluated_at: datetime


class PipelineFunnelResponse(BaseModel):
	total_scraped: int
	total_processed: int
	good_matches: int
	moderate_matches: int
	bad_matches: int
	failed_matches: int


def serialize_job_listing(listing: JobListing) -> dict[str, object]:
	payload: dict[str, object] = {
		"job_id": listing.job_id,
		"updated_at": listing.updated_at.isoformat() if listing.updated_at else None,
	}
	for field_name in JOB_FIELD_NAMES:
		payload[field_name] = getattr(listing, field_name)
	return payload


def serialize_job_with_match(listing: JobListing, match: JobMatch) -> dict[str, object]:
	payload = serialize_job_listing(listing)
	payload.update(
		match_score=match.match_score,
		is_match=match.is_match,
		reasoning=match.reasoning,
		prompt_name=match.prompt_name,
		prompt_version=match.prompt_version,
		model_name=match.model_name,
		evaluated_at=match.evaluated_at.isoformat() if match.evaluated_at else None,
	)
	return payload


@lru_cache
def get_engine():
	engine = create_db_engine(load_database_url())
	Base.metadata.create_all(engine)
	return engine


@lru_cache
def get_event_publisher() -> RedisStreamPublisher | None:
	return RedisStreamPublisher.from_env()


def get_session():
	with Session(get_engine()) as session:
		yield session


SessionDependency = Annotated[Session, Depends(get_session)]


def with_company_filter(statement: Select, company_name: str | None):
	if company_name is None:
		return statement

	return statement.where(func.lower(JobListing.company_name) == company_name.strip().lower())


def with_search_filters(
	statement: Select,
	*,
	job_role: str | None = None,
	location: str | None = None,
	query: str | None = None,
):
	if job_role:
		statement = statement.where(JobListing.job_role.ilike(f"%{job_role.strip()}%"))
	if location:
		statement = statement.where(JobListing.location.ilike(f"%{location.strip()}%"))
	if query:
		search_term = f"%{query.strip()}%"
		statement = statement.where(
			or_(
				JobListing.company_name.ilike(search_term),
				JobListing.job_role.ilike(search_term),
				JobListing.location.ilike(search_term),
			)
		)

	return statement


def with_match_filters(
	statement: Select,
	*,
	is_match: bool | None = None,
	min_score: int | None = None,
	max_score: int | None = None,
	prompt_version: str | None = None,
):
	if is_match is not None:
		statement = statement.where(JobMatch.is_match == is_match)
	if min_score is not None:
		statement = statement.where(JobMatch.match_score >= min_score)
	if max_score is not None:
		statement = statement.where(JobMatch.match_score <= max_score)
	if prompt_version:
		statement = statement.where(JobMatch.prompt_version == prompt_version)

	return statement


def get_job_or_404(session: Session, job_id: int, company_name: str | None) -> JobListing:
	statement = select(JobListing).where(JobListing.job_id == job_id)
	listing = session.scalar(with_company_filter(statement, company_name))
	if listing is None:
		detail = f"Job {job_id} was not found"
		if company_name:
			detail = f"Job {job_id} for company '{company_name}' was not found"
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

	return listing


def merge_patch_payload(listing: JobListing, patch: JobPatch) -> dict[str, str | None]:
	merged_payload = {field_name: getattr(listing, field_name) for field_name in JOB_FIELD_NAMES}
	merged_payload.update(patch.model_dump(exclude_unset=True))
	return normalize_job_payload(merged_payload)


@app.get("/health")
def healthcheck() -> dict[str, str]:
	return {"status": "ok", "table": get_resolved_table_name(), "match_table": get_resolved_match_table_name()}


@app.get("/jobs", response_model=list[JobRead])
def get_jobs(
	session: SessionDependency,
	company_name: str | None = Query(default=None),
	job_id: int | None = Query(default=None),
	limit: int = Query(default=100, ge=1, le=500),
	offset: int = Query(default=0, ge=0),
) -> list[JobListing]:
	statement = select(JobListing).order_by(JobListing.updated_at.desc(), JobListing.job_id.desc())
	if job_id is not None:
		statement = statement.where(JobListing.job_id == job_id)
	statement = with_company_filter(statement, company_name)
	statement = statement.offset(offset).limit(limit)
	return list(session.scalars(statement))


@app.get("/jobs/search", response_model=list[JobRead])
def search_jobs(
	session: SessionDependency,
	company_name: str | None = Query(default=None),
	job_id: int | None = Query(default=None),
	job_role: str | None = Query(default=None),
	location: str | None = Query(default=None),
	query: str | None = Query(default=None),
	limit: int = Query(default=100, ge=1, le=500),
	offset: int = Query(default=0, ge=0),
) -> list[JobListing]:
	if not any((company_name, job_id is not None, job_role, location, query)):
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Provide at least one search filter",
		)

	statement = select(JobListing).order_by(JobListing.updated_at.desc(), JobListing.job_id.desc())
	if job_id is not None:
		statement = statement.where(JobListing.job_id == job_id)
	statement = with_company_filter(statement, company_name)
	statement = with_search_filters(
		statement,
		job_role=job_role,
		location=location,
		query=query,
	)

	statement = statement.offset(offset).limit(limit)
	return list(session.scalars(statement))


@app.get("/jobs/count")
def count_jobs(
	session: SessionDependency,
	company_name: str | None = Query(default=None),
	job_id: int | None = Query(default=None),
	job_role: str | None = Query(default=None),
	location: str | None = Query(default=None),
	query: str | None = Query(default=None),
) -> dict[str, int]:
	statement = select(func.count()).select_from(JobListing)
	if job_id is not None:
		statement = statement.where(JobListing.job_id == job_id)
	statement = with_company_filter(statement, company_name)
	statement = with_search_filters(
		statement,
		job_role=job_role,
		location=location,
		query=query,
	)
	total = session.scalar(statement) or 0
	return {"total": int(total)}


@app.get("/jobs/matched", response_model=list[JobWithMatchRead])
def get_matched_jobs(
	session: SessionDependency,
	company_name: str | None = Query(default=None),
	job_id: int | None = Query(default=None),
	job_role: str | None = Query(default=None),
	location: str | None = Query(default=None),
	query: str | None = Query(default=None),
	is_match: bool | None = Query(default=None, description="Filter to jobs that cleared MATCH_THRESHOLD (true) or not (false)."),
	min_score: int | None = Query(default=None, ge=0, le=100),
	max_score: int | None = Query(default=None, ge=0, le=100),
	prompt_version: str | None = Query(default=None, description="Only jobs scored by this exact job_matches.prompt_version."),
	limit: int = Query(default=100, ge=1, le=500),
	offset: int = Query(default=0, ge=0),
) -> list[dict[str, object]]:
	"""job_listings inner-joined with job_matches -- every job JobManagerAgent has already
	scored, with the full listing plus its score/reasoning/prompt/model provenance in one row.
	Jobs not yet evaluated (no job_matches row) are excluded; that's the whole point of this
	endpoint over plain /jobs, which knows nothing about match state."""
	statement = (
		select(JobListing, JobMatch)
		.join(JobMatch, JobMatch.job_id == JobListing.job_id)
		.order_by(JobMatch.evaluated_at.desc(), JobListing.job_id.desc())
	)
	if job_id is not None:
		statement = statement.where(JobListing.job_id == job_id)
	statement = with_company_filter(statement, company_name)
	statement = with_search_filters(statement, job_role=job_role, location=location, query=query)
	statement = with_match_filters(
		statement, is_match=is_match, min_score=min_score, max_score=max_score, prompt_version=prompt_version
	)
	statement = statement.offset(offset).limit(limit)

	rows = session.execute(statement).all()
	return [serialize_job_with_match(listing, match) for listing, match in rows]


@app.get("/jobs/matched/count")
def count_matched_jobs(
	session: SessionDependency,
	company_name: str | None = Query(default=None),
	job_id: int | None = Query(default=None),
	job_role: str | None = Query(default=None),
	location: str | None = Query(default=None),
	query: str | None = Query(default=None),
	is_match: bool | None = Query(default=None),
	min_score: int | None = Query(default=None, ge=0, le=100),
	max_score: int | None = Query(default=None, ge=0, le=100),
	prompt_version: str | None = Query(default=None),
) -> dict[str, int]:
	"""Mirrors /jobs/matched's filters exactly (same join, same helpers) so a caller paginating
	that endpoint can compute total pages instead of guessing from a short page."""
	statement = select(func.count()).select_from(JobListing).join(JobMatch, JobMatch.job_id == JobListing.job_id)
	if job_id is not None:
		statement = statement.where(JobListing.job_id == job_id)
	statement = with_company_filter(statement, company_name)
	statement = with_search_filters(statement, job_role=job_role, location=location, query=query)
	statement = with_match_filters(
		statement, is_match=is_match, min_score=min_score, max_score=max_score, prompt_version=prompt_version
	)
	total = session.scalar(statement) or 0
	return {"total": int(total)}


@app.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: int, session: SessionDependency, company_name: str | None = Query(default=None)) -> JobListing:
	return get_job_or_404(session, job_id, company_name)


@app.post("/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, session: SessionDependency) -> JobListing:
	existing_listing = session.get(JobListing, payload.job_id)
	if existing_listing is not None:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail=f"Job {payload.job_id} already exists",
		)

	normalized_payload = normalize_job_payload(payload.model_dump())
	listing = JobListing(job_id=payload.job_id, **normalized_payload)
	session.add(listing)
	session.commit()
	session.refresh(listing)
	publish_server_event(
		get_event_publisher(),
		"job_created",
		job_id=listing.job_id,
		job=serialize_job_listing(listing),
	)
	return listing


@app.patch("/jobs/{job_id}", response_model=JobRead)
def patch_job(
	job_id: int,
	patch: JobPatch,
	session: SessionDependency,
	company_name: str | None = Query(default=None),
) -> JobListing:
	if not patch.model_fields_set:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Provide at least one field to update",
		)

	listing = get_job_or_404(session, job_id, company_name)
	merged_payload = merge_patch_payload(listing, patch)
	changed = apply_job_delta(listing, merged_payload)
	session.commit()
	session.refresh(listing)
	if changed:
		publish_server_event(
			get_event_publisher(),
			"job_updated",
			job_id=listing.job_id,
			job=serialize_job_listing(listing),
			updated_fields=sorted(patch.model_fields_set),
		)
	else:
		LOGGER.info("No changes detected for job_id=%s", listing.job_id)
	return listing


@app.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
	job_id: int,
	session: SessionDependency,
	company_name: str | None = Query(default=None),
) -> Response:
	listing = get_job_or_404(session, job_id, company_name)
	deleted_job = serialize_job_listing(listing)
	session.delete(listing)
	session.commit()
	publish_server_event(
		get_event_publisher(),
		"job_deleted",
		job_id=job_id,
		job=deleted_job,
	)
	return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- job_matches (read-only) -------------------------------------------------------------------
# JobManagerAgent is the sole writer of job_matches (see its tools/db_tools.py record_job_result,
# called once per job right after its ReAct agent scores it against the resume via
# evaluate_match/score_job). This service only reads that same table -- there is no POST/PATCH/
# DELETE here, match data is exposed for querying, not mutated from this side.


@app.get("/matches", response_model=list[JobMatchRead])
def get_matches(
	session: SessionDependency,
	job_id: int | None = Query(default=None),
	is_match: bool | None = Query(default=None, description="Filter to jobs that cleared MATCH_THRESHOLD (true) or not (false)."),
	min_score: int | None = Query(default=None, ge=0, le=100),
	max_score: int | None = Query(default=None, ge=0, le=100),
	prompt_version: str | None = Query(default=None, description="Only rows scored by this exact prompt_version."),
	limit: int = Query(default=100, ge=1, le=500),
	offset: int = Query(default=0, ge=0),
) -> list[JobMatch]:
	statement = select(JobMatch).order_by(JobMatch.evaluated_at.desc(), JobMatch.job_id.desc())
	if job_id is not None:
		statement = statement.where(JobMatch.job_id == job_id)
	statement = with_match_filters(
		statement, is_match=is_match, min_score=min_score, max_score=max_score, prompt_version=prompt_version
	)
	statement = statement.offset(offset).limit(limit)
	return list(session.scalars(statement))


@app.get("/matches/count")
def count_matches(
	session: SessionDependency,
	is_match: bool | None = Query(default=None),
	min_score: int | None = Query(default=None, ge=0, le=100),
	max_score: int | None = Query(default=None, ge=0, le=100),
	prompt_version: str | None = Query(default=None),
) -> dict[str, int]:
	statement = select(func.count()).select_from(JobMatch)
	statement = with_match_filters(
		statement, is_match=is_match, min_score=min_score, max_score=max_score, prompt_version=prompt_version
	)
	total = session.scalar(statement) or 0
	return {"total": int(total)}


@app.get("/matches/funnel", response_model=PipelineFunnelResponse)
def get_pipeline_funnel(session: SessionDependency) -> PipelineFunnelResponse:
	"""Counts for the scrape -> agent-processed -> good/moderate/bad/failed funnel the dashboard's
	alluvial chart renders. total_processed is every job_matches row regardless of score;
	total_scraped - total_processed is how many job_listings rows JobManagerAgent hasn't reached
	yet. good/moderate/bad/failed always sum to total_processed -- failed (404'd postings) is
	carved out of the score bands rather than counted as a genuine bad match."""
	not_found = JobMatch.reasoning.like(f"{_NOT_FOUND_REASON_PREFIX}%")

	total_scraped = session.scalar(select(func.count()).select_from(JobListing)) or 0
	total_processed = session.scalar(select(func.count()).select_from(JobMatch)) or 0
	failed_matches = session.scalar(select(func.count()).select_from(JobMatch).where(not_found)) or 0
	good_matches = (
		session.scalar(
			select(func.count())
			.select_from(JobMatch)
			.where(JobMatch.match_score >= _GOOD_MATCH_MIN_SCORE, ~not_found)
		)
		or 0
	)
	moderate_matches = (
		session.scalar(
			select(func.count())
			.select_from(JobMatch)
			.where(
				JobMatch.match_score >= _MODERATE_MATCH_MIN_SCORE,
				JobMatch.match_score < _GOOD_MATCH_MIN_SCORE,
				~not_found,
			)
		)
		or 0
	)
	bad_matches = (
		session.scalar(
			select(func.count())
			.select_from(JobMatch)
			.where(JobMatch.match_score < _MODERATE_MATCH_MIN_SCORE, ~not_found)
		)
		or 0
	)
	return PipelineFunnelResponse(
		total_scraped=int(total_scraped),
		total_processed=int(total_processed),
		good_matches=int(good_matches),
		moderate_matches=int(moderate_matches),
		bad_matches=int(bad_matches),
		failed_matches=int(failed_matches),
	)


@app.get("/matches/{job_id}", response_model=JobMatchRead)
def get_match(job_id: int, session: SessionDependency) -> JobMatch:
	match = session.get(JobMatch, job_id)
	if match is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No match recorded for job {job_id}")
	return match