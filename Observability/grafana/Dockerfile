FROM grafana/grafana:latest

# No login wall: anonymous visitors get Admin straight away. This stack is meant for local/dev
# observability of JobManagerAgent, not a multi-tenant deployment -- put real auth back (unset
# these three) before relying on it anywhere but a private/internal Railway network.
ENV GF_AUTH_ANONYMOUS_ENABLED=true
ENV GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
ENV GF_AUTH_DISABLE_LOGIN_FORM=true
# Matches the Prometheus service's own Railway service name by default -- override per
# environment (docker-compose.yml overrides this for local dev).
ENV PROMETHEUS_URL=http://prometheus.railway.internal:9090

# Build context is the repo root (see railway.toml's dockerfilePath / docker-compose.yml's
# build.context), same convention as ObservabilityServer/Dockerfile.
USER root
COPY ./provisioning /etc/grafana/provisioning
COPY ./docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
# Restore the base image's own non-root user -- only the COPY/chmod above needed root.
USER grafana

ENTRYPOINT ["/docker-entrypoint.sh"]
