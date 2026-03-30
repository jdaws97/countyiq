# Testing Strategy

## Testing Strategy

### Guiding Principle

Practical tests that catch real problems before merge. No mocks, no fake data fixtures, no elaborate test infrastructure. Three layers: CI catches code bugs, smoke tests catch deploy problems, Dagster asset checks catch data quality issues in production.

### Layer 1: Pre-Merge Checks (GitHub Actions CI)

A new workflow that runs on **pull requests** to `main` (not on push — the deploy workflows handle push). Tests must pass before the PR can be merged.

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
    branches: [main]
    paths:
      - 'pipelines/**'
      - 'api/**'
      - 'frontend/**'
      - '.github/workflows/ci.yml'

jobs:
  lint-and-type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dev dependencies
        run: pip install ruff mypy

      - name: Lint (ruff)
        run: ruff check pipelines/ api/

      - name: Type check (mypy)
        run: mypy pipelines/ api/ --ignore-missing-imports

  pipeline-schema-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -e pipelines/[dev]

      - name: Run schema validation tests
        run: pytest pipelines/tests/ -v

  frontend-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install and build
        working-directory: frontend
        run: |
          npm ci
          npm run build
```

**What this catches:**
- Syntax errors, unused imports, formatting issues (ruff)
- Type mismatches, missing attributes (mypy)
- Schema/parsing regressions (pytest)
- Frontend build failures (npm)

**What this intentionally does NOT do:**
- Hit live APIs (flaky, slow, rate limits)
- Require a database (no Docker Postgres in CI)
- Run integration tests (that's what Dagster asset checks do in production)

### Schema Validation Tests

Each pipeline source defines its expected output schema. Tests verify that the parsing logic produces the right structure. These use sample response fixtures (a small saved JSON/HTML file checked into the repo).

```
pipelines/
├── tests/
│   ├── conftest.py
│   ├── fixtures/              # Small sample responses from each source
│   │   ├── parcels_sample.json
│   │   ├── crimewatch_sample.html
│   │   ├── plcb_sample.csv
│   │   └── ...
│   ├── test_arcgis_parser.py
│   ├── test_crimewatch_parser.py
│   ├── test_plcb_parser.py
│   └── ...
```

**Example test:**

```python
# pipelines/tests/test_arcgis_parser.py
import json
from pathlib import Path
from pipelines.lib.parsers.arcgis import parse_parcels_response

FIXTURES = Path(__file__).parent / "fixtures"

def test_parcels_parser_returns_expected_fields():
    """Verify the parser produces all required columns."""
    sample = json.loads((FIXTURES / "parcels_sample.json").read_text())
    records = parse_parcels_response(sample)

    assert len(records) > 0
    required_fields = ["pidn", "owner_full", "propadr", "aprtotal", "saledt", "price"]
    for field in required_fields:
        assert field in records[0], f"Missing required field: {field}"


def test_parcels_parser_handles_null_values():
    """Verify the parser doesn't crash on null/missing fields."""
    sample = json.loads((FIXTURES / "parcels_sample.json").read_text())
    # Null out some fields to simulate real-world data
    sample["features"][0]["attributes"]["PRICE"] = None
    records = parse_parcels_response(sample)
    assert records[0]["price"] is None
```

**Effort per source:** ~1-2 test functions, ~15 minutes to write. The fixtures are just a small copy-paste from a real API response (already captured during feasibility testing).

### Layer 2: Smoke Test on Deploy

After the Dagster deploy workflow restarts services, verify they came up cleanly. Added as a final step in the `deploy-dagster.yml` workflow:

```yaml
      # After Watchtower pulls new image, verify via API health endpoint
      - name: Smoke test
        run: |
          sleep 60  # Wait for Watchtower to pull
          curl -f https://countyiq.com/api/health
```

You can also verify Dagster definitions loaded correctly by SSHing into the VPS:

```bash
# Smoke test: verify Dagster loaded all definitions
ssh countyiq 'docker exec countyiq-dagster dagster definitions list'
```

**What this catches:** Missing imports, broken config files, dependency issues that only surface when Dagster tries to load the full asset graph. These don't show up in unit tests because unit tests don't import the full Dagster definitions.

### Layer 3: Data Quality Checks (Dagster Asset Checks)

These run in production as part of the pipeline, not in CI. After each asset materializes, Dagster validates the output.

```python
# pipelines/lib/checks.py
from dagster import asset_check, AssetCheckResult, AssetCheckSeverity

@asset_check(asset="parcels_arcgis")
def parcels_record_count(context):
    """Verify parcel count is within expected range."""
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL"
    ).scalar()

    passed = 150_000 < count < 200_000  # Expected ~176K
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={"record_count": count},
        description=f"Got {count:,} records (expected 150K-200K)"
    )


@asset_check(asset="parcels_arcgis")
def parcels_no_null_pidn(context):
    """Verify no parcel records have null PIDN."""
    conn = get_connection()
    null_count = conn.execute(
        "SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL AND pidn IS NULL"
    ).scalar()

    return AssetCheckResult(
        passed=null_count == 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"null_pidn_count": null_count}
    )


@asset_check(asset="crimewatch_incidents")
def crimewatch_not_empty(context):
    """Verify scraper returned at least some incidents."""
    conn = get_connection()
    today_count = conn.execute(
        "SELECT COUNT(*) FROM staging.crimewatch WHERE DATE(created_at) = CURRENT_DATE"
    ).scalar()

    return AssetCheckResult(
        passed=today_count > 0,
        severity=AssetCheckSeverity.WARN,
        metadata={"today_count": today_count},
        description=f"Got {today_count} incidents today"
    )
```

**Failed checks trigger the Slack alerting pipeline** described in the Error Handling section:
- `WARN` severity → `#alerts-warning`
- `ERROR` severity → `#alerts-critical`

### What Each Layer Catches

| Problem | Layer 1 (CI) | Layer 2 (Smoke) | Layer 3 (Checks) |
|---|---|---|---|
| Syntax error in pipeline code | ✅ ruff | | |
| Type mismatch in function call | ✅ mypy | | |
| Parser returns wrong columns | ✅ pytest | | |
| Missing import after refactor | ✅ mypy | ✅ definition load | |
| Broken Dagster config | | ✅ definition load | |
| Website changed HTML structure | | | ✅ schema check |
| API returned 0 records | | | ✅ count check |
| Source went offline | | | ✅ run failure → retry → alert |
| Database constraint violation | | | ✅ run failure → alert |
| Frontend won't build | ✅ npm build | | |

### Dev Dependencies

```toml
# pipelines/pyproject.toml [project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.4",
    "mypy>=1.10",
]
```

### What's Intentionally NOT Included

| Approach | Why Skipped |
|---|---|
| Integration tests with live APIs | Flaky, slow, may hit rate limits; asset checks cover this in production |
| Docker Postgres in CI | Adds build time and complexity; schema migration testing is done locally (see Alembic section) |
| End-to-end frontend tests (Cypress, Playwright) | Overkill for MVP; manual browser testing is fine initially |
| Code coverage requirements | Chasing coverage percentages leads to bad tests; focus on meaningful assertions |
| Snapshot testing | Brittle; breaks on any output change even if the change is correct |
