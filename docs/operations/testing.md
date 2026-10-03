# Testing and Verification

Verification is layered. A narrow unit test cannot prove Dagster registration,
database migrations, a production bundle, or a real browser flow.

## Pipeline

Install exactly what is locked and run the non-integration suite:

```bash
cd pipelines
uv sync --locked --extra dev
.venv/bin/python -m pytest tests/ -q -m "not integration"
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

Integration tests (`-m integration`) are destructive: they delete and truncate
staging tables and append to audit ledgers. They may only run against the
dedicated `countyiq_test` database on the `postgres-test` container, migrated
to the repository head first:

```bash
cd pipelines
DATABASE_URL=postgresql://dagster_admin:localtest@localhost:5433/countyiq_test \
  .venv/bin/alembic upgrade head
DATABASE_NAME=countyiq_test .venv/bin/python -m pytest tests/ -q -m integration
```

`tests/conftest.py` wraps `psycopg2.connect` for every test session and
refuses the live `countyiq` database by name, including through
`DatabaseResource` and DSN strings, because a test that defaulted to it
deleted all 175,935 local parcels on 2026-09-02. Set
`COUNTYIQ_ALLOW_LIVE_DB_TESTS=1` only for a deliberate, read-only check
against a disposable restore.

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

The API liveness endpoint is `/api/health`; container readiness uses
`/api/ready`, which also verifies a database query. The Dagster image must load
`countyiq.definitions` and expose `/server_info`.

Deployment changes also require the non-mutating configuration gate:

```bash
bash -n docker/setup.sh docker/backup.sh docker/deploy.sh \
  docker/restore-drill.sh docker/lib/operations.sh
COUNTYIQ_DEPLOY_REF="$(git rev-parse HEAD)" \
COUNTYIQ_ENV_FILE="$PWD/.env" \
  docker/deploy.sh --check
```

The preflight deliberately rejects a dirty tree, placeholder credentials,
enabled paid passes, missing R2 lock confirmation, and a Compose graph that
cannot resolve. It does not contact R2, mutate Docker, or prove the live host.

## Continuous Integration

`.github/workflows/ci.yml` runs:

- the locked pipeline environment, definitions smoke test, and non-integration
  pipeline suite;
- the locked API environment and API unit tests;
- frontend clean install, typecheck, and lint.
- npm and Python dependency vulnerability audits;
- production Compose, deployment preflight/script syntax, and Caddy
  configuration validation.

`.github/workflows/api-contract-tests.yml` additionally starts the dedicated
PostGIS test container and runs the migration-backed API contract suite for API
or pipeline changes.

`.github/workflows/security.yml` declares the availability of GitHub-hosted
dependency review and CodeQL. On October 3, both were unavailable for this private
repository: dependency review rejected its missing entitlement/dependency graph,
and CodeQL rejected uploads because code scanning was disabled. The checked-in
`CODEQL_STATE` and `DEPENDENCY_REVIEW_STATE` declarations are `unavailable`;
the workflow reports those scanners as skipped, without claiming they passed.
Missing or invalid declarations fail. When the relevant feature is enabled in
GitHub, change its declaration to `enabled`; ordinary scanner failures then remain
enforcing. No billing or repository feature settings are changed by this workflow.

CI still enforces Gitleaks, npm/pip dependency audits and high-severity Python
Bandit checks on every pull request and main push. These do not replace CodeQL's
semantic analysis coverage. Weekly and manual Security runs reuse the complete
CI workflow so those available checks also run without a code change. Actions
remain pinned to full commit SHAs. Local release review should also run Gitleaks
against the exact working tree; CI repeats that scan.

GitHub documents [private-repository code scanning availability](https://docs.github.com/en/code-security/reference/code-scanning/troubleshoot-analysis-errors/private-repository-enablement),
[dependency-review requirements](https://github.com/actions/dependency-review-action#installation-standard)
and [reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows).

The API contract fixture provisions the same dedicated read-only database role
used by production and asserts the API connection has
`transaction_read_only=on`.

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
