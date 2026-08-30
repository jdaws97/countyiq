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
- AWS/Lambda/Terraform deployment material is historical and is not kept in the
  working tree.
