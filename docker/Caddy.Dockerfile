FROM node:26-alpine@sha256:2d984a15c9b54fd0aeb608b8e0d0d83529eb34d2966db27a1fb4f1edc3d298a3 AS frontend-build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm test
RUN npm run lint
RUN npm run build

FROM caddy:2-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648

# Port 8080 needs no privileged-port capability. File capabilities conflict
# with the Compose cap_drop: ALL boundary and prevent exec on startup.
RUN setcap -r /usr/bin/caddy

COPY docker/Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend-build /app/dist /srv
