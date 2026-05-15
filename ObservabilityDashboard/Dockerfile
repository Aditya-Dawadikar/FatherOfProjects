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
