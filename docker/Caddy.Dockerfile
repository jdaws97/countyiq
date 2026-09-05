FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS frontend-build

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
