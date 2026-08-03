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

# Documents the port docker-entrypoint.sh binds to by default. Railway's healthcheck actually
# targets whatever $PORT it assigns this service at runtime (see docker-entrypoint.sh), not this
# EXPOSE -- set PORT=9090 explicitly as a Railway variable on this service so the two agree.
EXPOSE 9090

ENTRYPOINT ["/docker-entrypoint.sh"]
