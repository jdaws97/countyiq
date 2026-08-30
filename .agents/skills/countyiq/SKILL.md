---
name: countyiq
description: |
  CountyIQ development skill for working in the CountyIQ monorepo. Use this skill whenever the task touches Dagster assets or jobs, FastAPI routes, the React frontend, PostgreSQL/PostGIS schema, deployment docs, York County source ingestion, entity resolution, development signals, County Scout, or the LLM-backed intelligence pipeline.
---

# CountyIQ Development Skill

CountyIQ is a York County real-estate intelligence platform with a monorepo containing:

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

Superseded plans and one-off research are intentionally absent from the working
tree; use git history when historical context is genuinely needed.

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

- Nothing is deployed yet. The intended deployment is Docker Compose on
  Hetzner plus Cloudflare; treat it as a target architecture until a live
  environment is explicitly verified.
- Netcup is the fallback VPS provider.
- AWS/Lambda/Terraform deployment paths are legacy.

## LLM Harness Reality

The intelligence passes currently use the shared harness in `pipelines/countyiq/lib/llm_harness.py`.

- Passes 0-4 resolve `COUNTYIQ_PASS{N}_MODEL`, then the evaluated code
  default, then `COUNTYIQ_OPENROUTER_MODEL`
- `COUNTYIQ_THINKING` is the global fallback; passes can override it with `COUNTYIQ_PASS{N}_THINKING`
- `COUNTYIQ_ARCHIVE_DIR` controls runtime archive output
- Every pass sends its static instruction block as a system message
  (`system_prompt` on `HarnessConfig`) so providers with implicit prompt
  caching reuse it; keep static text in the `*_SYSTEM_PROMPT` constants and
  per-item data in the user templates when editing prompts
- Other knobs: `COUNTYIQ_PASS{N}_REASONING_EFFORT`, `COUNTYIQ_PASS1_TRIALS` /
  `COUNTYIQ_PASS2_TRIALS` (N-trial voting), `COUNTYIQ_PASS1_ESCALATION_MODEL`
  (abstention cascade), `COUNTYIQ_PASS0_PDF_ENGINE` (default `native`)

Current model defaults and their evidence live in `docs/decisions.md` and
`pipelines/countyiq/lib/pass_llm_config.py`. Do not copy model slugs into this
skill; they change independently.

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

Then assume AWS/Lambda/Terraform material is legacy unless the user explicitly
wants it restored from git history.
