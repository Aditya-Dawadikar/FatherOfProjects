FROM clickhouse/clickhouse-server:24.8-alpine

# PostHog's own Django ClickHouse migrations run with `replicated=True` and use `ON CLUSTER`
# DDL even for a single node -- a bare ClickHouse container fails migration with "Requested
# cluster 'posthog_migrations' not found". config.xml/default.xml/users.xml below are PostHog's
# actual self-host config files (pulled from github.com/PostHog/posthog/docker/clickhouse/,
# vendored here as plain static files, not a live source checkout) with default.xml's cluster
# hosts changed from the docker-compose service name "clickhouse" to "localhost" (this is a
# single-node self-referencing cluster, so the node just points at itself). The env-var bootstrap
# (CLICKHOUSE_USER/PASSWORD/DB, set as Railway variables) still layers on top via the official
# image's own users.d/ generation -- replacing users.xml doesn't disable that.
#
# Deliberately NOT included: PostHog/docker/clickhouse/user_defined_function.xml. Its executable
# UDFs (funnel aggregation, etc.) need matching binaries in /var/lib/clickhouse/user_scripts that
# ship with the full posthog/posthog source tree -- without them ClickHouse fails to start
# entirely. Skipping it means some advanced funnel insights won't work; core event ingestion,
# autocapture, and session recordings don't depend on it.
COPY config.xml /etc/clickhouse-server/config.xml
COPY default.xml /etc/clickhouse-server/config.d/default.xml
COPY users.xml /etc/clickhouse-server/users.xml

# Data persists via a Railway volume mounted at /var/lib/clickhouse (attach one in the Railway
# dashboard; volumes aren't expressible in railway.toml).
EXPOSE 8123 9000
