# Infrastructure

## Current Direction

CountyIQ's current infrastructure direction is:

- Cloudflare in front for DNS, CDN, TLS, and WAF
- Cloudflare R2 for raw archives and object storage
- a single Ubuntu VPS running Docker Compose
- Caddy for reverse proxy
- FastAPI, Dagster, and PostgreSQL/PostGIS as containers

The provider is not a hard architectural dependency. Hostinger is the current preferred VPS option to evaluate. Older Hetzner-specific language is historical context only.

## Runtime Topology

| Layer | Current expectation |
|---|---|
| Front door | Cloudflare |
| Frontend | Cloudflare Pages preferred |
| API | FastAPI behind Caddy on the VPS |
| Pipelines | Dagster on the VPS |
| Database | PostgreSQL 16 + PostGIS on the VPS |
| Raw archive store | Cloudflare R2 |
| LLM backend | OpenRouter |

## Container Services

The production Compose stack in `docker/docker-compose.yml` is the current deployment reference:

| Service | Purpose |
|---|---|
| `postgres` | application database + PostGIS |
| `api` | FastAPI/Uvicorn |
| `dagster` | Dagster webserver + daemon |
| `caddy` | reverse proxy and TLS termination |
| `watchtower` | image polling / restarts |

## Required Environment

Production expects a root `.env` file with:

```bash
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_NAME=countyiq
DATABASE_USER=dagster_admin
DATABASE_PASSWORD=...
DATABASE_URL=postgresql://dagster_admin:...@postgres:5432/countyiq

OPENROUTER_API_KEY=...
COUNTYIQ_PASS0_MODEL=x-ai/grok-4.1-fast
COUNTYIQ_PASS1_MODEL=
COUNTYIQ_PASS2_MODEL=
COUNTYIQ_PASS3_MODEL=
COUNTYIQ_PASS4_MODEL=
COUNTYIQ_OPENROUTER_MODEL=xiaomi/mimo-v2-flash
COUNTYIQ_SEARCH_MODEL=
COUNTYIQ_THINKING=true
COUNTYIQ_ARCHIVE_DIR=/opt/countyiq/archives

R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_ENDPOINT_URL=https://ACCOUNT_ID.r2.cloudflarestorage.com
S3_RAW_BUCKET=countyiq-raw
```

Notes:

- Pass 0 prefers `COUNTYIQ_PASS0_MODEL`.
- Passes 1-4 prefer `COUNTYIQ_PASS{N}_MODEL`, then fall back to `COUNTYIQ_OPENROUTER_MODEL`.
- Search can use `COUNTYIQ_SEARCH_MODEL`, then fall back to `COUNTYIQ_OPENROUTER_MODEL`.
- `COUNTYIQ_THINKING` is only the global fallback; pass-specific overrides are supported.

## Access Model

- Public traffic should only reach Cloudflare and Caddy.
- Postgres and Dagster should stay private to the host and SSH tunnels.
- SSH key auth only.

## Backups And Archives

- PostgreSQL backups: `pg_dump` plus off-host storage
- raw pipeline archives: Cloudflare R2
- LLM output archives: `COUNTYIQ_ARCHIVE_DIR`

The archives are operational artifacts, not core repo content. They should not be committed to git.

## CI/CD

Current expected flow:

1. GitHub Actions builds/publishes container images.
2. Frontend can deploy independently via Cloudflare Pages.
3. The VPS pulls updated images and restarts containers.
4. Alembic migrations remain an explicit operator step.

## Legacy Material

The old AWS/Terraform deployment stack has been archived under `archives/infrastructure/aws-terraform/`.
It remains available for historical reference, but it is no longer part of the active deployment path.
