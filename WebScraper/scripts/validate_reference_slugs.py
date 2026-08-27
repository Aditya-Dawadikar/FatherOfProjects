"""Reusable curation tool: checks every slug in slugs/reference_slugs/*_companies.json against its
real ATS API and writes only the ones that still resolve (HTTP 200) to
slugs/reference_slugs/validated/*_companies.json, in the same array-of-strings shape as the input
-- so a validated file can be copied straight over an active slugs/*_companies.json once reviewed.

This is deliberately separate from ats_scraper.py's own fetchers: those fetch full job content
(Ashby's ?includeCompensation=true, Greenhouse's ?content=true detail calls) because they're
building real job_listings rows; this only needs to know whether the board exists at all, so it
hits the lightest version of each endpoint.

Usage (from WebScraper/):
    python -m scripts.validate_reference_slugs
    python -m scripts.validate_reference_slugs --source lever   # just one source
    python -m scripts.validate_reference_slugs --workers-ashby 5 --timeout 20
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import requests


REFERENCE_DIR = Path(__file__).resolve().parent.parent / "slugs" / "reference_slugs"
VALIDATED_DIR = REFERENCE_DIR / "validated"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
HEADERS = {"Accept": "application/json", "User-Agent": USER_AGENT}

# Lightest possible existence check per platform -- no job content, just "does this board exist".
SOURCE_URL_BUILDERS: dict[str, Callable[[str], str]] = {
	"greenhouse": lambda slug: f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
	"ashby": lambda slug: f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
	"lever": lambda slug: f"https://api.lever.co/v0/postings/{slug}?mode=json",
}

# Confirmed live against a known-dead slug for all three platforms: a nonexistent company returns
# a clean HTTP 404 on every one of them (not a 200-with-error-body), so status code alone is a
# reliable classifier -- no need to inspect response shape.
DEFAULT_WORKERS = {"greenhouse": 30, "ashby": 10, "lever": 30}


def check_slug(slug: str, build_url: Callable[[str], str], *, timeout: int, max_retries: int) -> tuple[str, str]:
	"""Returns (classification, detail). classification is one of valid/invalid/error.

	error is deliberately its own bucket, distinct from invalid -- a timeout or persistent 5xx/429
	doesn't mean the slug is dead, just that this run couldn't confirm either way. Only `invalid`
	(a real 404) should ever be treated as safe to drop from a slug list.
	"""
	url = build_url(slug)
	last_error = ""
	for attempt in range(max_retries + 1):
		try:
			response = requests.get(url, headers=HEADERS, timeout=timeout)
		except requests.RequestException as error:
			last_error = str(error)
			time.sleep(1.0 + attempt)
			continue

		if response.status_code == 200:
			return "valid", "200"
		if response.status_code == 404:
			return "invalid", "404"
		if response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
			time.sleep(2.0 * (attempt + 1))
			continue
		return "error", f"status={response.status_code}"

	return "error", f"request_exception: {last_error}"


def validate_source(source: str, *, workers: int, timeout: int, max_retries: int) -> dict[str, object]:
	input_file = REFERENCE_DIR / f"{source}_companies.json"
	if not input_file.exists():
		raise FileNotFoundError(f"{input_file} not found")

	slugs = json.loads(input_file.read_text(encoding="utf-8"))
	build_url = SOURCE_URL_BUILDERS[source]
	results: dict[str, list[str]] = {"valid": [], "invalid": [], "error": []}

	print(f"[{source}] checking {len(slugs)} slugs with {workers} workers...", flush=True)
	start = time.time()
	with ThreadPoolExecutor(max_workers=workers) as executor:
		futures = {executor.submit(check_slug, slug, build_url, timeout=timeout, max_retries=max_retries): slug for slug in slugs}
		for i, future in enumerate(as_completed(futures), 1):
			slug = futures[future]
			try:
				classification, _detail = future.result()
			except Exception as error:  # pragma: no cover -- defensive
				classification = "error"
				print(f"[{source}] {slug}: unexpected error: {error}", flush=True)
			results[classification].append(slug)
			if i % 250 == 0 or i == len(slugs):
				elapsed = time.time() - start
				print(
					f"[{source}] {i}/{len(slugs)} checked ({elapsed:.0f}s) -- "
					f"valid={len(results['valid'])} invalid={len(results['invalid'])} error={len(results['error'])}",
					flush=True,
				)

	elapsed = time.time() - start
	counts = {k: len(v) for k, v in results.items()}
	print(f"[{source}] DONE in {elapsed:.0f}s -- {counts}", flush=True)

	VALIDATED_DIR.mkdir(parents=True, exist_ok=True)
	valid_sorted = sorted(results["valid"])
	(VALIDATED_DIR / f"{source}_companies.json").write_text(
		json.dumps(valid_sorted, indent=2) + "\n", encoding="utf-8"
	)
	(VALIDATED_DIR / f"{source}_summary.json").write_text(
		json.dumps(
			{
				"source": source,
				"input_count": len(slugs),
				"counts": counts,
				"invalid": sorted(results["invalid"]),
				"error": sorted(results["error"]),
			},
			indent=2,
		)
		+ "\n",
		encoding="utf-8",
	)
	print(f"[{source}] wrote {VALIDATED_DIR / f'{source}_companies.json'} ({len(valid_sorted)} slugs)", flush=True)
	return {"source": source, "input_count": len(slugs), **counts}


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--source", choices=sorted(SOURCE_URL_BUILDERS), help="Only validate this one source")
	parser.add_argument("--timeout", type=int, default=15, help="Per-request timeout in seconds (default 15)")
	parser.add_argument("--max-retries", type=int, default=2, help="Retries for timeouts/429/5xx before giving up (default 2)")
	for source, default_workers in DEFAULT_WORKERS.items():
		parser.add_argument(f"--workers-{source}", type=int, default=default_workers, help=f"Concurrent workers for {source} (default {default_workers})")
	args = parser.parse_args()

	sources = [args.source] if args.source else sorted(SOURCE_URL_BUILDERS)
	summary = []
	for source in sources:
		workers = getattr(args, f"workers_{source}")
		summary.append(validate_source(source, workers=workers, timeout=args.timeout, max_retries=args.max_retries))

	print("\n=== SUMMARY ===")
	for row in summary:
		print(row)


if __name__ == "__main__":
	main()
