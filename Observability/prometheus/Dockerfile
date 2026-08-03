FROM prom/prometheus:latest

# Build context is this folder (docker-compose.yml's build.context; on Railway, this service's
# Root Directory must be set to Observability/prometheus so dockerfilePath="Dockerfile" resolves
# here too) -- not the repo root.
USER root
COPY ./prometheus.yml /etc/prometheus/prometheus.yml.template
COPY ./docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
# Restore the base image's own non-root user (nobody owns /etc/prometheus and /prometheus) --
# only the COPY/chmod above needed root.
USER nobody

ENTRYPOINT ["/docker-entrypoint.sh"]
