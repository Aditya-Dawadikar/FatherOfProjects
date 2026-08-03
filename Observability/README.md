# Observability

Prometheus + Grafana stack for scraping JobManagerAgent's system metrics. Deployable both as a
local docker-compose stack and as two separate Railway services (Prometheus and Grafana each get
their own Dockerfile/railway.toml, same one-folder-per-service convention as the rest of this repo).

JobManagerAgent runs a background thread (`integrations/metrics/collector.py`) that samples
CPU, memory, disk, and network usage on an interval (`METRICS_COLLECTION_INTERVAL_SECONDS`,
default 15s) and caches it in-memory as Prometheus gauges. `GET /metrics` on the agent's API
(default `http://localhost:8080/metrics`) serves whatever was last cached -- it never scrapes
the OS on request.

## Run locally

```
cd Observability
docker compose up -d --build
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001 (no login -- anonymous Admin access, see `grafana/Dockerfile`)

Grafana comes pre-provisioned with a `Prometheus` datasource (`grafana/provisioning/datasources/prometheus.yml`);
no manual setup needed to start building dashboards.

## Environment variables

### JobManagerAgent (`JobManagerAgent/.env.example`)

| Variable | Default | Purpose |
| --- | --- | --- |
| `METRICS_COLLECTION_INTERVAL_SECONDS` | `15` | How often the background thread refreshes the cached CPU/memory/disk/network gauges. `/metrics` always serves this cache; it never scrapes the OS per-request. |
| `METRICS_DISK_PATH` | unset -> `Path.cwd().anchor` (`C:\` locally, `/` on the Linux Railway deployment) | Filesystem path disk usage is sampled from. Only set this if you want a path other than the current drive/volume root. |

### Prometheus service (`Observability/prometheus/`)

| Variable | Default (baked into the Dockerfile/entrypoint) | Set it to, on Railway |
| --- | --- | --- |
| `SCRAPE_TARGET` | `host.docker.internal:8080` | JobManagerAgent's Railway-internal address, e.g. `jobmanageragent.railway.internal:8080` (adjust the port if JobManagerAgent's own `PORT` differs from 8080 there). |
| `PORT` | `9090` (compose maps the host port instead) | Set automatically by Railway -- don't set this yourself. |

`SCRAPE_TARGET` is set explicitly in `docker-compose.yml` for local dev; on Railway it must be set on the **prometheus** service itself (Railway dashboard -> Variables), since there's no docker-compose there to set it for you.

### Grafana service (`Observability/grafana/`)

| Variable | Default (baked into the Dockerfile) | Set it to, on Railway |
| --- | --- | --- |
| `PROMETHEUS_URL` | `http://prometheus.railway.internal:9090` | `http://<prometheus-service-name>.railway.internal:9090`, matching whatever you actually named the Prometheus service. Only needs overriding if you name that service something other than `prometheus`. |
| `GF_AUTH_ANONYMOUS_ENABLED` | `true` | Leave as-is to keep the no-login setup; see the security note below. |
| `GF_AUTH_ANONYMOUS_ORG_ROLE` | `Admin` | Same. |
| `GF_AUTH_DISABLE_LOGIN_FORM` | `true` | Same. |
| `PORT` | `3000` (compose maps the host port instead) | Set automatically by Railway -- don't set this yourself. |

`PROMETHEUS_URL` is set explicitly in `docker-compose.yml` for local dev (`http://prometheus:9090`, compose's built-in service-name DNS); on Railway it must be set on the **grafana** service itself if the Prometheus service isn't named exactly `prometheus`.

## Deploy to Railway

Prometheus and Grafana are two independent Railway services, both built from this repo via a
Dockerfile (`builder = "DOCKERFILE"` in each `railway.toml`, same as `ObservabilityServer`) --
Railway doesn't run docker-compose directly, so each container needs its own service.

1. In the Railway project, add a new service for each of `Observability/prometheus/` and
   `Observability/grafana/`, pointing each at this repo. Railway will pick up the
   `dockerfilePath` from that folder's `railway.toml` automatically (repo root stays the build
   context, matching `ObservabilityServer`).
2. Set `SCRAPE_TARGET` on the **prometheus** service and `PROMETHEUS_URL` on the **grafana**
   service -- see the Environment variables tables above for values. Both services read
   Railway's `$PORT` automatically; don't set it yourself.

**Security note:** Grafana ships with anonymous Admin access and no login form (see
`grafana/Dockerfile`), as requested for this stack. That's fine behind Railway's private
networking, but if you expose the Grafana service on a public Railway domain, anyone with the
URL gets Admin. Turn a real auth method back on (drop the three `GF_AUTH_*` env vars) before
doing that.

## Metrics exposed by JobManagerAgent

All gauges are prefixed `jobmanageragent_`:

- `jobmanageragent_cpu_usage_percent`, `jobmanageragent_cpu_count`
- `jobmanageragent_memory_used_bytes`, `jobmanageragent_memory_total_bytes`, `jobmanageragent_memory_usage_percent`
- `jobmanageragent_disk_used_bytes`, `jobmanageragent_disk_total_bytes`, `jobmanageragent_disk_usage_percent`
- `jobmanageragent_network_bytes_sent_total`, `jobmanageragent_network_bytes_received_total`
- `jobmanageragent_metrics_last_collected_timestamp_seconds` -- when the cache was last refreshed; useful for alerting on a stuck collector thread
