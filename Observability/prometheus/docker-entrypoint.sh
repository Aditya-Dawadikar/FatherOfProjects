#!/bin/sh
set -e

# Prometheus config has no env-var expansion, so the scrape target is templated in via sed
# instead -- see prometheus.yml's __SCRAPE_TARGET__ placeholder.
SCRAPE_TARGET="${SCRAPE_TARGET:-host.docker.internal:8080}"
sed "s|__SCRAPE_TARGET__|${SCRAPE_TARGET}|g" /etc/prometheus/prometheus.yml.template > /etc/prometheus/prometheus.yml

# Railway assigns this service's public/internal port via $PORT; default to Prometheus's usual
# 9090 for local docker-compose, where the port is instead fixed by the compose file's mapping.
exec /bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus \
  --web.listen-address=":${PORT:-9090}"
