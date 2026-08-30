# Pipeline Code Structure

`pipelines/` is the Python 3.11 Dagster project. Runtime code lives in the
`countyiq` package; Alembic migrations, tests, and manual development tools
sit beside it.

## Layout

| Path | Responsibility |
|---|---|
| `countyiq/assets/` | Dagster assets and asset checks, grouped by source type |
| `countyiq/lib/` | Parsers, clients, SCD2 helpers, LLM passes, and shared domain logic |
| `countyiq/resources/` | PostgreSQL and R2 resource construction |
| `countyiq/jobs/` | Asset selections for manually runnable jobs |
| `countyiq/schedules/` | Cron schedules for those jobs |
| `countyiq/sensors/` | Run-status alerting |
| `countyiq/definitions.py` | Registers assets, checks, jobs, schedules, sensors, and resources |
| `alembic/versions/` | Ordered database migrations |
| `tests/` | Unit, contract, parser, wiring, and database-backed tests |
| `eval/` | Manual model-comparison runner and report tool |
| `scripts/` | Small manual smoke tests that do not belong to the Dagster graph |

Asset groups currently include `arcgis`, `radar`, `bulk`, `scrapers`,
`enrichment`, `scout`, `paused_sources`, and `manual_sources`. The latter two
are intentionally outside scheduled production jobs. Parsers belong under `countyiq/lib/parsers/`; source-specific
configuration belongs in `countyiq/lib/county_config.py`.

## Registration

`countyiq/definitions.py` loads assets and asset checks from the package, then
registers explicit jobs, schedules, sensors, and resources. A new asset is
discoverable when it is imported by its package and loaded through that module
tree. A new job or schedule must also be added to the corresponding registry.

Dagster resource parameters on assets must be type-annotated. Otherwise Dagster
interprets them as asset dependencies.

## Data Contracts

- PIDN is the parcel key.
- County-specific URLs, filters, and thresholds come from `county_config.py`.
- Scheduled source jobs select only assets whose county capability is
  configured, and optional job schedules are registered only when at least one
  matching capability exists. A new county manifest can omit optional sources
  without creating empty or predictably failing network runs.
- Raw payloads are archived to R2 before parsing.
- Staging tables use SCD Type 2 (`valid_from`, `valid_to`).
- `public.properties` is a view.
- Schema changes go through Alembic.

## Local Workflow

```bash
cd pipelines
uv sync --locked --extra dev
.venv/bin/python -m pytest tests/ -q -k "not integration"
.venv/bin/dagster dev -m countyiq.definitions
```

Use the local Docker Postgres instructions in `AGENTS.md` for database-backed
tests and migrations.
