# Testing and Verification

Verification is layered. A narrow unit test cannot prove Dagster registration,
database migrations, a production bundle, or a real browser flow.

## Pipeline

Install exactly what is locked and run the non-integration suite:

```bash
cd pipelines
uv sync --locked --extra dev
.venv/bin/python -m pytest tests/ -q -k "not integration"
```

For asset, job, schedule, resource, or configuration wiring changes, also load
the complete definitions graph:

```bash
cd pipelines
.venv/bin/python -c "from countyiq.definitions import defs; print('definitions OK')"
```

Parser tests use small captured source fixtures. Network calls and model calls
do not belong in the normal unit suite. Live source checks are manual and
targeted because public sites are slow and fragile.

## API

Fast unit tests do not require Postgres:

```bash
uv sync --project api --locked
api/.venv/bin/python -m pytest api/unit_tests -q
```

Contract tests use the dedicated `postgres-test` container on port 5433. The
session fixture starts the container, creates `countyiq_test`, applies every
migration, resets only the test tables, seeds a minimal York-shaped dataset,
and calls FastAPI with `TestClient`.

```bash
cd pipelines
docker compose up -d postgres-test
cd ..
uv sync --project api --locked
api/.venv/bin/python -m pytest api/tests -v
```

Never point contract tests at the development or production `countyiq`
database; the fixture truncates its dedicated schema state.

Current contract coverage includes health, property details, municipality
details, the unified feed, radar, owner briefs/relationships, and the response
fields shared with the frontend.

## Database and Migrations

For a clean migration-chain check:

```bash
cd pipelines
docker compose up -d postgres-test
DATABASE_HOST=localhost \
DATABASE_PORT=5433 \
DATABASE_NAME=countyiq_test \
DATABASE_USER=dagster_admin \
DATABASE_PASSWORD=localtest \
DATABASE_URL=postgresql://dagster_admin:localtest@localhost:5433/countyiq_test \
  uv run --locked alembic upgrade head
```

The PostGIS extensions and base schemas from the ordered `init-db/*.sql`
scripts must exist before Alembic runs. Use `docker compose down -v` only when
an intentional, fully destructive test-volume reset is required.

## Frontend

```bash
cd frontend
npm ci
npx tsc -b
npm run lint
npm run build
```

Run the production build whenever routing, bundling, dependencies, or shared
types change. Meaningful UI changes also require a real Playwright browser
check:

1. start the Vite dev server or production preview;
2. open the changed route;
3. exercise navigation and the relevant interaction;
4. inspect browser console and failed requests;
5. recheck at a narrow viewport when layout is affected.

## Container Builds

Both Python images install from checked-in uv lockfiles:

```bash
docker build -f api/Dockerfile -t countyiq-api:test .
docker build -f pipelines/Dockerfile -t countyiq-pipelines:test .
```

The API image health endpoint is `/api/health`. The Dagster image must load
`countyiq.definitions` and expose `/server_info`.

## Continuous Integration

`.github/workflows/ci.yml` runs:

- the locked pipeline environment, definitions smoke test, and non-integration
  pipeline suite;
- the locked API environment and API unit tests;
- frontend clean install, typecheck, and lint.

`.github/workflows/api-contract-tests.yml` additionally starts the dedicated
PostGIS test container and runs the migration-backed API contract suite for API
or pipeline changes.

## Production Data Checks

Dagster asset checks are registered separately from assets and run against
materialized data. They cover record counts, schema drift, and enrichment
integrity. They complement tests; they do not replace parser, migration,
contract, or browser verification.

For each source refresh, operators should be able to answer:

- Did raw payload archival succeed?
- Is the current row count plausible relative to the prior materialization?
- Did schema fields disappear or change type?
- Did SCD2 expiration/insertion behave as expected?
- Are downstream event and enrichment counts explainable?
