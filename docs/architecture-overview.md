# Architecture Overview

CountyIQ is a containerized real-estate intelligence stack with Cloudflare in
front, a React frontend, a FastAPI API, and local Dagster jobs feeding
PostgreSQL/PostGIS on the VPS.

This page describes repository configuration. Deployment status and hostname
rollout steps live in [Account workspaces](operations/account-workspaces.md#guarded-hostname-rollout).

## System Shape

```text
Users
  |
  v
Cloudflare
  - DNS / CDN / TLS / WAF
  - Access for invited testers on the app host
  - Tunnel to the private origin
  - Cloudflare R2 for selected raw-source and backup archives
  |
  v
Ubuntu VPS
  - cloudflared (outbound Tunnel connector)
  - Caddy (marketing/app static files and API proxy)
  - FastAPI
  - PostgreSQL 16 + PostGIS

Operator PC
  - Explicit Dagster CLI jobs and native authoring scripts
  - Direct source acquisition and governed R2 archives
  - Local SQLite run history and logs
  - Temporary SSH connection to the VPS writer role
```

## Request Flow

- `countyiq.net`: public marketing HTML; Sign in opens `app.countyiq.net`.
- `app.countyiq.net`: application HTML and all product routes, gated by
  Cloudflare Access for testing.
- App-host `/api/*`: proxied by Caddy to FastAPI, which verifies configured
  customer identity. Marketing-host API requests return 404.
- Cloudflare terminates public TLS; Tunnel reaches Caddy on private port 8080.
  Both frontend entries are built and served with the VPS web image.
- Selected source and backup archives: stored outside Postgres in Cloudflare R2

## Data Flow

1. The operator runs a named job or asset subset on the PC. Dagster assets
   acquire sources directly and write county data into `staging.*` through the
   protected SSH session.
2. Enrichment assets derive `public.*` outputs such as signals, evidence, briefs, and narratives.
3. The API reads PostgreSQL/PostGIS and serves parcel, owner, search, radar, and ops endpoints.
4. The frontend renders those surfaces for map, search, intelligence, and monitoring workflows.
5. The local runner records job and source outcomes in the application health
   ledgers before exiting; full run history stays on the PC.

There is no deployed Dagster daemon, scheduler, sensor process, or webserver in
this release model. See [Local pipeline commands](operations/local-pipelines.md)
for the executable workflow and state paths. Deployment receipts establish
whether that model is active on a particular host.

## Module and Authority Boundaries

CountyIQ remains one monorepo, but it is not one runtime:

- `frontend/` depends on the documented HTTP contract, never Python internals.
- `api/` reads source data and performs scoped account/workspace writes using
  only the API database role. It must not import Dagster or pipeline packages.
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

- Pass 0: proceeding extraction from PDFs
- Pass 1: entity verification
- Pass 2: batched signal validation
- Pass 3: parcel brief generation
- Pass 4: county narrative generation

Inference can use explicitly enabled OpenRouter passes or supported native
subscription authoring on the PC. Source refresh sessions force all inference
passes off. Model configuration and quality gates still apply; a successful
source refresh does not authorize model work.

## Deployment Reality

- The Compose project and persistent-volume names are fixed, while application
  images are tagged with the exact reviewed Git SHA.
- `docker/deploy.sh` is the only production release path. It validates the
  environment, excludes local pipeline sessions with the host deployment lock,
  quiesces application writers, verifies an off-host backup,
  applies migrations, checks readiness, and writes a release receipt.
- `infra/cloudflare/` manages Cloudflare DNS, Tunnel, and Access using OpenTofu.
