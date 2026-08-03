#!/bin/sh
set -e

# Prometheus config has no env-var expansion, so the scrape target is templated in via sed
# instead -- see prometheus.yml's __SCRAPE_TARGET__ placeholder.
SCRAPE_TARGET="${SCRAPE_TARGET:-host.docker.internal:8080}"
sed "s|__SCRAPE_TARGET__|${SCRAPE_TARGET}|g" /etc/prometheus/prometheus.yml.template > /etc/prometheus/prometheus.yml

# Prometheus itself never logs incoming requests (confirmed against --log.level=debug), so this
# is the only place that will ever say what this container actually resolved at startup --
# useful for confirming SCRAPE_TARGET took effect without inspecting the generated config file.
# To see who's actually calling this container (including Railway's own healthcheck), use
# `railway logs --service Prometheus --http` instead -- that's Railway's edge proxy logging each
# inbound request (path/status/duration), which is a layer above anything this container can see.
echo "prometheus-entrypoint: scrape_target=${SCRAPE_TARGET} listen_address=0.0.0.0:9090"

# Deliberately NOT reading $PORT here: Prometheus is only ever reached over Railway's private
# network (by Grafana, and by Railway's own healthcheck), never through a public-domain proxy --
# unlike Grafana's entrypoint, which does need to track $PORT. Always listening on the fixed
# 9090 keeps this consistent with the image's own EXPOSE and with Grafana's PROMETHEUS_URL
# default (Observability/grafana/Dockerfile), both of which assume port 9090.
exec /bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus
