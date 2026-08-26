from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


DEFAULT_JOB_TABLE_NAME = "job_listings"

# job_listings.source value for every job scraped from Work at a Startup -- the only source that
# has ever existed. Mirrors JobManagerAgent/utils/config.py's DEFAULT_JOB_SOURCE (each service
# keeps its own copy of shared/job_data.py by convention, so this constant is duplicated too).
DEFAULT_JOB_SOURCE = "ycombinator"


def load_job_table_name() -> str:
	return os.getenv("JOB_TABLE_NAME", DEFAULT_JOB_TABLE_NAME).strip() or DEFAULT_JOB_TABLE_NAME


def load_database_url() -> str:
	for env_name in ("DATABASE_URL", "POSTGRES_URL"):
		value = os.getenv(env_name, "").strip()
		if value:
			return value

	raise KeyError("DATABASE_URL or POSTGRES_URL is not defined in the environment")


class Base(DeclarativeBase):
	pass


class JobListing(Base):
	__tablename__ = load_job_table_name()
	__table_args__ = (UniqueConstraint("source", "source_job_id", name="uq_job_listings_source_source_job_id"),)

	# Surrogate primary key -- see JobManagerAgent/scripts/migrations/0003_add_source_and_surrogate_key_to_job_listings.py
	# and 0005_drop_job_id_from_job_listings.py. Replaces the old job_id INTEGER PK: Ashby/Lever ids
	# are UUID strings and Greenhouse ids come from a separate id space than YC's, so no single
	# source's native id can safely be the global key once multiple sources exist. Server-generated
	# (Postgres IDENTITY) -- never set this from application code.
	id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
	# The source's native job id, as text (Ashby/Lever UUIDs, Greenhouse/YC numeric ids as strings).
	source_job_id: Mapped[str] = mapped_column(Text, nullable=False)
	# Which platform this job came from: "ycombinator", "ashby", "greenhouse", or "lever".
	source: Mapped[str] = mapped_column(Text, nullable=False)
	company_name: Mapped[str] = mapped_column(String(255), nullable=False)
	company_batch: Mapped[str | None] = mapped_column(String(50))
	company_url: Mapped[str | None] = mapped_column(Text)
	company_one_liner: Mapped[str | None] = mapped_column(Text)
	company_logo_url: Mapped[str | None] = mapped_column(Text)
	company_last_active_at: Mapped[str | None] = mapped_column(String(100))
	job_role: Mapped[str] = mapped_column(String(255), nullable=False)
	job_url: Mapped[str | None] = mapped_column(Text)
	application_link: Mapped[str | None] = mapped_column(Text)
	location: Mapped[str | None] = mapped_column(String(255))
	job_type: Mapped[str | None] = mapped_column(String(100))
	role_type: Mapped[str | None] = mapped_column(String(100))
	salary_range: Mapped[str | None] = mapped_column(String(100))
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=False),
		default=datetime.utcnow,
		onupdate=datetime.utcnow,
		nullable=False,
	)


JOB_FIELD_NAMES = (
	"company_name",
	"company_batch",
	"company_url",
	"company_one_liner",
	"company_logo_url",
	"company_last_active_at",
	"job_role",
	"job_url",
	"application_link",
	"location",
	"job_type",
	"role_type",
	"salary_range",
)


def normalize_database_url(database_url: str) -> str:
	if database_url.startswith("postgresql://"):
		return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
	if database_url.startswith("postgres://"):
		return database_url.replace("postgres://", "postgresql+psycopg://", 1)
	return database_url


def create_db_engine(database_url: str):
	return create_engine(normalize_database_url(database_url), future=True)


def normalize_job_payload(job: dict[str, object]) -> dict[str, str | None]:
	return {
		"company_name": str(job.get("company_name") or ""),
		"company_batch": job.get("company_batch") or None,
		"company_url": job.get("company_url") or None,
		"company_one_liner": job.get("company_one_liner") or None,
		"company_logo_url": job.get("company_logo_url") or None,
		"company_last_active_at": job.get("company_last_active_at") or None,
		"job_role": str(job.get("job_role") or ""),
		"job_url": job.get("job_url") or None,
		"application_link": job.get("application_link") or None,
		"location": job.get("location") or None,
		"job_type": job.get("job_type") or None,
		"role_type": job.get("role_type") or None,
		"salary_range": job.get("salary_range") or None,
	}


def apply_job_delta(listing: JobListing, payload: dict[str, str | None]) -> bool:
	changed = False
	for field_name in JOB_FIELD_NAMES:
		incoming_value = payload[field_name]
		if getattr(listing, field_name) != incoming_value:
			setattr(listing, field_name, incoming_value)
			changed = True

	return changed