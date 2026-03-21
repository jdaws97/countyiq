# CountyIQ — Claude Code Instructions

## Local Development Rules

These rules apply to ALL local development work. Follow them exactly.

### Python

- **Use `uv`, not `pip` or `venv`.** The system Python is 3.10; the project requires 3.11.
- Create venvs with: `uv venv .venv --python 3.11`
- Install packages with: `uv pip install -e ".[dev]"`
- **Never use `python` — always use `python3` or the venv's `python`** (`source .venv/bin/activate` first, or `.venv/bin/python`).
- The pipelines venv lives at `pipelines/.venv/`. Always `cd pipelines` and `source .venv/bin/activate` before running pipeline code.

### Docker Postgres (Local Testing)

- Start: `cd pipelines && docker compose up -d postgres-test`
- Connection: `postgresql://dagster_admin:localtest@localhost:5433/york_county_intel`
- Apply schema: run `init.sql` first (extensions/schemas), then `alembic upgrade head` (tables)
- Stop: `docker compose down -v` (with `-v` to reset data, without to keep it)

### Local-First Development

- **Do NOT run `terraform apply`** until Phase 5. All code is built and verified locally against Docker Postgres first.
- API testing: `cd api && uvicorn main:app --reload --port 8000`
- Frontend testing: `cd frontend && npm run dev` (Vite on localhost:5173)
- Pipeline testing: `cd pipelines && source .venv/bin/activate && pytest tests/ -v`
- Dagster UI: `cd pipelines && source .venv/bin/activate && dagster dev -m york_county.definitions`

### Environment Variables for Local Dev

```bash
export DATABASE_HOST=localhost
export DATABASE_PORT=5433
export DATABASE_NAME=york_county_intel
export DATABASE_USER=dagster_admin
export DATABASE_PASSWORD=localtest
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/york_county_intel"
```

## Project Conventions

- **York County first, built to expand.** We are building for York County PA. But all pipeline code must be county-agnostic — no hardcoded county names, URLs, or thresholds in assets or parsers. Use `county_config.py` instead.
- **County config pattern:** Every pipeline asset calls `get_county_config()` from `york_county/lib/county_config.py` to get URLs, filter strings, and thresholds. Parsers accept county-specific params (e.g., `county_filter`) rather than hardcoding values. Never hardcode `"York County"`, ArcGIS URLs, or record count thresholds directly in asset or parser code.
- **PIDN** (13-char string) is the canonical parcel identifier everywhere. Not PARID, not `parcel_id`.
- No `raw` schema in RDS/Postgres. Raw data goes to S3 (`s3://york-county-raw/<prefix>/<source>/<date>/`).
- All staging tables use SCD Type 2 (`valid_from`/`valid_to`).
- `public.properties` is a VIEW, not a table.
- Lambda API routes are all under `/api/*`.
- Dagster resource params in `@asset` functions must be type-annotated (e.g., `database: DatabaseResource`) or Dagster treats them as asset dependencies.

## Skills & Tools — When to Use

### Always use first

| Trigger | Skill/Tool | Why |
|---|---|---|
| Any task in this repo | `countyiq` skill | Loads full architecture context — routes you to the right docs, enforces hard rules (PIDN, schema layout, Lambda constraints). **Invoke this before doing anything.** |
| Before writing code that uses an external library | **Context7** (`context7`) | Pull current API docs. Dagster, FastAPI, Alembic, MapLibre, Deck.gl all have breaking changes between versions. Don't guess — check. |

### Use when the task matches

| Trigger | Skill/Tool |
|---|---|
| Building a Playwright scraper (Assessment, eFACTS, CRIMEWATCH, PALS) | **Playwright MCP** — navigate the live site, inspect DOM, test selectors, take screenshots BEFORE writing the parser |
| Building React components, pages, or UI layouts | **`frontend-design` skill** — produces distinctive, production-grade UI |
| Verifying frontend renders correctly | **Playwright MCP** — navigate to localhost:5173 or CloudFront URL, take screenshots |
| Starting a multi-step implementation task | **`superpowers:writing-plans`** — plan before coding |
| Completing a major step (source asset, API route, frontend view) | **`superpowers:requesting-code-review`** — review against plan and standards |
| 2+ independent tasks that can run in parallel | **`superpowers:dispatching-parallel-agents`** — e.g., building FEMA + PA Open Data assets simultaneously |
| About to claim work is done | **`superpowers:verification-before-completion`** — run verification commands, confirm output before asserting success |
| Encountering a bug or test failure | **`superpowers:systematic-debugging`** — diagnose before proposing fixes |
