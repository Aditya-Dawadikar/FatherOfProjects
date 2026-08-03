FROM grafana/grafana:latest

# No login wall: anonymous visitors get Admin straight away. This stack is meant for local/dev
# observability of JobManagerAgent, not a multi-tenant deployment -- put real auth back (unset
# these three) before relying on it anywhere but a private/internal Railway network.
ENV GF_AUTH_ANONYMOUS_ENABLED=true
ENV GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
ENV GF_AUTH_DISABLE_LOGIN_FORM=true
# Grafana blocks iframe embedding by default (X-Frame-Options: deny) -- JobDataDashboard's Agent
# Vitals tab embeds the dashboard directly, so both are needed: allow_embedding drops the
# X-Frame-Options block, and cookie samesite=none lets Grafana's anonymous-session cookie survive
# being loaded from a different origin inside an iframe (the two dashboards are separate Railway
# services/domains). Secure cookies require HTTPS, which Railway's domains already provide.
ENV GF_SECURITY_ALLOW_EMBEDDING=true
ENV GF_SECURITY_COOKIE_SAMESITE=none
# Matches the Prometheus service's own Railway service name by default -- override per
# environment (docker-compose.yml overrides this for local dev).
ENV PROMETHEUS_URL=http://prometheus.railway.internal:9090

# Build context is this folder (docker-compose.yml's build.context; on Railway, this service's
# Root Directory must be set to Observability/grafana so dockerfilePath="Dockerfile" resolves
# here too) -- not the repo root.
USER root
COPY ./provisioning /etc/grafana/provisioning
COPY ./docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
# Restore the base image's own non-root user -- only the COPY/chmod above needed root.
USER grafana

ENTRYPOINT ["/docker-entrypoint.sh"]
