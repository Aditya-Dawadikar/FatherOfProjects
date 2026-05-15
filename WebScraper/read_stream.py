from __future__ import annotations

import argparse
import json

from redis import Redis

from scraper import load_env_value
from stream_events import DEFAULT_STREAM_NAME


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Read WebScraper events from Redis Stream")
	parser.add_argument("--count", type=int, default=10, help="Maximum number of events to read")
	parser.add_argument(
		"--last-id",
		default="0-0",
		help="Stream entry ID to start after. Use '$' to wait for new events only.",
	)
	parser.add_argument(
		"--block-ms",
		type=int,
		default=0,
		help="Milliseconds to block for new events when using XREAD. Use 0 to return immediately.",
	)
	return parser.parse_args()


def load_stream_config() -> tuple[str, str]:
	redis_url = load_env_value("REDIS_URL")
	try:
		stream_name = load_env_value("REDIS_STREAM_NAME")
	except KeyError:
		stream_name = DEFAULT_STREAM_NAME
	return redis_url, stream_name


def try_parse_json(value: str) -> object:
	if not value:
		return value
	if value[0] not in "[{\"":
		return value
	try:
		return json.loads(value)
	except json.JSONDecodeError:
		return value


def main() -> None:
	args = parse_args()
	redis_url, stream_name = load_stream_config()
	client = Redis.from_url(redis_url, decode_responses=True)

	response = client.xread(
		{stream_name: args.last_id},
		count=args.count,
		block=args.block_ms or None,
	)

	if not response:
		print("No stream entries found.")
		return

	for _, entries in response:
		for entry_id, fields in entries:
			parsed_fields = {key: try_parse_json(value) for key, value in fields.items()}
			print(json.dumps({"id": entry_id, "fields": parsed_fields}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
	main()