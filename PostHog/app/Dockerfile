FROM posthog/posthog:latest

# The base image's own default entrypoint (bin/docker) runs migrations, then a worker process
# and the web server in one container -- exactly the "hobby"/monolith mode PostHog's own code
# gates on DEPLOYMENT=hobby (set as a Railway variable on this service, alongside DATABASE_URL/
# REDIS_URL/CLICKHOUSE_HOST/KAFKA_HOSTS/SECRET_KEY/SITE_URL). No command override needed -- this
# is a plain pass-through, same as Observability/prometheus's Dockerfile wrapping prom/prometheus.
EXPOSE 8000
