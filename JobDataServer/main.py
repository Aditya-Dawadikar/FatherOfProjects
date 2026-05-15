from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
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
from stream_events import RedisStreamPublisher, publish_server_event


LOGGER = logging.getLogger(__name__)


app = FastAPI(
	title="Job Data Server",
	description="Simple CRUD API for the WebScraper job_listings table.",
	version="0.1.0",
)


def get_resolved_table_name() -> str:
	return os.getenv("JOB_TABLE_NAME", JobListing.__tablename__).strip() or JobListing.__tablename__


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


def serialize_job_listing(listing: JobListing) -> dict[str, object]:
	payload: dict[str, object] = {
		"job_id": listing.job_id,
		"updated_at": listing.updated_at.isoformat() if listing.updated_at else None,
	}
	for field_name in JOB_FIELD_NAMES:
		payload[field_name] = getattr(listing, field_name)
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


def with_company_filter(statement: Select[tuple[JobListing]], company_name: str | None):
	if company_name is None:
		return statement

	return statement.where(func.lower(JobListing.company_name) == company_name.strip().lower())


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
	return {"status": "ok", "table": get_resolved_table_name()}


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

	statement = statement.offset(offset).limit(limit)
	return list(session.scalars(statement))


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