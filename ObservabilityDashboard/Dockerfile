FROM node:22-alpine AS build

WORKDIR /app/ObservabilityDashboard

COPY ObservabilityDashboard/package.json ./package.json
COPY ObservabilityDashboard/package-lock.json ./package-lock.json

RUN npm ci

COPY ObservabilityDashboard/ ./

RUN npm run build

FROM caddy:2-alpine

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/ObservabilityDashboard/dist /usr/share/caddy

EXPOSE 8080

CMD ["/bin/sh", "-c", "echo '[dashboard-runtime] PORT='\"${PORT:-8080}\"' OBSERVABILITY_API_UPSTREAM='\"${OBSERVABILITY_API_UPSTREAM:-<unset>}\"; exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile"]
