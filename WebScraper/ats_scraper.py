from __future__ import annotations

import logging
import os
from html import unescape
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


def load_board_slugs(env_var: str, default: str) -> list[str]:
	raw = os.getenv(env_var, "").strip()
	if not raw and ENV_FILE.exists():
		load_dotenv(ENV_FILE)
		raw = os.getenv(env_var, "").strip()
	raw = raw or default
	return [slug.strip() for slug in raw.split(",") if slug.strip()]


def _get_json(url: str) -> Any:
	response = requests.get(url, headers=JSON_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
	response.raise_for_status()
	return response.json()


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

	jobs = data.get("jobs") or []
	normalized = []
	for job in jobs:
		job_id = job.get("id")
		if job_id is None:
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

	jobs = (data or {}).get("jobs") or []
	normalized = []
	for job in jobs:
		job_id = job.get("id")
		if job_id is None:
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

	normalized = []
	for job in jobs:
		job_id = job.get("id")
		if job_id is None:
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
	non-YC source -- scrapes every board slug configured for it (comma-separated env var, see
	_FETCHERS) and concatenates the results. Per-slug failures (dead board, network error) are
	logged and skipped rather than failing the whole source, same spirit as the reference
	aggregator's dead-slug handling.
	"""
	fetch_fn, env_var, default = _FETCHERS[source]
	slugs = load_board_slugs(env_var, default)
	jobs: list[dict[str, Any]] = []
	for slug in slugs:
		slug_jobs = fetch_fn(slug)
		LOGGER.info("%s: %s: %s jobs", source, slug, len(slug_jobs))
		jobs.extend(slug_jobs)

	return {"source": source, "boards": slugs, "job_count": len(jobs), "jobs": jobs}
