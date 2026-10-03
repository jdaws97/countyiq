# Pipeline Code Structure

`pipelines/` is the Python 3.11 Dagster project. Runtime code lives in the
`countyiq` package; Alembic migrations, tests, and manual development tools
sit beside it.

## Layout

| Path                              | Responsibility                                                                                                                                                                     |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `countyiq/assets/`                | Dagster assets and asset checks, grouped by source type                                                                                                                            |
| `countyiq/lib/`                   | Parsers, clients, SCD2 helpers, LLM passes, and shared domain logic                                                                                                                |
| `countyiq/resources/`             | PostgreSQL and R2 resource construction                                                                                                                                            |
| `countyiq/jobs/`                  | Asset selections for manually runnable jobs                                                                                                                                        |
| `countyiq/definitions.py`         | Registers assets, checks, explicit jobs, and resources                                                                                                                             |
| `countyiq/run_job.py`             | Executes a local job and synchronously publishes health receipts                                                                                                                   |
| `countyiq/lib/run_reporting.py`   | Projects completed runs and asset checks into application health                                                                                                                   |
| `countyiq/lib/remote_pipeline.py` | Keeps the production SSH tunnel and writer lease alive                                                                                                                             |
| `alembic/versions/`               | Ordered database migrations                                                                                                                                                        |
| `tests/`                          | Unit, contract, parser, wiring, and database-backed tests                                                                                                                          |
| `eval/`                           | Manual model-comparison runner and report tool                                                                                                                                     |
| `scripts/`                        | The `run_pipeline.py` entry point and bounded manual tools, including `backtest_radar_weights.py` (calibrates opportunity weights against historical plan filings; no model calls) |

Asset groups currently include `arcgis`, `radar`, `bulk`, `scrapers`,
`enrichment`, `paused_sources`, and `manual_sources`. The latter two
are intentionally outside ordinary refresh jobs. Parsers belong under `countyiq/lib/parsers/`; source-specific
configuration belongs in `countyiq/lib/county_config.py`.

## Registration

`countyiq/definitions.py` loads assets and asset checks from the package, then
registers explicit jobs and resources. A new asset is
discoverable when it is imported by its package and loaded through that module
tree. A new job must also be added to the registry. There are no registered
schedules or sensors; the operator invokes jobs or asset subsets locally.

Dagster resource parameters on assets must be type-annotated. Otherwise Dagster
interprets them as asset dependencies.

## Data Contracts

- PIDN is the parcel key.
- County-specific URLs, filters, and thresholds come from `county_config.py`.
- Source jobs select only assets whose county capability is configured. The
  local runner rejects an empty job and a subset outside its selected job.
  A new county manifest can omit optional sources without creating
  predictably failing network runs.
- Raw payloads are archived to R2 before parsing.
- Staging tables use SCD Type 2 (`valid_from`, `valid_to`).
- `public.properties` is a view.
- Schema changes go through Alembic.
- Model output is a proposal, not source truth. `intelligence_integrity.py`
  validates exact Pass 0 quotes, explicit Pass 1 membership and source IDs,
  Pass 2 evidence references, and Pass 3 inline citations before projection.
  Failures append operator-visible metadata and validator errors to
  `meta.intelligence_validation_rejections`; invalid payloads never project.
- Pass 0–3 writes append immutable provenance first. A semantic flip on an
  unchanged evidence hash is quarantined; only an accepted inference may
  replace a current projection. Model, prompt, provider, payload, citations,
  evidence references, and supersession are retained in `meta` history.
- Quarantined flips first pass through `lib/intelligence_autoresolve.py`
  (rule policy, optional `lib/intelligence_judge.py` confirmation); routine
  ones resolve automatically and are marked `auto_resolution`. What remains
  is the human queue in `meta.intelligence_review_queue`, operated through
  `scripts/review_intelligence_contradictions.py` (`list`, `show`, `resolve`,
  `auto`, and the sampled audit `sample` / `approve` / `reject`). The writer
  transaction appends the resolving version and updates or retracts the
  serving projection atomically. `scripts/verify_intelligence_preflight.py`
  is the no-model, read-only gate before any paid run; after a pass's first
  accepted run it enforces the live gate pass rate instead of a label receipt.

## Local Workflow

```bash
cd pipelines
uv sync --locked --extra dev
.venv/bin/python -m pytest tests/ -q -m "not integration"
.venv/bin/python scripts/run_pipeline.py --local --job deterministic_enrichment_refresh
```

Use the local Docker Postgres instructions in `AGENTS.md` for database-backed
tests and migrations. The command uses explicit development `DATABASE_*`
settings. For production, use the protected SSH session documented in
[Local pipeline commands](../operations/local-pipelines.md).
