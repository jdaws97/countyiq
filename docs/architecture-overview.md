# Architecture Overview

CountyIQ is currently a containerized civic intelligence stack with Cloudflare in front, a React frontend, a FastAPI API, and Dagster pipelines feeding PostgreSQL/PostGIS.

## System Shape

```text
Users
  |
  v
Cloudflare
  - DNS / CDN / TLS / WAF
  - Cloudflare Pages for the frontend (current preferred setup)
  - Cloudflare R2 for raw archives and tile/object storage
  |
  v
Ubuntu VPS (current target: generic container host, likely Hostinger)
  - Caddy
  - FastAPI
  - Dagster
  - PostgreSQL 16 + PostGIS
```

## Request Flow

- `/*`: frontend, ideally served from Cloudflare Pages
- `/api/*`: proxied to FastAPI behind Caddy
- raw archives and tile-like artifacts: stored outside Postgres, primarily in Cloudflare R2

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

OpenRouter is the primary remote inference backend. Local GGUF support remains in the harness for evaluation and fallback.

## Deployment Reality

- The current deployment story is containerized VPS plus Cloudflare, not AWS Lambda.
- Hostinger is the current preferred VPS option to evaluate.
- Hetzner references in older materials are historical, not architectural requirements.
- The old AWS/Terraform stack has been archived under `archives/infrastructure/aws-terraform/` and should not be treated as an active deployment path.
