from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any

import requests
from requests.exceptions import HTTPError, RequestException

from scraper import ENV_FILE
from dotenv import load_dotenv


LOGGER = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
REQUEST_TIMEOUT_SECONDS = 30
JSON_HEADERS = {"Accept": "application/json", "User-Agent": USER_AGENT}

# Default board slugs per source -- opt-in via env var, comma-separated, so nothing scrapes beyond
# YC until a slug is actually configured. These defaults are real, live company boards (confirmed
# reachable during development) so a first run works out of the box without any extra setup.
_DEFAULT_GREENHOUSE_SLUGS = "stripe"
_DEFAULT_ASHBY_SLUGS = "ramp"
_DEFAULT_LEVER_SLUGS = "palantir"

# Full company slug lists (thousands of entries each -- see reference aggregator this repo studied)
# live here as static JSON, one flat array of strings per source. Used whenever the matching env
# var override below is unset, so a full run without extra config scrapes every company in these
# files rather than just the one-company default above.
SLUGS_DIR = Path(__file__).with_name("slugs")
_SLUG_FILES = {
	"greenhouse": SLUGS_DIR / "greenhouse_companies.json",
	"ashby": SLUGS_DIR / "ashby_companies.json",
	"lever": SLUGS_DIR / "lever_companies.json",
}

# How many companies to fetch concurrently per source -- with thousands of slugs in the files
# above, doing this serially would take hours. Mirrors the reference aggregator's per-platform
# worker counts (it found Ashby's endpoint least tolerant of concurrency).
_MAX_WORKERS = {"greenhouse": 20, "ashby": 5, "lever": 20}

# Only jobs whose own posted/updated timestamp falls within this many hours of "now" are written --
# every source's own list endpoint returns its ENTIRE current catalog with no server-side date
# filter, and scraping thousands of companies' full catalogs into job_listings would hand
# JobManagerAgent a backlog of tens of thousands of jobs to run real LLM calls against. This is the
# actual cost control: filtering client-side after fetch, not fetching less.
RECENCY_WINDOW_HOURS = int(os.getenv("SCRAPE_RECENCY_HOURS", "6"))

# job_listings rows from these three sources older than this are deleted by
# dataWriter.purge_stale_jobs (see job_runner.py) -- the other half of the same cost control: a
# job outside the recency window above will never be written again (its own timestamp only moves
# forward, and future scrapes filter it out the same way), so keeping it around forever serves no
# purpose except growing JobManagerAgent's eventual backlog. YC is deliberately excluded -- its
# scrape has always been small (one filtered search page), never the source of this problem.
RETENTION_MAX_AGE_DAYS = int(os.getenv("SCRAPE_RETENTION_DAYS", "7"))
RETENTION_SOURCES = ("ashby", "greenhouse", "lever")


def load_board_slugs(source: str, env_var: str, default: str) -> list[str]:
	"""Explicit env var wins (comma-separated, for pointing at a handful of companies while
	testing) over the source's full slugs/*.json file, which wins over the single-company
	`default` fallback used only if neither is present."""
	raw = os.getenv(env_var, "").strip()
	if not raw and ENV_FILE.exists():
		load_dotenv(ENV_FILE)
		raw = os.getenv(env_var, "").strip()
	if raw:
		return [slug.strip() for slug in raw.split(",") if slug.strip()]

	slug_file = _SLUG_FILES.get(source)
	if slug_file is not None and slug_file.exists():
		try:
			slugs = json.loads(slug_file.read_text(encoding="utf-8"))
		except (OSError, ValueError) as error:
			LOGGER.warning("Could not read %s: %s; falling back to default slug", slug_file, error)
		else:
			cleaned = [str(slug).strip() for slug in slugs if str(slug).strip()]
			if cleaned:
				return cleaned

	return [slug.strip() for slug in default.split(",") if slug.strip()]


def _get_json(url: str) -> Any:
	response = requests.get(url, headers=JSON_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
	response.raise_for_status()
	return response.json()


def _recency_cutoff() -> datetime:
	return datetime.now(timezone.utc) - timedelta(hours=RECENCY_WINDOW_HOURS)


def _parse_iso(value: str | None) -> datetime | None:
	if not value:
		return None
	try:
		parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
	except ValueError:
		return None
	return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_epoch_millis(value: object) -> datetime | None:
	if not isinstance(value, (int, float)):
		return None
	return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


# --- Greenhouse -----------------------------------------------------------------------------
# Job Board API, documented and public: https://developers.greenhouse.io/job-board.html. Confirmed
# live against boards-api.greenhouse.io/v1/boards/stripe/jobs during development -- the list
# endpoint already carries company_name/title/location/absolute_url/id/updated_at, so no per-job
# call is needed at scrape time. job_url is deliberately set to the per-job *detail* endpoint
# (`.../jobs/{id}?content=true`) rather than the human-facing absolute_url -- JobManagerAgent's
# crawler (services/crawler.py:fetch_job_detail_greenhouse) fetches that JSON endpoint directly to
# get the full posting description at match time; absolute_url is kept in application_link for
# humans to actually open the posting.


def fetch_greenhouse_jobs(slug: str) -> list[dict[str, Any]]:
	url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
	try:
		data = _get_json(url)
	except HTTPError as error:
		LOGGER.warning("Greenhouse %s: HTTP error %s", slug, error)
		return []
	except RequestException as error:
		LOGGER.warning("Greenhouse %s: request failed: %s", slug, error)
		return []

	cutoff = _recency_cutoff()
	jobs = data.get("jobs") or []
	normalized = []
	for job in jobs:
		job_id = job.get("id")
		if job_id is None:
			continue
		updated_at = _parse_iso(job.get("updated_at"))
		if updated_at is None or updated_at < cutoff:
			continue
		normalized.append(
			{
				"source": "greenhouse",
				"source_job_id": str(job_id),
				"company_name": job.get("company_name") or slug.title(),
				"company_batch": None,
				"company_url": None,
				"company_one_liner": None,
				"company_logo_url": None,
				"company_last_active_at": None,
				"job_role": job.get("title", ""),
				"job_url": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}?content=true",
				"application_link": job.get("absolute_url"),
				"location": (job.get("location") or {}).get("name"),
				"job_type": None,
				"role_type": None,
				"salary_range": None,
			}
		)
	return normalized


# --- Ashby ------------------------------------------------------------------------------------
# Public Job Board API, documented: https://developers.ashbyhq.com/reference/jobboardposting.
# Confirmed live against api.ashbyhq.com/posting-api/job-board/ramp during development -- unlike
# Greenhouse, the list response already includes full descriptionHtml per job, so job_url is set
# to this same list endpoint (there is no separate per-job detail endpoint); JobManagerAgent's
# crawler re-fetches it and filters by source_job_id (services/crawler.py:fetch_job_detail_ashby).


def fetch_ashby_jobs(slug: str) -> list[dict[str, Any]]:
	url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
	try:
		data = _get_json(url)
	except HTTPError as error:
		LOGGER.warning("Ashby %s: HTTP error %s", slug, error)
		return []
	except RequestException as error:
		LOGGER.warning("Ashby %s: request failed: %s", slug, error)
		return []

	cutoff = _recency_cutoff()
	jobs = (data or {}).get("jobs") or []
	normalized = []
	for job in jobs:
		job_id = job.get("id")
		if job_id is None:
			continue
		published_at = _parse_iso(job.get("publishedAt"))
		if published_at is None or published_at < cutoff:
			continue
		normalized.append(
			{
				"source": "ashby",
				"source_job_id": str(job_id),
				"company_name": slug.replace("-", " ").title(),
				"company_batch": None,
				"company_url": f"https://jobs.ashbyhq.com/{slug}",
				"company_one_liner": None,
				"company_logo_url": None,
				"company_last_active_at": None,
				"job_role": unescape((job.get("title") or "").strip()),
				"job_url": url,
				"application_link": job.get("jobUrl") or job.get("applyUrl"),
				"location": job.get("location"),
				"job_type": job.get("employmentType"),
				"role_type": job.get("department"),
				"salary_range": None,
			}
		)
	return normalized


# --- Lever ------------------------------------------------------------------------------------
# Public postings API, documented: https://github.com/lever/postings-api. Confirmed live against
# api.lever.co/v0/postings/palantir during development -- like Ashby, the list response already
# includes full descriptionPlain/lists content per posting, so job_url is set to this same list
# endpoint; JobManagerAgent's crawler re-fetches it and filters by source_job_id
# (services/crawler.py:fetch_job_detail_lever).


def fetch_lever_jobs(slug: str) -> list[dict[str, Any]]:
	url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
	try:
		jobs = _get_json(url)
	except HTTPError as error:
		LOGGER.warning("Lever %s: HTTP error %s", slug, error)
		return []
	except RequestException as error:
		LOGGER.warning("Lever %s: request failed: %s", slug, error)
		return []

	if not isinstance(jobs, list):
		LOGGER.warning("Lever %s: unexpected payload (not a list); dead/unknown slug?", slug)
		return []

	cutoff = _recency_cutoff()
	normalized = []
	for job in jobs:
		job_id = job.get("id")
		if job_id is None:
			continue
		created_at = _parse_epoch_millis(job.get("createdAt"))
		if created_at is None or created_at < cutoff:
			continue
		categories = job.get("categories") or {}
		normalized.append(
			{
				"source": "lever",
				"source_job_id": str(job_id),
				"company_name": slug.replace("-", " ").title(),
				"company_batch": None,
				"company_url": f"https://jobs.lever.co/{slug}",
				"company_one_liner": None,
				"company_logo_url": None,
				"company_last_active_at": None,
				"job_role": job.get("text", ""),
				"job_url": url,
				"application_link": job.get("applyUrl") or job.get("hostedUrl"),
				"location": categories.get("location"),
				"job_type": categories.get("commitment"),
				"role_type": categories.get("team"),
				"salary_range": None,
			}
		)
	return normalized


_FETCHERS = {
	"greenhouse": (fetch_greenhouse_jobs, "GREENHOUSE_BOARD_SLUGS", _DEFAULT_GREENHOUSE_SLUGS),
	"ashby": (fetch_ashby_jobs, "ASHBY_BOARD_SLUGS", _DEFAULT_ASHBY_SLUGS),
	"lever": (fetch_lever_jobs, "LEVER_BOARD_SLUGS", _DEFAULT_LEVER_SLUGS),
}


def run_scrape_stage_for_source(source: str) -> dict[str, Any]:
	"""Mirrors scraper.py's run_scrape_stage shape ({"jobs": [...], "job_count": n, ...}) for one
	non-YC source -- scrapes every board slug configured for it (env var override, else
	slugs/*.json, else a single-company default -- see load_board_slugs) concurrently, keeping
	only postings from within the last RECENCY_WINDOW_HOURS. Per-slug failures (dead board,
	network error) are logged and skipped rather than failing the whole source, same spirit as the
	reference aggregator's dead-slug handling.
	"""
	fetch_fn, env_var, default = _FETCHERS[source]
	slugs = load_board_slugs(source, env_var, default)
	max_workers = _MAX_WORKERS.get(source, 10)
	jobs: list[dict[str, Any]] = []

	with ThreadPoolExecutor(max_workers=max_workers) as executor:
		futures = {executor.submit(fetch_fn, slug): slug for slug in slugs}
		for i, future in enumerate(as_completed(futures), 1):
			slug = futures[future]
			try:
				slug_jobs = future.result()
			except Exception:
				LOGGER.exception("%s: %s: fetch raised unexpectedly", source, slug)
				continue
			if slug_jobs:
				jobs.extend(slug_jobs)
			if i % 200 == 0 or i == len(slugs):
				LOGGER.info("%s: checked %s/%s boards, %s recent jobs so far", source, i, len(slugs), len(jobs))

	return {"source": source, "boards": slugs, "job_count": len(jobs), "jobs": jobs}
