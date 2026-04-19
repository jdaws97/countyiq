---
name: countyiq
description: |
  CountyIQ development skill for working in the CountyIQ monorepo. Use this skill whenever the task touches Dagster assets or jobs, FastAPI routes, the React frontend, PostgreSQL/PostGIS schema, deployment docs, York County source ingestion, entity resolution, development signals, County Scout, or the LLM-backed intelligence pipeline.
---

# CountyIQ Development Skill

CountyIQ is a York County civic intelligence platform with a monorepo containing:

- `frontend/`: React application
- `api/`: FastAPI service
- `pipelines/`: Dagster pipelines and enrichment passes
- `docker/`: containerized deployment assets

The current project center of gravity is the intelligence platform: source ingestion plus Passes 0-4 using the shared OpenRouter harness.

## Read These First

Only read the docs you need. Treat the files below as the current source of truth:

| File | Use it for |
|---|---|
| `docs/current-state.md` | Fast orientation on what the repo is today |
| `docs/architecture-overview.md` | High-level system shape |
| `docs/infrastructure.md` | Current deployment direction |
| `docs/open-items.md` | What is actually left to work through |
| `docs/decisions.md` | Current vs provisional vs legacy decisions |
| `docs/schema/strategy.md` | PIDN, schema layout, and property-view rules |
| `docs/schema/migrations.md` | Alembic and migration workflow |
| `docs/api/api.md` | API behavior and deployment shape |
| `docs/frontend/architecture.md` | Frontend surfaces and stack |
| `docs/pipelines/code-structure.md` | Dagster/package layout |
| `docs/products/county-scout.md` | County Scout product notes |

Historical plans, implementation phases, and draft research have been moved under `archives/docs/`. Do not treat them as current unless the active docs explicitly send you there.

## Hard Rules

### Identifiers

- PIDN is the canonical parcel identifier everywhere.
- Do not introduce `parcel_id` as a competing concept.

### Schema

- No `raw` schema in Postgres.
- Raw source payloads belong in object storage, not relational tables.
- Staging tables are SCD Type 2 with `valid_from` / `valid_to`.
- `public.properties` is a view, not a base table.

### Routing

- API routes live under `/api/*`.
- The frontend's `/ops/health` page calls `GET /api/ops/health`.

### County Configuration

- County-specific URLs, thresholds, and filters belong in `countyiq/lib/county_config.py`.
- Do not hardcode York County strings or endpoints inside reusable assets/parsers when config should own them.

### Dagster

- Dagster resource arguments in `@asset` functions must be type-annotated.
- Keep jobs, schedules, and asset dependencies aligned with what actually exists in code.

## Current Deployment Reality

- The active deployment direction is containerized VPS plus Cloudflare.
- Hostinger is the current preferred provider to evaluate.
- Hetzner references are historical context only.
- The old AWS/Terraform stack lives under `archives/infrastructure/aws-terraform/` and is not the current source of truth.

## LLM Harness Reality

The intelligence passes currently use the shared harness in `pipelines/countyiq/lib/llm_harness.py`.

- Pass 0 prefers `COUNTYIQ_PASS0_MODEL`
- Passes 1-4 prefer `COUNTYIQ_PASS{N}_MODEL`, then fall back to `COUNTYIQ_OPENROUTER_MODEL`
- `COUNTYIQ_THINKING` is the global fallback; passes can override it with `COUNTYIQ_PASS{N}_THINKING`
- `COUNTYIQ_ARCHIVE_DIR` controls runtime archive output

Current operator defaults:

- Pass 0 operator default: `x-ai/grok-4.1-fast`
- Later-pass operator default: `xiaomi/mimo-v2-flash`
- Qwen 3.5 remains a live evaluation candidate

## Task Routing

### If the task is pipeline-related

Read:

- `docs/current-state.md`
- `docs/pipelines/code-structure.md`
- `docs/schema/strategy.md`

Then inspect:

- `pipelines/countyiq/definitions.py`
- the relevant asset group under `pipelines/countyiq/assets/`
- the matching tests in `pipelines/tests/`

### If the task is API-related

Read:

- `docs/current-state.md`
- `docs/api/api.md`

Then inspect:

- `api/main.py`
- `api/routes/`

### If the task is frontend-related

Read:

- `docs/current-state.md`
- `docs/frontend/architecture.md`

Then inspect:

- `frontend/src/App.tsx`
- `frontend/src/pages/`

### If the task is deployment/docs cleanup

Read:

- `docs/current-state.md`
- `docs/infrastructure.md`
- `docs/open-items.md`
- `docs/decisions.md`

Then assume:

- AWS/Lambda-era material outside the archive is legacy unless the user explicitly wants it preserved.
