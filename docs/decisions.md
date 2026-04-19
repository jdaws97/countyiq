# Decision Log

This file now tracks only the decisions that matter to the current repo shape.

## Current Decisions

| Area | Current choice | Why it matters |
|---|---|---|
| Product lane | Real-estate intelligence for investors and developers in South-Central PA (2026-04-19) | Named buyer forces surface prioritization. See `docs/products/real-estate-intelligence.md`. |
| Repository shape | Single monorepo | Keeps frontend, API, pipelines, docs, and deploy assets together. |
| Runtime stack | React + FastAPI + Dagster + PostgreSQL/PostGIS | This is the active application architecture in code. |
| Routing | All API routes under `/api/*` | Matches the Caddy and Cloudflare-facing design. |
| Orchestration | Dagster | Active jobs, schedules, sensors, and asset graph already depend on it. |
| Database | PostgreSQL 16 + PostGIS | Canonical relational + spatial store. |
| Object storage | Cloudflare R2 | Used for raw data archives and off-database artifacts. |
| LLM backend | OpenRouter | This is the primary remote harness backend in active code. |
| Intelligence model split | Pass 0 separated from Passes 1-4 | Matches the actual env-var split in the enrichment assets. |
| Schema migrations | Alembic | Current migration path in `pipelines/alembic/versions/`. |
| Canonical parcel identifier | PIDN | Must remain consistent everywhere. |

## Current Operator Defaults

These are not hard-coded business decisions, but they are the current working defaults:

| Use case | Current default |
|---|---|
| Pass 0 PDF extraction | `x-ai/grok-4.1-fast` |
| Passes 1-4 | `xiaomi/mimo-v2-flash` |
| Thinking toggle | `COUNTYIQ_THINKING=true` |

## Provisional Decisions

| Area | Current stance | Notes |
|---|---|---|
| VPS provider | Prefer Hostinger for evaluation | Hetzner is no longer assumed. |
| Frontend hosting | Prefer Cloudflare Pages | Can still be revisited if the static site should live with the VPS stack. |
| Later-pass model lineup | Keep testing | Qwen 3.5 remains a candidate worth benchmarking again. |

## Legacy Decisions

These are older decisions that should not drive new work:

| Area | Status |
|---|---|
| AWS Lambda API path | Legacy |
| AWS/Terraform-first deployment plan | Archived under `archives/infrastructure/aws-terraform/` |
| AWS as the source of truth for runtime docs | Legacy |

## Tradeoffs We Are Accepting

| Tradeoff | Why |
|---|---|
| Single VPS remains a SPOF | Simpler operations and lower cost still outweigh clustering complexity at current scale. |
| Self-managed Postgres | Fits the containerized VPS direction and keeps the stack portable. |
| Manual migration application | Safer than auto-applying schema changes during rapid iteration. |
| Generated archives outside Postgres | Preserves LLM and source artifacts without bloating the database. |
