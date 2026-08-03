FROM prom/prometheus:latest

# Build context is the repo root (see railway.toml's dockerfilePath / docker-compose.yml's
# build.context) so this Dockerfile can COPY files from anywhere in the monorepo, same
# convention as ObservabilityServer/Dockerfile.
USER root
COPY Observability/prometheus/prometheus.yml /etc/prometheus/prometheus.yml.template
COPY Observability/prometheus/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
# Restore the base image's own non-root user (nobody owns /etc/prometheus and /prometheus) --
# only the COPY/chmod above needed root.
USER nobody

ENTRYPOINT ["/docker-entrypoint.sh"]
