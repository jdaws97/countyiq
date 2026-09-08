---
name: countyiq
description: |
  Architecture router for the CountyIQ monorepo. Use for cross-cutting or architecture-sensitive work involving data identity/schema, Dagster wiring, API/frontend contracts, deployment, county ingestion, entity resolution, or intelligence/LLM passes. Do not use for meta-review, status checks, simple lookups, or trivial edits.
---

# CountyIQ Development Skill

CountyIQ is a York County real-estate intelligence platform with a React
frontend, FastAPI service, Dagster pipelines, and PostgreSQL/PostGIS storage.
Use this skill as a router, not as a prereading checklist. Paths below are
relative to the repository root.

## Working Method

- Follow `AGENTS.md` for scope, authorization, delegation, and verification.
- Use `docs/current-state.md` for cross-cutting orientation only.
- Use `docs/architecture-overview.md` for system boundaries,
  `docs/decisions.md` when reopening a decision, and `docs/open-items.md` only
  for planned or unresolved work.
- When documentation and executable behavior conflict, verify the code and call
  out the mismatch rather than silently choosing one.

## Current Invariants

Reevaluate these defaults when the user reopens a decision or current repository
evidence contradicts them.

- **Identity:** PIDN is the canonical parcel identifier; do not introduce
  `parcel_id` as a competing concept.
- **Schema:** raw payloads belong in object storage rather than a Postgres `raw`
  schema; staging tables use SCD Type 2 `valid_from` / `valid_to`; and
  `public.properties` is a view.
- **Routing:** API routes live under `/api/*`; frontend `/ops/health` calls
  `GET /api/ops/health`.
- **County configuration:** county URLs, thresholds, and filters belong in
  `pipelines/countyiq/lib/county_config.py` rather than reusable assets or parsers.
- **Dagster:** resource arguments in `@asset` functions are type-annotated; jobs,
  schedules, and dependencies stay aligned with executable definitions.

## Task Router

| Area | Inspect first | Load only if needed |
|---|---|---|
| Pipelines | Relevant asset/library and matching `pipelines/tests/` tests | `docs/pipelines/code-structure.md`; add `docs/schema/strategy.md` for identity/storage |
| API | Relevant route/library and matching API tests | `docs/api/api.md`; `api/main.py` for registration or app wiring |
| Frontend | Relevant component/page/state module and tests | `docs/frontend/architecture.md`; `frontend/src/App.tsx` for routing or app-shell work |
| Schema | Migration, affected SQL/model code, and schema tests | `docs/schema/strategy.md` and `docs/schema/migrations.md` |
| Deployment | The specific deployment artifact | `docs/current-state.md` and `docs/infrastructure.md` |
| Product/docs | The affected surface or document | `docs/products/real-estate-intelligence.md`; decisions/open-items only for status or history |

## Volatile Details

Do not copy changing deployment status, model names, or environment knobs into
this skill.

- Verify deployment claims from current docs and the environment; never assume a
  target architecture is live.
- For intelligence passes, inspect the relevant pass,
  `pipelines/countyiq/lib/llm_harness.py`,
  `pipelines/countyiq/lib/pass_llm_config.py`, tests, and decisions as needed.
- For prompt changes, inspect prompt-cache and integrity tests. Keep static
  instructions in system-prompt constants and per-item data in user templates;
  let tests define current thresholds and citation requirements.
