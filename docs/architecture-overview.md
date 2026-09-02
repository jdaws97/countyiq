# Architecture Overview

CountyIQ is a containerized real-estate intelligence stack with Cloudflare in
front, a React frontend, a FastAPI API, and Dagster pipelines feeding
PostgreSQL/PostGIS.

## System Shape

```text
Users
  |
  v
Cloudflare
  - DNS / CDN / TLS / WAF
  - Cloudflare Pages for the frontend (current preferred setup)
  - Cloudflare R2 for selected raw-source and backup archives
  |
  v
Ubuntu VPS (Hetzner)
  - Caddy
  - FastAPI
  - Dagster
  - PostgreSQL 16 + PostGIS
```

## Request Flow

- `/*`: frontend, ideally served from Cloudflare Pages
- `/api/*`: proxied to FastAPI behind Caddy
- selected source and backup archives: stored outside Postgres in Cloudflare R2

## Data Flow

1. Dagster assets ingest county source data into `staging.*`.
2. Enrichment assets derive `public.*` outputs such as signals, evidence, briefs, and narratives.
3. The API reads PostgreSQL/PostGIS and serves parcel, owner, search, radar, and ops endpoints.
4. The frontend renders those surfaces for map, search, intelligence, and monitoring workflows.

## Module and Authority Boundaries

CountyIQ remains one monorepo, but it is not one runtime:

- `frontend/` depends on the documented HTTP contract, never Python internals.
- `api/` is a read-only serving process. It must not import Dagster or pipeline
  packages and receives only the API database role.
- `pipelines/countyiq/` owns ingestion, enrichment, and serving-projection
  writes. It must not import the API package and uses a separate writer role.
- `pipelines/alembic/` is the sole schema authority. Only the short-lived
  `migrate` service receives the administrator URL.
- `docker/` owns deployment orchestration, release receipts, and backup/restore
  operations. Application startup never applies migrations.

The import and Compose contracts are executable in
`pipelines/tests/test_architecture_boundaries.py`. Database tables and HTTP
schemas are the explicit integration seams; source imports across the API and
pipeline packages are rejected.

## Intelligence Pipeline

The current repo is no longer just an MVP property browser. It includes an LLM-backed intelligence pipeline:

- Pass 0: proceeding extraction from PDFs
- Pass 1: entity verification
- Pass 2: batched signal validation
- Pass 3: parcel brief generation
- Pass 4: county narrative generation

OpenRouter is the only inference backend in the production harness. Model
fallbacks are alternate OpenRouter routes selected through explicit pass
configuration.

## Deployment Reality

- The current deployment story is containerized VPS plus Cloudflare, not AWS Lambda.
- Hetzner is the selected VPS provider; Netcup is the fallback.
- The Compose project and persistent-volume names are fixed, while application
  images are tagged with the exact reviewed Git SHA.
- `docker/deploy.sh` is the only production release path. It validates the
  environment, quiesces API and pipeline writers, verifies an off-host backup,
  applies migrations, checks readiness, and writes a release receipt.
- AWS/Lambda/Terraform deployment material is historical and is not kept in the
  working tree.
