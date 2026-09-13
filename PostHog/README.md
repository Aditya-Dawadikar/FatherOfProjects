# PostHog

Self-hosted PostHog, used to see how far people actually explore JobDataDashboard when it's shared
with recruiters -- which tabs they reach, how deep they go, where they drop off, and (via session
recordings) what a real visit looks like. Deployed the same way as every other service in this
repo: a folder per component, each with its own `Dockerfile` + `railway.toml`, pointed at PostHog's
own published images -- no Railway template, no vendored PostHog source. Portable to any Docker
host by copying the same three Dockerfiles and re-pointing the env vars.

## Services

| Folder | Image | Role |
| --- | --- | --- |
| `PostHog/app/` | `posthog/posthog:latest` | The actual PostHog application. Runs the image's own default entrypoint (`bin/docker`): migrations, then a worker process and the web/API server together in one container -- PostHog's supported single-container ("hobby") mode, gated by `DEPLOYMENT=hobby`. |
| `PostHog/clickhouse/` | `clickhouse/clickhouse-server:24.8-alpine` | Analytics event store. |
| `PostHog/kafka/` | `bitnami/kafka:3.7` | Single-broker, KRaft mode (no separate Zookeeper container) -- right-sized for hobby-scale traffic. |

Postgres, Redis, and object storage (for session recordings) are **not** hand-built -- they're
Railway's own managed Postgres/Redis services plus a Railway Bucket, wired in via variable
references, same pattern the rest of this repo already uses for its own Postgres/Redis.

## Environment variables

Set these as Railway variables on the **PostHog app** service (`PostHog/app/`):

| Variable | Value |
| --- | --- |
| `DEPLOYMENT` | `hobby` |
| `SITE_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` (after generating a domain for this service) |
| `SECRET_KEY` | a random 50+ char secret (sealed variable) |
| `IS_BEHIND_PROXY` | `true` |
| `DISABLE_SECURE_SSL_REDIRECT` | `true` |
| `DATABASE_URL` | `${{PostHog-Postgres.DATABASE_URL}}` |
| `REDIS_URL` | `${{PostHog-Redis.REDIS_URL}}` |
| `CLICKHOUSE_HOST` | `${{PostHog-ClickHouse.RAILWAY_PRIVATE_DOMAIN}}` |
| `CLICKHOUSE_DATABASE` | `posthog` |
| `CLICKHOUSE_SECURE` | `false` |
| `CLICKHOUSE_VERIFY` | `false` |
| `KAFKA_HOSTS` | `${{PostHog-Kafka.RAILWAY_PRIVATE_DOMAIN}}:9092` |
| `OBJECT_STORAGE_ENABLED` | `true` |
| `OBJECT_STORAGE_ENDPOINT` | bucket endpoint from `railway bucket credentials` |
| `OBJECT_STORAGE_ACCESS_KEY_ID` / `OBJECT_STORAGE_SECRET_ACCESS_KEY` | bucket credentials |
| `OBJECT_STORAGE_BUCKET` | the bucket name |

On **PostHog-ClickHouse**: `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DB=posthog` (the
official image bootstraps from these on first boot). Attach a Railway volume at
`/var/lib/clickhouse` so events survive a redeploy.

On **PostHog-Kafka** (single-node KRaft bootstrap):

```
KAFKA_ENABLE_KRAFT=yes
KAFKA_CFG_PROCESS_ROLES=broker,controller
KAFKA_CFG_NODE_ID=1
KAFKA_CFG_CONTROLLER_LISTENER_NAMES=CONTROLLER
KAFKA_CFG_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093
KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
KAFKA_CFG_ADVERTISED_LISTENERS=PLAINTEXT://${{RAILWAY_PRIVATE_DOMAIN}}:9092
KAFKA_CFG_CONTROLLER_QUORUM_VOTERS=1@localhost:9093
KAFKA_KRAFT_CLUSTER_ID=<fixed-22-char-base64-id, generate once and never change it>
ALLOW_PLAINTEXT_LISTENER=yes
```

## Wiring into JobDataDashboard

Same as before -- see `.env.example` in `JobDataDashboard/JobDataDashboard/`:

| Variable | Value |
| --- | --- |
| `VITE_POSTHOG_KEY` | Project API key, from the PostHog instance's first-run signup (Project Settings) |
| `VITE_POSTHOG_HOST` | The PostHog app service's public URL |

Instrumentation itself (`src/lib/posthog.ts`, pageview tracking in `Layout.tsx`, the
`feature_flag_toggled`/`rate_limit_distribution_updated` events) is unchanged by where PostHog
runs -- see git history on this file for that part.

## Moving to a different host

Nothing here depends on Railway specifically: the three Dockerfiles just wrap public images.
Rebuild them anywhere Docker runs, point `DATABASE_URL`/`REDIS_URL`/`CLICKHOUSE_HOST`/`KAFKA_HOSTS`
at wherever those backing services live there, and update `VITE_POSTHOG_HOST` in the dashboard.

## Notes / caveats

- **Single-broker Kafka and single-node ClickHouse** have no redundancy. Fine for hobby-scale
  portfolio traffic; not a production-grade analytics pipeline.
- **`posthog/posthog:latest`** tracks upstream continuously -- pin to a specific tag/digest if a
  reproducible build matters more than always running current PostHog.
- If the app container crash-loops on boot, check its logs first (`railway logs --service PostHog`)
  -- `bin/docker`'s migration step is the most common failure point (usually a ClickHouse/Kafka/
  Postgres connectivity issue, not an app bug).
