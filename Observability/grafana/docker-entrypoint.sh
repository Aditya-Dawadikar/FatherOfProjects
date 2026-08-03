#!/bin/sh
set -e

# Railway assigns this service's port via $PORT; Grafana's own knob for that is
# GF_SERVER_HTTP_PORT (default 3000, which local docker-compose relies on via its port mapping).
export GF_SERVER_HTTP_PORT="${PORT:-3000}"
exec /run.sh
