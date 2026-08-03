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

# Inherited from the base image already, but declared explicitly here since Railway uses this
# (and the healthcheck path in railway.toml) to find the fixed port docker-entrypoint.sh binds to.
EXPOSE 9090

ENTRYPOINT ["/docker-entrypoint.sh"]
