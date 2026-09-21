FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS frontend-build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm test
RUN npm run lint
RUN npm run build

FROM caddy:2-alpine@sha256:de23def33b17fb5d1290b0f6c2add1d70780e52341896c00a4c8a2a2fe9d355e

# Port 8080 needs no privileged-port capability. File capabilities conflict
# with the Compose cap_drop: ALL boundary and prevent exec on startup.
RUN setcap -r /usr/bin/caddy

COPY docker/Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend-build /app/dist /srv
