#!/bin/sh
set -e

# Prometheus config has no env-var expansion, so the scrape target is templated in via sed
# instead -- see prometheus.yml's __SCRAPE_TARGET__ placeholder.
SCRAPE_TARGET="${SCRAPE_TARGET:-host.docker.internal:8080}"
sed "s|__SCRAPE_TARGET__|${SCRAPE_TARGET}|g" /etc/prometheus/prometheus.yml.template > /etc/prometheus/prometheus.yml

# Railway's own healthcheck targets whatever $PORT this service was assigned -- confirmed
# empirically (SSH into the running container showed it bound to :8080, matching the last
# successful deployment's logs, even though the image's own EXPOSE says 9090). A hardcoded
# --web.listen-address here previously broke the healthcheck because nothing was actually
# listening on the port Railway was probing. Set PORT=9090 explicitly as a Railway variable on
# this service (Variables tab) to keep that assignment predictable and matching Grafana's
# PROMETHEUS_URL default (Observability/grafana/Dockerfile) -- don't rely on whatever Railway
# would otherwise assign implicitly.
PORT="${PORT:-9090}"
echo "prometheus-entrypoint: scrape_target=${SCRAPE_TARGET} listen_address=0.0.0.0:${PORT}"

exec /bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus \
  --web.listen-address=":${PORT}"
