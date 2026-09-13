FROM clickhouse/clickhouse-server:24.8-alpine

# The official image bootstraps a user/database from CLICKHOUSE_USER/CLICKHOUSE_PASSWORD/
# CLICKHOUSE_DB env vars (set as Railway variables on this service) -- no custom config.xml/
# users.xml needed at hobby scale. Data persists via a Railway volume mounted at
# /var/lib/clickhouse (attach one in the Railway dashboard; not expressible in railway.toml).
EXPOSE 8123 9000
