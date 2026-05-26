FROM node:22-alpine AS build

WORKDIR /app/JobDataDashboard

COPY JobDataDashboard/package.json ./package.json
COPY JobDataDashboard/package-lock.json ./package-lock.json

RUN npm ci

COPY JobDataDashboard/ ./

RUN npm run build

FROM caddy:2-alpine

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/JobDataDashboard/dist /usr/share/caddy

EXPOSE 8080

CMD ["/bin/sh", "-c", "echo '[job-data-dashboard-runtime] PORT='\"${PORT:-8080}\"' JOB_DATA_API_UPSTREAM='\"${JOB_DATA_API_UPSTREAM:-<unset>}\"; exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile"]