# Intelligence Platform Phase 1: Data Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data infrastructure (new tables, new pipelines, source URL provenance) that the intelligence reasoning pipeline will consume in Phase 2.

**Architecture:** Two new data source pipelines (PA DOS Corporate Entities, Public Proceedings) feed into new staging tables alongside existing data. All staging tables gain `source_url` for evidence provenance. Intelligence output tables (evidence, parcel_briefs, county_narratives, entity_graph) are created now but populated in Phase 2. Pass 0 (multimodal document extraction) converts meeting minute PDFs into structured records.

**Tech Stack:** Dagster (asset orchestration), psycopg2 (database), Alembic (migrations), Playwright (PA DOS scraping), requests (PDF downloads), llama-cpp-python (multimodal extraction), pdf2image (PDF rendering)

**Spec:** `docs/superpowers/specs/2026-04-03-intelligence-platform-repositioning-design.md`

**Subsequent plans:**
- Phase 2: LLM Harness & Reasoning Pipeline (Passes 1-4, model testing)
- Phase 3-5: API + Frontend + Cleanup

---

### Task 1: Alembic Migration — New Tables

**Files:**
- Create: `pipelines/alembic/versions/012_intelligence_platform.py`

- [ ] **Step 1: Write the migration**

```python
"""Intelligence platform tables: staging sources, public intelligence output, meta tracking

Revision ID: 012
Revises: 011
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- New staging tables ---

    op.create_table(
        "corporate_entities",
        sa.Column("entity_name", sa.Text, nullable=False),
        sa.Column("entity_number", sa.Text),
        sa.Column("entity_type", sa.Text),
        sa.Column("status", sa.Text),
        sa.Column("formation_date", sa.Date),
        sa.Column("registered_agent_name", sa.Text),
        sa.Column("registered_agent_address", sa.Text),
        sa.Column("office_address", sa.Text),
        sa.Column("officers", JSONB),
        sa.Column("source_url", sa.Text),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("entity_name", "valid_from"),
        schema="staging",
    )
    op.create_index(
        "idx_corporate_entities_current",
        "corporate_entities",
        ["entity_name"],
        schema="staging",
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "idx_corporate_entities_agent",
        "corporate_entities",
        ["registered_agent_name"],
        schema="staging",
        postgresql_where=sa.text("valid_to IS NULL"),
    )

    op.create_table(
        "public_proceedings",
        sa.Column("id", sa.Integer, autoincrement=True, nullable=False),
        sa.Column("body_name", sa.Text, nullable=False),
        sa.Column("meeting_date", sa.Date, nullable=False),
        sa.Column("proceeding_type", sa.Text, nullable=False),
        sa.Column("raw_text", sa.Text),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("document_url", sa.Text),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
        schema="staging",
    )
    op.create_index(
        "idx_proceedings_body_date",
        "public_proceedings",
        ["body_name", "meeting_date"],
        schema="staging",
    )

    op.create_table(
        "proceeding_extractions",
        sa.Column("id", sa.Integer, autoincrement=True, nullable=False),
        sa.Column("proceeding_id", sa.Integer, nullable=False),
        sa.Column("extraction_type", sa.Text, nullable=False),
        sa.Column("applicant_name", sa.Text),
        sa.Column("parcel_reference", sa.Text),
        sa.Column("current_zoning", sa.Text),
        sa.Column("proposed_zoning", sa.Text),
        sa.Column("decision", sa.Text),
        sa.Column("conditions", JSONB),
        sa.Column("supporting_text", sa.Text),
        sa.Column("extraction_confidence", sa.Float),
        sa.Column("model_used", sa.Text),
        sa.Column("page_number", sa.Integer),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["proceeding_id"],
            ["staging.public_proceedings.id"],
            name="fk_extraction_proceeding",
        ),
        schema="staging",
    )
    op.create_index(
        "idx_extractions_applicant",
        "proceeding_extractions",
        ["applicant_name"],
        schema="staging",
    )
    op.create_index(
        "idx_extractions_parcel",
        "proceeding_extractions",
        ["parcel_reference"],
        schema="staging",
    )

    # --- Intelligence output tables (public schema) ---

    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer, autoincrement=True, nullable=False),
        sa.Column("pidn", sa.Text, nullable=False),
        sa.Column("signal_key", sa.Text, nullable=False),
        sa.Column("claim", sa.Text),
        sa.Column("evidence_data", JSONB),
        sa.Column("source_url", sa.Text),
        sa.Column("internal_url", sa.Text),
        sa.Column("validation_status", sa.Text),
        sa.Column("adjusted_significance", sa.Text),
        sa.Column("validation_reasoning", sa.Text),
        sa.Column("cross_references", JSONB),
        sa.Column("validated_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pidn", "signal_key", name="uq_evidence_pidn_signal"),
        schema="public",
    )
    op.create_index(
        "idx_evidence_pidn",
        "evidence",
        ["pidn"],
        schema="public",
    )

    op.create_table(
        "parcel_briefs",
        sa.Column("pidn", sa.Text, nullable=False),
        sa.Column("brief_text", sa.Text),
        sa.Column("assessment", sa.Text),
        sa.Column("assessment_reasoning", sa.Text),
        sa.Column("key_questions", sa.ARRAY(sa.Text)),
        sa.Column("signal_count", sa.Integer),
        sa.Column("citations", JSONB),
        sa.Column("brief_version", sa.Integer, server_default=sa.text("1")),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("pass_metadata", JSONB),
        sa.PrimaryKeyConstraint("pidn"),
        schema="public",
    )

    op.create_table(
        "county_narratives",
        sa.Column("narrative_id", sa.Integer, autoincrement=True, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("narrative_type", sa.Text, nullable=False),
        sa.Column("trajectory", sa.Text),
        sa.Column("affected_pidns", sa.ARRAY(sa.Text)),
        sa.Column("key_entities", sa.ARRAY(sa.Text)),
        sa.Column("citations", JSONB),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("narrative_id"),
        schema="public",
    )

    op.create_table(
        "entity_graph",
        sa.Column("entity_id", sa.Integer, autoincrement=True, nullable=False),
        sa.Column("canonical_name", sa.Text, nullable=False),
        sa.Column("entity_type", sa.Text),
        sa.Column("linked_names", sa.ARRAY(sa.Text)),
        sa.Column("linked_sources", JSONB),
        sa.Column("relationships", JSONB),
        sa.Column("verification_status", sa.Text),
        sa.Column("verification_reasoning", sa.Text),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("entity_id"),
        schema="public",
    )
    op.create_index(
        "idx_entity_graph_name",
        "entity_graph",
        ["canonical_name"],
        schema="public",
    )

    # --- Meta tracking ---

    op.create_table(
        "intelligence_passes",
        sa.Column("pidn", sa.Text, nullable=False),
        sa.Column("pass_number", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("input_hash", sa.Text),
        sa.Column("error_message", sa.Text),
        sa.PrimaryKeyConstraint("pidn", "pass_number"),
        schema="meta",
    )


def downgrade() -> None:
    op.drop_table("intelligence_passes", schema="meta")
    op.drop_table("entity_graph", schema="public")
    op.drop_table("county_narratives", schema="public")
    op.drop_table("parcel_briefs", schema="public")
    op.drop_table("evidence", schema="public")
    op.drop_index("idx_extractions_parcel", table_name="proceeding_extractions", schema="staging")
    op.drop_index("idx_extractions_applicant", table_name="proceeding_extractions", schema="staging")
    op.drop_table("proceeding_extractions", schema="staging")
    op.drop_index("idx_proceedings_body_date", table_name="public_proceedings", schema="staging")
    op.drop_table("public_proceedings", schema="staging")
    op.drop_index("idx_corporate_entities_agent", table_name="corporate_entities", schema="staging")
    op.drop_index("idx_corporate_entities_current", table_name="corporate_entities", schema="staging")
    op.drop_table("corporate_entities", schema="staging")
```

- [ ] **Step 2: Start Docker Postgres and apply migration**

```bash
cd pipelines && docker compose up -d postgres-test
```

Wait for postgres to be ready, then:

```bash
cd pipelines && source .venv/bin/activate
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq"
alembic upgrade head
```

Expected: Migration 012 applied successfully, no errors.

- [ ] **Step 3: Verify tables exist**

```bash
cd pipelines && source .venv/bin/activate
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq"
python3 -c "
import psycopg2
conn = psycopg2.connect('postgresql://dagster_admin:localtest@localhost:5433/countyiq')
cur = conn.cursor()
tables = [
    ('staging', 'corporate_entities'),
    ('staging', 'public_proceedings'),
    ('staging', 'proceeding_extractions'),
    ('public', 'evidence'),
    ('public', 'parcel_briefs'),
    ('public', 'county_narratives'),
    ('public', 'entity_graph'),
    ('meta', 'intelligence_passes'),
]
for schema, table in tables:
    cur.execute(
        'SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s AND table_name = %s',
        (schema, table),
    )
    count = cur.fetchone()[0]
    status = 'OK' if count == 1 else 'MISSING'
    print(f'{status}: {schema}.{table}')
conn.close()
"
```

Expected: All 8 tables show `OK`.

- [ ] **Step 4: Commit**

```bash
git add pipelines/alembic/versions/012_intelligence_platform.py
git commit -m "feat: add intelligence platform tables (staging, public, meta)"
```

---

### Task 2: Add source_url to Existing Staging Tables

**Files:**
- Create: `pipelines/alembic/versions/013_source_url_provenance.py`

- [ ] **Step 1: Write the migration**

```python
"""Add source_url column to existing staging tables for evidence provenance

Revision ID: 013
Revises: 012
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None

STAGING_TABLES = [
    "parcels",
    "structures",
    "zoning",
    "roads",
    "municipalities",
    "planning_subdivisions",
    "ecodev_candidates",
    "growth_areas",
    "future_landuse",
    "conservation_easements",
    "ag_security",
    "cdbg_housing",
    "flood_zones",
    "tax_claims",
    "plcb_licenses",
    "address_points",
    "penndot_roads",
    "penndot_projects",
]


def upgrade() -> None:
    for table in STAGING_TABLES:
        op.add_column(
            table,
            sa.Column("source_url", sa.Text),
            schema="staging",
        )


def downgrade() -> None:
    for table in STAGING_TABLES:
        op.drop_column(table, "source_url", schema="staging")
```

- [ ] **Step 2: Apply migration**

```bash
cd pipelines && source .venv/bin/activate
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq"
alembic upgrade head
```

Expected: Migration 013 applied. All staging tables now have `source_url` column.

- [ ] **Step 3: Verify column exists on a sample of tables**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "
import psycopg2
conn = psycopg2.connect('postgresql://dagster_admin:localtest@localhost:5433/countyiq')
cur = conn.cursor()
for table in ['parcels', 'tax_claims', 'plcb_licenses', 'planning_subdivisions']:
    cur.execute('''
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'staging' AND table_name = %s AND column_name = 'source_url'
    ''', (table,))
    found = cur.fetchone()
    print(f\"{'OK' if found else 'MISSING'}: staging.{table}.source_url\")
conn.close()
"
```

Expected: All show `OK`.

- [ ] **Step 4: Commit**

```bash
git add pipelines/alembic/versions/013_source_url_provenance.py
git commit -m "feat: add source_url column to all existing staging tables"
```

---

### Task 3: County Config — PA DOS + Municipality Websites

**Files:**
- Modify: `pipelines/countyiq/lib/county_config.py`

- [ ] **Step 1: Read current county_config.py**

Read `pipelines/countyiq/lib/county_config.py` to see the current `CountyConfig` fields and `COUNTY_CONFIGS` dict.

- [ ] **Step 2: Add PA DOS fields to CountyConfig**

Add these fields to the `CountyConfig` dataclass after the existing source URL fields:

```python
    # PA DOS Corporate Entities
    pa_dos_search_url: str = ""
    pa_dos_min_records: int = 100

    # Public Proceedings
    municipality_websites: tuple = ()  # Tuple of (name, minutes_url, proceeding_type) tuples
```

- [ ] **Step 3: Add PA DOS + municipality websites to York County config**

In the `COUNTY_CONFIGS` dict under the `"york"` entry, add:

```python
        pa_dos_search_url="https://www.corporations.pa.gov/Search/CorpSearch",
        pa_dos_min_records=100,
        municipality_websites=(
            # Start with all 72 municipalities
            # Format: (body_name, minutes_url, proceeding_type)
            # This will be populated by researching each municipality's website
            # For now, seed with known URLs — expand as sites are discovered
        ),
```

Note: The full `municipality_websites` tuple will be populated by a research pass through all 72 municipality websites. This is a data-gathering task, not a code task. Seed with a few known URLs to prove the pipeline works, then expand.

- [ ] **Step 4: Commit**

```bash
git add pipelines/countyiq/lib/county_config.py
git commit -m "feat: add PA DOS and municipality websites to county config"
```

---

### Task 4: PA DOS Corporate Entity Parser + Tests

**Files:**
- Create: `pipelines/countyiq/lib/parsers/pa_dos_entities.py`
- Create: `pipelines/tests/fixtures/pa_dos_sample.html`
- Create: `pipelines/tests/test_pa_dos_parser.py`

- [ ] **Step 1: Create test fixture**

Use Playwright to visit `https://www.corporations.pa.gov/Search/CorpSearch`, search for a known LLC (e.g., a common York County business entity from `staging.parcels`), and save the results HTML to `pipelines/tests/fixtures/pa_dos_sample.html`.

This is a manual research step — the fixture captures the actual HTML structure that the parser will need to handle.

- [ ] **Step 2: Write failing parser tests**

```python
# pipelines/tests/test_pa_dos_parser.py
import os
import pytest
from countyiq.lib.parsers.pa_dos_entities import parse_entity_search_results


@pytest.fixture
def sample_html():
    fixture_path = os.path.join(
        os.path.dirname(__file__), "fixtures", "pa_dos_sample.html"
    )
    with open(fixture_path) as f:
        return f.read()


def test_parse_returns_list(sample_html):
    results = parse_entity_search_results(sample_html)
    assert isinstance(results, list)
    assert len(results) > 0


def test_parse_entity_has_required_fields(sample_html):
    results = parse_entity_search_results(sample_html)
    entity = results[0]
    assert "entity_name" in entity
    assert "entity_number" in entity
    assert "entity_type" in entity
    assert "status" in entity
    assert "source_url" in entity


def test_parse_entity_has_agent_fields(sample_html):
    results = parse_entity_search_results(sample_html)
    entity = results[0]
    assert "registered_agent_name" in entity
    assert "registered_agent_address" in entity


def test_parse_entity_has_officers(sample_html):
    results = parse_entity_search_results(sample_html)
    entity = results[0]
    assert "officers" in entity
    assert isinstance(entity["officers"], list)


def test_parse_source_url_points_to_pa_dos(sample_html):
    results = parse_entity_search_results(sample_html)
    entity = results[0]
    assert "corporations.pa.gov" in entity["source_url"]
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_pa_dos_parser.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'countyiq.lib.parsers.pa_dos_entities'`

- [ ] **Step 4: Write parser implementation**

```python
# pipelines/countyiq/lib/parsers/pa_dos_entities.py
"""Parser for PA Department of State corporate entity search results."""
from bs4 import BeautifulSoup


def parse_entity_search_results(html: str) -> list[dict]:
    """Parse PA DOS search results HTML into entity records.

    Args:
        html: Raw HTML from corporations.pa.gov search results or detail page.

    Returns:
        List of entity dicts with keys: entity_name, entity_number, entity_type,
        status, formation_date, registered_agent_name, registered_agent_address,
        office_address, officers, source_url.
    """
    soup = BeautifulSoup(html, "lxml")
    entities = []

    # NOTE: The actual selectors below must be adapted to the real PA DOS HTML
    # structure after examining the fixture. This is a starting implementation
    # that will be refined against the fixture in Step 5.

    for row in soup.select("table tr[data-entity]"):
        entity = {
            "entity_name": _text(row, ".entity-name"),
            "entity_number": _text(row, ".entity-number"),
            "entity_type": _text(row, ".entity-type"),
            "status": _text(row, ".entity-status"),
            "formation_date": _text(row, ".formation-date") or None,
            "registered_agent_name": _text(row, ".agent-name"),
            "registered_agent_address": _text(row, ".agent-address"),
            "office_address": _text(row, ".office-address"),
            "officers": _parse_officers(row),
            "source_url": _build_source_url(row),
        }
        entities.append(entity)

    return entities


def _text(element, selector: str) -> str:
    """Extract text from first matching child element."""
    el = element.select_one(selector)
    return el.get_text(strip=True) if el else ""


def _parse_officers(row) -> list[dict]:
    """Extract officer list from entity detail."""
    officers = []
    for officer_el in row.select(".officer"):
        officers.append({
            "name": _text(officer_el, ".officer-name"),
            "title": _text(officer_el, ".officer-title"),
        })
    return officers


def _build_source_url(row) -> str:
    """Build the direct URL to this entity on PA DOS."""
    entity_number = _text(row, ".entity-number")
    return f"https://www.corporations.pa.gov/Search/CorpSearch?entityNumber={entity_number}"
```

**IMPORTANT:** The CSS selectors above are placeholders. After creating the fixture in Step 1, the selectors MUST be updated to match the actual HTML structure of the PA DOS website. Run the tests, inspect failures, and fix selectors until all tests pass.

- [ ] **Step 5: Adapt selectors to actual fixture HTML and run tests**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_pa_dos_parser.py -v
```

Iterate: read the fixture HTML, update selectors in the parser, re-run tests until all pass.

Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add pipelines/countyiq/lib/parsers/pa_dos_entities.py pipelines/tests/test_pa_dos_parser.py pipelines/tests/fixtures/pa_dos_sample.html
git commit -m "feat: PA DOS corporate entity parser with tests"
```

---

### Task 5: PA DOS Corporate Entity Dagster Asset

**Files:**
- Create: `pipelines/countyiq/assets/scrapers/pa_dos_entities.py`

- [ ] **Step 1: Write the asset**

```python
# pipelines/countyiq/assets/scrapers/pa_dos_entities.py
"""PA Department of State corporate entity lookup.

Queries PA DOS for every LLC/Corp/LP name found in staging.parcels.owner_full,
parses registration details (agent, officers, office address), and upserts
to staging.corporate_entities via SCD Type 2.
"""
from dagster import asset, AssetExecutionContext, MaterializeResult, MetadataValue

from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.pa_dos_entities import parse_entity_search_results
from countyiq.lib.scd import scd2_upsert
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

import requests
import time
import json
import re

# Patterns that indicate a business entity (not a person)
ENTITY_PATTERNS = re.compile(
    r"\b(LLC|L\.L\.C|INC|CORP|LP|L\.P|LTD|TRUST|PARTNERS|ASSOCIATES|"
    r"HOLDINGS|ENTERPRISES|PROPERTIES|GROUP|VENTURES|CAPITAL|INVESTMENTS)\b",
    re.IGNORECASE,
)


@asset(
    group_name="scrapers",
    description="PA DOS corporate entity lookup for business owners in York County parcels",
    kinds={"postgres", "scraper"},
)
def pa_dos_entities(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    county = get_county_config()
    cur = database.cursor()

    # 1. Extract unique business entity names from parcels
    cur.execute("""
        SELECT DISTINCT owner_full
        FROM staging.parcels
        WHERE valid_to IS NULL
          AND owner_full IS NOT NULL
          AND owner_full != ''
    """)
    all_owners = [row[0] for row in cur.fetchall()]
    business_names = [name for name in all_owners if ENTITY_PATTERNS.search(name)]
    context.log.info(f"Found {len(business_names)} unique business entity names to look up")

    # 2. Check which entities we already have (skip if recently verified)
    cur.execute("""
        SELECT entity_name FROM staging.corporate_entities
        WHERE valid_to IS NULL
          AND valid_from > NOW() - INTERVAL '7 days'
    """)
    recently_verified = {row[0] for row in cur.fetchall()}
    to_lookup = [n for n in business_names if n not in recently_verified]
    context.log.info(f"Skipping {len(recently_verified)} recently verified, looking up {len(to_lookup)}")

    # 3. Query PA DOS for each entity
    all_records = []
    errors = 0
    for i, name in enumerate(to_lookup):
        try:
            html = _search_pa_dos(county.pa_dos_search_url, name)
            records = parse_entity_search_results(html)
            all_records.extend(records)

            if (i + 1) % 50 == 0:
                context.log.info(f"Processed {i + 1}/{len(to_lookup)} lookups, {len(all_records)} records found")

            # Throttle to avoid overwhelming PA DOS
            time.sleep(1.0)
        except Exception as e:
            context.log.warning(f"Failed to look up '{name}': {e}")
            errors += 1
            if errors > 50:
                context.log.error("Too many errors, stopping early")
                break
            time.sleep(2.0)

    context.log.info(f"Total records from PA DOS: {len(all_records)}")

    if len(all_records) == 0:
        context.log.warning("No records retrieved from PA DOS")
        return MaterializeResult(
            metadata={"record_count": MetadataValue.int(0), "errors": MetadataValue.int(errors)}
        )

    # 4. Archive raw to S3
    s3.archive(
        f"{county.s3_prefix}/scrapers/pa_dos",
        json.dumps(all_records, default=str),
        filename="entities.json",
    )

    # 5. SCD2 upsert
    stats = scd2_upsert(
        cursor=cur,
        schema="staging",
        table="corporate_entities",
        records=all_records,
        key_columns=["entity_name"],
        value_columns=[
            "entity_number", "entity_type", "status", "formation_date",
            "registered_agent_name", "registered_agent_address",
            "office_address", "officers", "source_url",
        ],
    )
    cur.connection.commit()

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(len(all_records)),
            "inserted": MetadataValue.int(stats["inserted"]),
            "expired": MetadataValue.int(stats["expired"]),
            "unchanged": MetadataValue.int(stats["unchanged"]),
            "errors": MetadataValue.int(errors),
            "lookups_attempted": MetadataValue.int(len(to_lookup)),
        }
    )


def _search_pa_dos(base_url: str, entity_name: str) -> str:
    """Query PA DOS search and return HTML response."""
    resp = requests.get(
        base_url,
        params={"searchTerm": entity_name},
        timeout=30,
        headers={"User-Agent": "CountyIQ/1.0 (civic intelligence platform)"},
    )
    resp.raise_for_status()
    return resp.text
```

**NOTE:** The `_search_pa_dos` function assumes a simple GET request. PA DOS may require POST, session cookies, or CAPTCHA handling. If so, this function should be upgraded to use Playwright. Verify against the live site during integration testing.

- [ ] **Step 2: Verify asset loads in Dagster**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "
from countyiq.assets.scrapers.pa_dos_entities import pa_dos_entities
print(f'Asset loaded: {pa_dos_entities.key}')
print(f'Group: {pa_dos_entities.group_names_by_key}')
"
```

Expected: Asset loads without import errors.

- [ ] **Step 3: Commit**

```bash
git add pipelines/countyiq/assets/scrapers/pa_dos_entities.py
git commit -m "feat: PA DOS corporate entity lookup Dagster asset"
```

---

### Task 6: Public Proceedings Scraper + Tests

**Files:**
- Create: `pipelines/countyiq/lib/parsers/public_proceedings.py`
- Create: `pipelines/tests/fixtures/proceedings_sample.html`
- Create: `pipelines/tests/test_proceedings_parser.py`

- [ ] **Step 1: Research and create fixture**

Use Playwright to visit 2-3 municipality websites that publish meeting minutes (e.g., West Manchester Township, Springettsbury Township, York City). Save a sample minutes page HTML to `pipelines/tests/fixtures/proceedings_sample.html`.

Document the URL patterns observed — some municipalities use a CMS (e.g., WordPress, Civic Plus), some have static pages with PDF links.

- [ ] **Step 2: Write failing parser tests**

```python
# pipelines/tests/test_proceedings_parser.py
import os
import pytest
from countyiq.lib.parsers.public_proceedings import (
    extract_pdf_links,
    parse_meeting_date_from_filename,
)


@pytest.fixture
def sample_html():
    fixture_path = os.path.join(
        os.path.dirname(__file__), "fixtures", "proceedings_sample.html"
    )
    with open(fixture_path) as f:
        return f.read()


def test_extract_pdf_links_returns_list(sample_html):
    links = extract_pdf_links(sample_html, base_url="https://example.com/minutes")
    assert isinstance(links, list)


def test_extract_pdf_links_are_absolute_urls(sample_html):
    links = extract_pdf_links(sample_html, base_url="https://example.com/minutes")
    for link in links:
        assert link["url"].startswith("http"), f"Relative URL found: {link['url']}"


def test_extract_pdf_links_have_filename(sample_html):
    links = extract_pdf_links(sample_html, base_url="https://example.com/minutes")
    for link in links:
        assert "filename" in link
        assert link["filename"].endswith(".pdf") or link["filename"].endswith(".PDF")


def test_parse_meeting_date_from_typical_filenames():
    assert parse_meeting_date_from_filename("Minutes-2025-11-14.pdf") == "2025-11-14"
    assert parse_meeting_date_from_filename("ZHB_Minutes_March_2025.pdf") == "2025-03-01"
    assert parse_meeting_date_from_filename("PC_01-15-2026.pdf") == "2026-01-15"


def test_parse_meeting_date_returns_none_for_unparseable():
    assert parse_meeting_date_from_filename("agenda.pdf") is None
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_proceedings_parser.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 4: Write parser implementation**

```python
# pipelines/countyiq/lib/parsers/public_proceedings.py
"""Parser for municipal meeting minutes pages.

Extracts PDF links from municipality websites and parses
meeting dates from filenames/link text.
"""
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# Common date patterns in municipal PDF filenames
DATE_PATTERNS = [
    # 2025-11-14, 2025_11_14
    re.compile(r"(\d{4})[-_](\d{2})[-_](\d{2})"),
    # 01-15-2026, 01_15_2026
    re.compile(r"(\d{2})[-_](\d{2})[-_](\d{4})"),
    # March 2025, November 2025
    re.compile(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s*(\d{4})",
        re.IGNORECASE,
    ),
]

MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}


def extract_pdf_links(html: str, base_url: str) -> list[dict]:
    """Extract PDF download links from a municipality minutes page.

    Args:
        html: Raw HTML of the minutes listing page.
        base_url: Base URL for resolving relative links.

    Returns:
        List of dicts with keys: url, filename, link_text.
    """
    soup = BeautifulSoup(html, "lxml")
    links = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if not href.lower().endswith(".pdf"):
            continue

        absolute_url = urljoin(base_url, href)
        filename = href.split("/")[-1].split("?")[0]
        link_text = a_tag.get_text(strip=True)

        links.append({
            "url": absolute_url,
            "filename": filename,
            "link_text": link_text,
        })

    return links


def parse_meeting_date_from_filename(filename: str) -> str | None:
    """Extract a meeting date from a PDF filename.

    Returns ISO date string (YYYY-MM-DD) or None if unparseable.
    """
    # Try YYYY-MM-DD or YYYY_MM_DD
    m = DATE_PATTERNS[0].search(filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # Try MM-DD-YYYY or MM_DD_YYYY
    m = DATE_PATTERNS[1].search(filename)
    if m:
        return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"

    # Try "Month YYYY"
    m = DATE_PATTERNS[2].search(filename)
    if m:
        month_num = MONTH_MAP.get(m.group(1).lower())
        if month_num:
            return f"{m.group(2)}-{month_num}-01"

    return None
```

- [ ] **Step 5: Run tests**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_proceedings_parser.py -v
```

Expected: All tests PASS (adjust PDF link extraction against actual fixture HTML if needed).

- [ ] **Step 6: Commit**

```bash
git add pipelines/countyiq/lib/parsers/public_proceedings.py pipelines/tests/test_proceedings_parser.py pipelines/tests/fixtures/proceedings_sample.html
git commit -m "feat: public proceedings PDF link parser with tests"
```

---

### Task 7: Public Proceedings Dagster Asset

**Files:**
- Create: `pipelines/countyiq/assets/scrapers/public_proceedings.py`

- [ ] **Step 1: Write the asset**

```python
# pipelines/countyiq/assets/scrapers/public_proceedings.py
"""Public proceedings scraper for all York County municipalities.

Downloads meeting minute PDFs from municipality websites and stores
metadata in staging.public_proceedings. PDF files are archived to R2.
"""
from dagster import asset, AssetExecutionContext, MaterializeResult, MetadataValue

from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.public_proceedings import extract_pdf_links, parse_meeting_date_from_filename
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

import requests
import time
import json

# Map common labels to proceeding_type
PROCEEDING_TYPE_PATTERNS = {
    "zhb": "zoning_hearing",
    "zoning hearing": "zoning_hearing",
    "zoning board": "zoning_hearing",
    "planning commission": "planning_commission",
    "planning comm": "planning_commission",
    "supervisors": "supervisors",
    "board of supervisors": "supervisors",
    "council": "council",
    "borough council": "council",
}


@asset(
    group_name="scrapers",
    description="Download meeting minute PDFs from all York County municipality websites",
    kinds={"postgres", "scraper"},
)
def public_proceedings_scrape(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    county = get_county_config()
    cur = database.cursor()

    total_new = 0
    total_skipped = 0
    errors = 0

    for body_name, minutes_url, proceeding_type in county.municipality_websites:
        context.log.info(f"Scraping {body_name}: {minutes_url}")

        try:
            # Fetch the minutes listing page
            resp = requests.get(minutes_url, timeout=30)
            resp.raise_for_status()
            pdf_links = extract_pdf_links(resp.text, base_url=minutes_url)

            context.log.info(f"  Found {len(pdf_links)} PDF links for {body_name}")

            for link in pdf_links:
                # Check if we already have this document
                cur.execute("""
                    SELECT id FROM staging.public_proceedings
                    WHERE body_name = %(body)s AND document_url = %(url)s AND valid_to IS NULL
                """, {"body": body_name, "url": link["url"]})

                if cur.fetchone():
                    total_skipped += 1
                    continue

                # Parse meeting date from filename or link text
                meeting_date = parse_meeting_date_from_filename(link["filename"])
                if meeting_date is None:
                    meeting_date = parse_meeting_date_from_filename(link["link_text"])
                if meeting_date is None:
                    context.log.warning(f"  Cannot parse date from: {link['filename']}")
                    continue

                # Download PDF
                pdf_resp = requests.get(link["url"], timeout=60)
                pdf_resp.raise_for_status()

                # Archive to R2
                safe_body = body_name.lower().replace(" ", "_")
                s3.archive_file_bytes(
                    f"{county.s3_prefix}/proceedings/{safe_body}/{meeting_date}",
                    pdf_resp.content,
                    filename=link["filename"],
                )

                # Insert into staging
                cur.execute("""
                    INSERT INTO staging.public_proceedings
                        (body_name, meeting_date, proceeding_type, source_url, document_url)
                    VALUES (%(body)s, %(date)s, %(type)s, %(source)s, %(doc)s)
                """, {
                    "body": body_name,
                    "date": meeting_date,
                    "type": proceeding_type,
                    "source": minutes_url,
                    "doc": link["url"],
                })
                total_new += 1
                time.sleep(0.5)

        except Exception as e:
            context.log.warning(f"  Error scraping {body_name}: {e}")
            errors += 1

    cur.connection.commit()

    context.log.info(
        f"Proceedings scrape complete: {total_new} new, {total_skipped} skipped, {errors} errors"
    )

    return MaterializeResult(
        metadata={
            "new_documents": MetadataValue.int(total_new),
            "skipped_existing": MetadataValue.int(total_skipped),
            "errors": MetadataValue.int(errors),
            "municipalities_attempted": MetadataValue.int(len(county.municipality_websites)),
        }
    )
```

**NOTE:** The `s3.archive_file_bytes` method may not exist on `S3StorageResource`. If not, add a simple method that writes bytes to S3, or use `s3.archive()` with the raw bytes. Check `pipelines/countyiq/resources/storage.py` during implementation.

- [ ] **Step 2: Verify asset loads**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "
from countyiq.assets.scrapers.public_proceedings import public_proceedings_scrape
print(f'Asset loaded: {public_proceedings_scrape.key}')
"
```

Expected: No import errors.

- [ ] **Step 3: Commit**

```bash
git add pipelines/countyiq/assets/scrapers/public_proceedings.py
git commit -m "feat: public proceedings scraper Dagster asset"
```

---

### Task 8: Pass 0 — Multimodal Document Extraction

**Files:**
- Create: `pipelines/countyiq/lib/llm_harness.py`
- Create: `pipelines/countyiq/assets/enrichment/proceeding_extraction.py`
- Create: `pipelines/tests/fixtures/proceedings_page_sample.png`
- Create: `pipelines/tests/test_proceeding_extraction.py`

- [ ] **Step 1: Install llama-cpp-python and pdf2image**

```bash
cd pipelines && source .venv/bin/activate
uv pip install llama-cpp-python pdf2image Pillow
```

Also ensure `poppler-utils` is installed on the system for pdf2image:

```bash
sudo apt-get install -y poppler-utils
```

- [ ] **Step 2: Write the LLM harness base module**

This is the shared scaffolding all passes will use. Phase 1 implements just the core; Passes 1-4 in Phase 2 extend it.

```python
# pipelines/countyiq/lib/llm_harness.py
"""LLM harness for CountyIQ intelligence pipeline.

Provides the shared infrastructure for all reasoning passes:
prompt template rendering, structured output parsing, retry logic,
and llama.cpp model management.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path

from llama_cpp import Llama
from llama_cpp.llama_chat_format import MoondreamChatHandler


@dataclass(frozen=True)
class HarnessConfig:
    """Configuration for an LLM harness invocation."""
    model_path: str
    n_ctx: int = 4096
    n_gpu_layers: int = -1  # -1 = all layers on GPU
    temperature: float = 0.1
    max_tokens: int = 2048
    chat_handler: object = None  # For multimodal models


class HarnessResult:
    """Result from an LLM harness invocation."""
    def __init__(self, raw_output: str, parsed: dict | None, success: bool, error: str | None = None):
        self.raw_output = raw_output
        self.parsed = parsed
        self.success = success
        self.error = error


_model_cache: dict[str, Llama] = {}


def get_model(config: HarnessConfig) -> Llama:
    """Get or create a cached Llama model instance."""
    if config.model_path not in _model_cache:
        kwargs = {
            "model_path": config.model_path,
            "n_ctx": config.n_ctx,
            "n_gpu_layers": config.n_gpu_layers,
            "verbose": False,
        }
        if config.chat_handler:
            kwargs["chat_handler"] = config.chat_handler
        _model_cache[config.model_path] = Llama(**kwargs)
    return _model_cache[config.model_path]


def invoke(config: HarnessConfig, prompt: str, image_path: str | None = None) -> HarnessResult:
    """Invoke the LLM with a prompt and optional image.

    Args:
        config: Model and generation parameters.
        prompt: The full prompt text.
        image_path: Optional path to an image file (for multimodal models).

    Returns:
        HarnessResult with parsed JSON output if successful.
    """
    model = get_model(config)

    messages = []
    if image_path:
        import base64
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                {"type": "text", "text": prompt},
            ],
        })
    else:
        messages.append({"role": "user", "content": prompt})

    try:
        response = model.create_chat_completion(
            messages=messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            response_format={"type": "json_object"},
        )
        raw_output = response["choices"][0]["message"]["content"]

        # Parse JSON
        parsed = json.loads(raw_output)
        return HarnessResult(raw_output=raw_output, parsed=parsed, success=True)

    except json.JSONDecodeError as e:
        return HarnessResult(raw_output=raw_output, parsed=None, success=False, error=f"JSON parse error: {e}")
    except Exception as e:
        return HarnessResult(raw_output="", parsed=None, success=False, error=str(e))


def invoke_with_retry(config: HarnessConfig, prompt: str, image_path: str | None = None, retries: int = 1) -> HarnessResult:
    """Invoke with retry on failure."""
    result = invoke(config, prompt, image_path)
    if result.success:
        return result

    for attempt in range(retries):
        result = invoke(config, prompt, image_path)
        if result.success:
            return result

    return result
```

- [ ] **Step 3: Write the Pass 0 extraction prompt template**

```python
# pipelines/countyiq/lib/pass0_templates.py
"""Prompt templates for Pass 0: Document Intelligence.

Extracts structured records from municipal meeting minute page images.
"""

EXTRACTION_PROMPT = """You are reading a municipal meeting document from {body_name}, York County, PA.
This is page {page_num} of {total_pages} from a {proceeding_type} meeting on {meeting_date}.

Extract ALL of the following if present on this page:
- Rezoning applications (applicant, parcel/address, current zoning, proposed zoning, decision)
- Variance requests (applicant, parcel/address, variance type, decision)
- Conditional use permits (applicant, parcel/address, proposed use, decision)
- Subdivision/land development reviews (applicant, plan name, parcel/address, proposed lots/units, decision)
- Development proposals discussed (developer/applicant name, project description, location)
- Any entity names associated with property actions

For each extracted record, include:
- The exact text from the document that supports your extraction
- Your confidence level (high/medium/low)

If this page contains no relevant records, return {{"extractions": []}}.

OUTPUT FORMAT:
{{
  "extractions": [
    {{
      "extraction_type": "rezoning_application|variance_request|conditional_use|subdivision_review|development_proposal",
      "applicant_name": "name or null",
      "parcel_reference": "PIDN or address or null",
      "current_zoning": "zone code or null",
      "proposed_zoning": "zone code or null",
      "decision": "approved|denied|tabled|continued|null",
      "conditions": ["list of conditions if any"],
      "supporting_text": "exact quote from the document",
      "confidence": "high|medium|low"
    }}
  ]
}}"""
```

- [ ] **Step 4: Write failing extraction tests**

```python
# pipelines/tests/test_proceeding_extraction.py
import os
import json
import pytest
from unittest.mock import patch, MagicMock
from countyiq.lib.pass0_templates import EXTRACTION_PROMPT
from countyiq.lib.llm_harness import HarnessResult


def test_extraction_prompt_formats_correctly():
    prompt = EXTRACTION_PROMPT.format(
        body_name="West Manchester Township",
        page_num=1,
        total_pages=5,
        proceeding_type="planning_commission",
        meeting_date="2025-11-14",
    )
    assert "West Manchester Township" in prompt
    assert "page 1 of 5" in prompt
    assert "planning_commission" in prompt
    assert "2025-11-14" in prompt


def test_extraction_prompt_has_all_extraction_types():
    prompt = EXTRACTION_PROMPT.format(
        body_name="X", page_num=1, total_pages=1,
        proceeding_type="X", meeting_date="X",
    )
    assert "rezoning_application" in prompt
    assert "variance_request" in prompt
    assert "conditional_use" in prompt
    assert "subdivision_review" in prompt
    assert "development_proposal" in prompt


def test_harness_result_success():
    result = HarnessResult(
        raw_output='{"extractions": []}',
        parsed={"extractions": []},
        success=True,
    )
    assert result.success
    assert result.parsed == {"extractions": []}


def test_harness_result_failure():
    result = HarnessResult(
        raw_output="invalid json",
        parsed=None,
        success=False,
        error="JSON parse error",
    )
    assert not result.success
    assert result.error is not None
```

- [ ] **Step 5: Run tests**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_proceeding_extraction.py -v
```

Expected: All tests PASS (these test the templates and result types, not the actual LLM invocation).

- [ ] **Step 6: Write the Pass 0 Dagster asset**

```python
# pipelines/countyiq/assets/enrichment/proceeding_extraction.py
"""Pass 0: Document Intelligence — extract structured records from meeting minutes.

Reads PDF pages as images, sends to multimodal LLM, extracts
rezoning applications, variance requests, subdivisions, etc.
Stores results in staging.proceeding_extractions.
"""
from dagster import asset, AssetExecutionContext, MaterializeResult, MetadataValue
from countyiq.lib.llm_harness import HarnessConfig, invoke_with_retry
from countyiq.lib.pass0_templates import EXTRACTION_PROMPT
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

import os
import tempfile

# Model path from environment — allows different models in dev vs prod
MODEL_PATH = os.environ.get("COUNTYIQ_MULTIMODAL_MODEL", "")


@asset(
    group_name="enrichment",
    deps=["public_proceedings_scrape"],
    description="Extract structured records from meeting minute PDFs using multimodal LLM",
    kinds={"postgres", "llm"},
)
def proceeding_extraction(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    if not MODEL_PATH:
        context.log.error("COUNTYIQ_MULTIMODAL_MODEL not set — skipping Pass 0")
        return MaterializeResult(metadata={"status": MetadataValue.text("skipped — no model configured")})

    config = HarnessConfig(
        model_path=MODEL_PATH,
        n_ctx=4096,
        n_gpu_layers=int(os.environ.get("COUNTYIQ_GPU_LAYERS", "-1")),
        temperature=0.1,
        max_tokens=2048,
    )

    cur = database.cursor()

    # Find proceedings without extractions
    cur.execute("""
        SELECT pp.id, pp.body_name, pp.meeting_date, pp.proceeding_type,
               pp.document_url
        FROM staging.public_proceedings pp
        LEFT JOIN staging.proceeding_extractions pe ON pp.id = pe.proceeding_id
        WHERE pp.valid_to IS NULL
          AND pe.id IS NULL
        ORDER BY pp.meeting_date DESC
    """)
    unprocessed = cur.fetchall()
    context.log.info(f"Found {len(unprocessed)} unprocessed proceedings")

    total_extractions = 0
    total_pages = 0
    errors = 0

    for proc_id, body_name, meeting_date, proceeding_type, document_url in unprocessed:
        try:
            # Download PDF from R2 (or original URL) to temp file
            with tempfile.TemporaryDirectory() as tmpdir:
                pdf_path = os.path.join(tmpdir, "document.pdf")
                _download_pdf(document_url, pdf_path, s3)

                # Convert PDF pages to images
                from pdf2image import convert_from_path
                images = convert_from_path(pdf_path, dpi=200)

                for page_num, img in enumerate(images, 1):
                    total_pages += 1
                    img_path = os.path.join(tmpdir, f"page_{page_num}.png")
                    img.save(img_path, "PNG")

                    prompt = EXTRACTION_PROMPT.format(
                        body_name=body_name,
                        page_num=page_num,
                        total_pages=len(images),
                        proceeding_type=proceeding_type,
                        meeting_date=meeting_date,
                    )

                    result = invoke_with_retry(config, prompt, image_path=img_path, retries=1)

                    if not result.success:
                        context.log.warning(
                            f"  Pass 0 failed for {body_name} {meeting_date} p{page_num}: {result.error}"
                        )
                        errors += 1
                        continue

                    extractions = result.parsed.get("extractions", [])

                    for ext in extractions:
                        cur.execute("""
                            INSERT INTO staging.proceeding_extractions
                                (proceeding_id, extraction_type, applicant_name,
                                 parcel_reference, current_zoning, proposed_zoning,
                                 decision, conditions, supporting_text,
                                 extraction_confidence, model_used, page_number)
                            VALUES (%(proc_id)s, %(type)s, %(applicant)s,
                                    %(parcel)s, %(cur_zone)s, %(prop_zone)s,
                                    %(decision)s, %(conditions)s, %(text)s,
                                    %(confidence)s, %(model)s, %(page)s)
                        """, {
                            "proc_id": proc_id,
                            "type": ext.get("extraction_type", "unknown"),
                            "applicant": ext.get("applicant_name"),
                            "parcel": ext.get("parcel_reference"),
                            "cur_zone": ext.get("current_zoning"),
                            "prop_zone": ext.get("proposed_zoning"),
                            "decision": ext.get("decision"),
                            "conditions": _to_json(ext.get("conditions")),
                            "text": ext.get("supporting_text"),
                            "confidence": _confidence_to_float(ext.get("confidence", "low")),
                            "model": os.path.basename(MODEL_PATH),
                            "page": page_num,
                        })
                        total_extractions += 1

            cur.connection.commit()

        except Exception as e:
            context.log.warning(f"  Error processing {body_name} {meeting_date}: {e}")
            errors += 1

    context.log.info(
        f"Pass 0 complete: {total_extractions} extractions from {total_pages} pages, {errors} errors"
    )

    return MaterializeResult(
        metadata={
            "extractions": MetadataValue.int(total_extractions),
            "pages_processed": MetadataValue.int(total_pages),
            "proceedings_processed": MetadataValue.int(len(unprocessed)),
            "errors": MetadataValue.int(errors),
        }
    )


def _download_pdf(url: str, dest_path: str, s3: S3StorageResource):
    """Download a PDF from URL or R2 to local path."""
    import requests
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(resp.content)


def _confidence_to_float(confidence: str) -> float:
    return {"high": 0.9, "medium": 0.7, "low": 0.4}.get(confidence.lower(), 0.4)


def _to_json(value):
    """Convert a value to JSON string for JSONB column, or None."""
    if value is None:
        return None
    import json
    return json.dumps(value)
```

- [ ] **Step 7: Verify asset loads**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "
from countyiq.assets.enrichment.proceeding_extraction import proceeding_extraction
print(f'Asset loaded: {proceeding_extraction.key}')
"
```

Expected: No import errors.

- [ ] **Step 8: Commit**

```bash
git add pipelines/countyiq/lib/llm_harness.py pipelines/countyiq/lib/pass0_templates.py pipelines/countyiq/assets/enrichment/proceeding_extraction.py pipelines/tests/test_proceeding_extraction.py
git commit -m "feat: Pass 0 multimodal document extraction with LLM harness"
```

---

### Task 9: Dagster Job Definitions for New Assets

**Files:**
- Modify: `pipelines/countyiq/jobs/__init__.py`

- [ ] **Step 1: Read current jobs file**

Read `pipelines/countyiq/jobs/__init__.py` to see existing job definitions.

- [ ] **Step 2: Add new job definitions**

Add these jobs after the existing definitions:

```python
pa_dos_refresh = define_asset_job(
    name="pa_dos_refresh",
    selection=AssetSelection.assets("pa_dos_entities"),
    description="Refresh PA DOS corporate entity lookups",
)

proceedings_refresh = define_asset_job(
    name="proceedings_refresh",
    selection=AssetSelection.assets("public_proceedings_scrape"),
    description="Scrape meeting minutes from all York County municipalities",
)

proceedings_extraction_refresh = define_asset_job(
    name="proceedings_extraction_refresh",
    selection=AssetSelection.assets("proceeding_extraction"),
    description="Run Pass 0: extract structured records from meeting minute PDFs",
)

intelligence_data_refresh = define_asset_job(
    name="intelligence_data_refresh",
    selection=AssetSelection.assets("pa_dos_entities", "public_proceedings_scrape", "proceeding_extraction"),
    description="Full intelligence data pipeline: PA DOS + proceedings + extraction",
)
```

- [ ] **Step 3: Export new jobs from the module**

Ensure the new jobs are included in the `__all__` or `Definitions` exports. Check how existing jobs are exported in `definitions.py` and follow the same pattern.

- [ ] **Step 4: Verify jobs load in Dagster**

```bash
cd pipelines && source .venv/bin/activate
dagster job list -m countyiq.definitions 2>/dev/null | grep -E "(pa_dos|proceedings|intelligence)"
```

Expected: All 4 new jobs appear in the list.

- [ ] **Step 5: Commit**

```bash
git add pipelines/countyiq/jobs/__init__.py
git commit -m "feat: Dagster jobs for intelligence data pipelines"
```

---

### Task 10: Source URL Backfill in Existing Assets

**Files:**
- Modify: Multiple existing asset files to include `source_url` in their records

- [ ] **Step 1: Read county_config to identify source URLs**

Read `pipelines/countyiq/lib/county_config.py` and note the URL fields for each source. These are the source_url values that should be written to each staging table.

- [ ] **Step 2: Update ArcGIS asset records to include source_url**

For each ArcGIS asset (parcels, zoning, structures, municipalities, etc.), the `source_url` should be the ArcGIS FeatureServer URL from county_config. Add `source_url` to the record dict before SCD2 upsert, and add `"source_url"` to the `value_columns` list.

Example pattern (apply to each ArcGIS asset):

In the asset function, after creating each record dict, add:

```python
record["source_url"] = county.arcgis_parcels_url  # Use the appropriate URL field
```

And in the `scd2_upsert` call, add `"source_url"` to `value_columns`:

```python
stats = scd2_upsert(
    cursor=cur,
    schema="staging",
    table="parcels",
    records=records,
    key_columns=["pidn"],
    value_columns=[...existing columns..., "source_url"],
)
```

Apply this pattern to all ArcGIS assets, bulk assets (PLCB, FEMA, PA Open Data, tax claims), and scraper assets.

- [ ] **Step 3: Run a quick test to verify source_url flows through**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "
# Verify scd2_upsert handles source_url column without errors
from countyiq.lib.scd import scd2_upsert
import psycopg2
conn = psycopg2.connect('postgresql://dagster_admin:localtest@localhost:5433/countyiq')
cur = conn.cursor()
# Attempt a minimal insert with source_url to verify column exists
cur.execute('''
    SELECT column_name FROM information_schema.columns
    WHERE table_schema = '\''staging'\'' AND table_name = '\''parcels'\'' AND column_name = '\''source_url'\''
''')
print('source_url column exists:', cur.fetchone() is not None)
conn.close()
"
```

- [ ] **Step 4: Commit**

```bash
git add pipelines/countyiq/assets/
git commit -m "feat: add source_url provenance to all existing pipeline assets"
```

---

### Task 11: Integration Verification

- [ ] **Step 1: Verify full migration chain**

```bash
cd pipelines && source .venv/bin/activate
docker compose down -v && docker compose up -d postgres-test
```

Wait for postgres, then:

```bash
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq"
alembic upgrade head
```

Expected: All migrations (001-013) apply cleanly.

- [ ] **Step 2: Verify Dagster loads all assets**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "
from countyiq.definitions import defs
asset_keys = [a.key.to_user_string() for a in defs.get_all_asset_specs()]
print(f'Total assets: {len(asset_keys)}')
for key in sorted(asset_keys):
    print(f'  {key}')
new_assets = [k for k in asset_keys if k in ('pa_dos_entities', 'public_proceedings_scrape', 'proceeding_extraction')]
print(f'New intelligence assets: {new_assets}')
assert len(new_assets) == 3, f'Expected 3 new assets, got {len(new_assets)}'
print('All new assets loaded successfully')
"
```

Expected: All 3 new assets appear in the asset list.

- [ ] **Step 3: Run parser tests**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_pa_dos_parser.py tests/test_proceedings_parser.py tests/test_proceeding_extraction.py -v
```

Expected: All tests PASS.

- [ ] **Step 4: Final commit (if any remaining changes)**

```bash
git status
# If there are uncommitted changes:
git add -A && git commit -m "chore: integration verification cleanup"
```

---

## Phase 1 Complete Checklist

After all tasks are done, verify:

- [ ] Migrations 012 + 013 apply cleanly on fresh database
- [ ] 8 new tables exist (3 staging, 4 public, 1 meta)
- [ ] All existing staging tables have `source_url` column
- [ ] PA DOS scraper asset loads and can be materialized (may need live site testing)
- [ ] Proceedings scraper asset loads (needs municipality_websites populated)
- [ ] Pass 0 extraction asset loads (needs COUNTYIQ_MULTIMODAL_MODEL set)
- [ ] All parser tests pass
- [ ] Dagster UI shows new assets and jobs
- [ ] County config has PA DOS and municipality website fields

## Next: Phase 2 Plan

Phase 2 (LLM Harness & Reasoning Pipeline) will be planned after Phase 1 is complete. It covers:
- llama.cpp model setup and testing on 4090
- Model evaluation framework (test dataset of ~100 parcels)
- Pass 1: Entity verification harness + Dagster asset
- Pass 2: Signal validation harness + Dagster asset
- Pass 3: Brief generation harness + Dagster asset
- Pass 4: County narrative harness + Dagster asset
- Production deployment on Hetzner VPS
