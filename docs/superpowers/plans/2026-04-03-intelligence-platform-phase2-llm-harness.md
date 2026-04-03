# Intelligence Platform Phase 2: LLM Harness & Reasoning Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 4-pass LLM reasoning pipeline that transforms raw signal data into validated evidence, parcel intelligence briefs, and county-level narratives.

**Architecture:** Each pass has three components: (1) a context gatherer (pure SQL/Python that assembles all data the LLM needs), (2) a prompt template (static per pass/signal type, with conditional sections based on available data), (3) a Dagster enrichment asset that orchestrates the pass using the existing `llm_harness.py`. Incremental processing via `meta.intelligence_passes` — only re-run parcels whose input data changed (tracked by input hash). Model selection is empirical — build harness first, then evaluate candidates.

**Tech Stack:** llama-cpp-python (GGUF inference), Dagster (orchestration), psycopg2 (context queries), existing `llm_harness.py` from Phase 1

**Spec:** `docs/superpowers/specs/2026-04-03-intelligence-platform-repositioning-design.md`

**Phase 1 outputs used:** `llm_harness.py` (HarnessConfig, invoke_with_retry), `pass0_templates.py` (pattern reference), `proceeding_extraction.py` (asset pattern reference), tables: `public.evidence`, `public.parcel_briefs`, `public.county_narratives`, `public.entity_graph`, `meta.intelligence_passes`

**Subsequent plans:**
- Phase 3-5: API + Frontend + Cleanup

---

## File Structure

```
pipelines/countyiq/lib/
  llm_harness.py                    # Exists (Phase 1) — no changes
  pass0_templates.py                # Exists (Phase 1) — no changes
  pass1_entity_verification.py      # NEW — context gatherer + template + output parser
  pass2_signal_validation.py        # NEW — context gatherers + templates per signal type
  pass3_brief_generation.py         # NEW — context gatherer + template + output parser
  pass4_county_narratives.py        # NEW — scan functions + templates + output parsers
  intelligence_common.py            # NEW — shared SQL helpers (parcel lookup, entity lookup, etc.)

pipelines/countyiq/assets/enrichment/
  proceeding_extraction.py          # Exists (Phase 1, Pass 0) — no changes
  entity_verification.py            # NEW — Pass 1 Dagster asset
  signal_validation.py              # NEW — Pass 2 Dagster asset
  brief_generation.py               # NEW — Pass 3 Dagster asset
  county_narratives.py              # NEW — Pass 4 Dagster asset

pipelines/countyiq/jobs/__init__.py # Modify — add intelligence pass jobs

pipelines/tests/
  test_intelligence_common.py       # NEW
  test_pass1_entity.py              # NEW
  test_pass2_signals.py             # NEW
  test_pass3_briefs.py              # NEW
  test_pass4_narratives.py          # NEW
  fixtures/
    entity_cluster_sample.json      # NEW — mock entity cluster for Pass 1 tests
    signal_context_sample.json      # NEW — mock signal context for Pass 2 tests
    validated_signals_sample.json   # NEW — mock validated signals for Pass 3 tests
    parcel_briefs_sample.json       # NEW — mock briefs batch for Pass 4 tests

pipelines/eval/                     # NEW — model evaluation framework
  eval_runner.py                    # NEW — runs candidate models through same prompts
  eval_dataset.sql                  # NEW — SQL to extract ~100 test parcels
  eval_report.py                    # NEW — compares model outputs, generates report
```

---

### Task 1: Shared Intelligence Context Module

**Files:**
- Create: `pipelines/countyiq/lib/intelligence_common.py`
- Create: `pipelines/tests/test_intelligence_common.py`

This module provides reusable SQL helper functions that multiple passes need — looking up parcels, entities, portfolios, proceedings, neighbors, etc. Each function takes a database cursor and returns structured dicts.

- [ ] **Step 1: Write failing tests**

```python
# pipelines/tests/test_intelligence_common.py
"""Tests for shared intelligence context helpers.

These test the output structure and formatting of context functions,
not the actual SQL execution (which requires a database).
"""
import pytest
from countyiq.lib.intelligence_common import (
    format_parcel_context,
    format_tax_claims_context,
    format_entity_context,
    format_portfolio_context,
    format_proceedings_context,
    format_neighbors_context,
    format_corporate_context,
    compute_input_hash,
)


class TestFormatParcelContext:
    def test_returns_dict_with_required_keys(self):
        row = {
            "pidn": "4500112340000",
            "owner_full": "SMITH JOHN A",
            "propadr": "1520 MOUNT ROSE AVE",
            "aprtotal": 185000,
            "acres": 4.2,
            "class": "C",
            "saledt": "2024-03-15",
            "price": 185000,
            "previous_owner": "SMITH MARGARET A",
            "municipality": "West Manchester Township",
            "school_dis": "West York Area",
            "source_url": "https://example.com",
        }
        result = format_parcel_context(row)
        assert result["pidn"] == "4500112340000"
        assert result["owner"] == "SMITH JOHN A"
        assert result["address"] == "1520 MOUNT ROSE AVE"
        assert result["assessed_value"] == 185000
        assert result["acres"] == 4.2
        assert result["municipality"] == "West Manchester Township"

    def test_handles_none_values(self):
        row = {
            "pidn": "4500112340000",
            "owner_full": None,
            "propadr": None,
            "aprtotal": None,
            "acres": None,
            "class": None,
            "saledt": None,
            "price": None,
            "previous_owner": None,
            "municipality": None,
            "school_dis": None,
            "source_url": None,
        }
        result = format_parcel_context(row)
        assert result["owner"] == ""
        assert result["assessed_value"] == 0


class TestFormatTaxClaimsContext:
    def test_returns_list_of_dicts(self):
        rows = [
            {"tax_year": 2022, "authority_name": "COUNTY", "total": 1200.0, "owner_name": "SMITH"},
            {"tax_year": 2023, "authority_name": "SCHOOL", "total": 2500.0, "owner_name": "SMITH"},
        ]
        result = format_tax_claims_context(rows)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["year"] == 2022
        assert result[0]["authority"] == "COUNTY"
        assert result[0]["amount"] == 1200.0

    def test_empty_rows_returns_empty_list(self):
        assert format_tax_claims_context([]) == []


class TestComputeInputHash:
    def test_same_input_same_hash(self):
        data = {"pidn": "123", "signals": ["a", "b"]}
        h1 = compute_input_hash(data)
        h2 = compute_input_hash(data)
        assert h1 == h2

    def test_different_input_different_hash(self):
        h1 = compute_input_hash({"pidn": "123"})
        h2 = compute_input_hash({"pidn": "456"})
        assert h1 != h2

    def test_returns_hex_string(self):
        h = compute_input_hash({"test": True})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_intelligence_common.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write implementation**

```python
# pipelines/countyiq/lib/intelligence_common.py
"""Shared context-gathering helpers for the intelligence pipeline.

These functions format database rows into structured dicts that
prompt templates can consume. They also provide SQL query builders
and hashing utilities for incremental processing.
"""
import hashlib
import json
from datetime import date, datetime


def format_parcel_context(row: dict) -> dict:
    """Format a staging.parcels row into context for LLM prompts."""
    return {
        "pidn": row.get("pidn", ""),
        "owner": row.get("owner_full") or "",
        "address": row.get("propadr") or "",
        "assessed_value": row.get("aprtotal") or 0,
        "acres": row.get("acres") or 0,
        "property_class": row.get("class") or "",
        "sale_date": _format_date(row.get("saledt")),
        "sale_price": row.get("price") or 0,
        "previous_owner": row.get("previous_owner") or "",
        "municipality": row.get("municipality") or "",
        "school_district": row.get("school_dis") or "",
        "source_url": row.get("source_url") or "",
    }


def format_tax_claims_context(rows: list[dict]) -> list[dict]:
    """Format staging.tax_claims rows into context."""
    return [
        {
            "year": row.get("tax_year"),
            "authority": row.get("authority_name", ""),
            "amount": row.get("total", 0),
            "owner": row.get("owner_name", ""),
        }
        for row in rows
    ]


def format_entity_context(row: dict | None) -> dict:
    """Format a public.entity_graph row into context."""
    if row is None:
        return {"found": False}
    return {
        "found": True,
        "entity_id": row.get("entity_id"),
        "canonical_name": row.get("canonical_name", ""),
        "entity_type": row.get("entity_type", "unknown"),
        "linked_names": row.get("linked_names") or [],
        "relationships": row.get("relationships") or [],
        "verification_status": row.get("verification_status", ""),
    }


def format_portfolio_context(rows: list[dict]) -> list[dict]:
    """Format parcels owned by the same entity into context."""
    return [
        {
            "pidn": row.get("pidn", ""),
            "address": row.get("propadr") or "",
            "assessed_value": row.get("aprtotal") or 0,
            "sale_date": _format_date(row.get("saledt")),
            "sale_price": row.get("price") or 0,
        }
        for row in rows
    ]


def format_proceedings_context(rows: list[dict]) -> list[dict]:
    """Format staging.proceeding_extractions rows into context."""
    return [
        {
            "type": row.get("extraction_type", ""),
            "applicant": row.get("applicant_name") or "",
            "parcel": row.get("parcel_reference") or "",
            "decision": row.get("decision") or "",
            "meeting_date": _format_date(row.get("meeting_date")),
            "body": row.get("body_name", ""),
            "source_url": row.get("source_url") or "",
            "supporting_text": row.get("supporting_text") or "",
        }
        for row in rows
    ]


def format_neighbors_context(rows: list[dict]) -> list[dict]:
    """Format adjacent parcel rows into context."""
    return [
        {
            "pidn": row.get("pidn", ""),
            "owner": row.get("owner_full") or "",
            "assessed_value": row.get("aprtotal") or 0,
            "acres": row.get("acres") or 0,
            "property_class": row.get("class") or "",
            "total_owed": row.get("total_owed") or 0,
            "years_delinquent": row.get("years_delinquent") or 0,
        }
        for row in rows
    ]


def format_corporate_context(rows: list[dict]) -> list[dict]:
    """Format staging.corporate_entities rows into context."""
    return [
        {
            "entity_name": row.get("entity_name", ""),
            "entity_number": row.get("entity_number") or "",
            "status": row.get("status") or "",
            "formation_date": _format_date(row.get("formation_date")),
            "office_address": row.get("office_address") or "",
            "source_url": row.get("source_url") or "",
        }
        for row in rows
    ]


def compute_input_hash(data: dict) -> str:
    """Compute SHA-256 hash of input data for incremental processing.

    If the hash matches the stored hash for this (pidn, pass_number),
    the pass can be skipped.
    """
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


# --- SQL Query Builders ---

PARCEL_QUERY = """
    SELECT pidn, owner_full, propadr, aprtotal, acres, class,
           saledt, price, previous_owner, deed_book, deed_page,
           municipality, school_dis, source_url
    FROM staging.parcels
    WHERE pidn = %(pidn)s AND valid_to IS NULL
"""

TAX_CLAIMS_QUERY = """
    SELECT tax_year, authority_name, total, owner_name
    FROM staging.tax_claims
    WHERE pidn = %(pidn)s AND valid_to IS NULL
    ORDER BY tax_year
"""

PROCEEDINGS_FOR_PARCEL_QUERY = """
    SELECT pe.extraction_type, pe.applicant_name,
           pe.parcel_reference, pe.decision, pe.conditions,
           pe.supporting_text, pp.body_name, pp.meeting_date,
           pp.source_url
    FROM staging.proceeding_extractions pe
    JOIN staging.public_proceedings pp ON pe.proceeding_id = pp.id
    WHERE pe.parcel_reference = %(pidn)s
    ORDER BY pp.meeting_date DESC
"""

PROCEEDINGS_FOR_ENTITY_QUERY = """
    SELECT pe.extraction_type, pe.applicant_name,
           pe.parcel_reference, pe.decision, pe.conditions,
           pe.supporting_text, pp.body_name, pp.meeting_date,
           pp.source_url
    FROM staging.proceeding_extractions pe
    JOIN staging.public_proceedings pp ON pe.proceeding_id = pp.id
    WHERE pe.applicant_name = ANY(%(names)s)
    ORDER BY pp.meeting_date DESC
"""

NEIGHBORS_QUERY = """
    SELECT p.pidn, p.owner_full, p.aprtotal, p.acres, p.class,
           tc.total_owed, tc.years_delinquent
    FROM staging.parcels p
    LEFT JOIN (
        SELECT pidn, SUM(total) as total_owed,
               COUNT(DISTINCT tax_year) as years_delinquent
        FROM staging.tax_claims WHERE valid_to IS NULL
        GROUP BY pidn
    ) tc ON p.pidn = tc.pidn
    WHERE ST_Touches(p.geom, (
        SELECT geom FROM staging.parcels
        WHERE pidn = %(pidn)s AND valid_to IS NULL
    )) AND p.valid_to IS NULL
"""

CORPORATE_FOR_NAMES_QUERY = """
    SELECT entity_name, entity_number, status, formation_date,
           office_address, source_url
    FROM staging.corporate_entities
    WHERE entity_name = ANY(%(names)s)
      AND valid_to IS NULL
"""

ENTITY_GRAPH_QUERY = """
    SELECT entity_id, canonical_name, entity_type, linked_names,
           linked_sources, relationships, verification_status
    FROM public.entity_graph
    WHERE canonical_name = %(name)s
       OR %(name)s = ANY(linked_names)
    LIMIT 1
"""

PORTFOLIO_QUERY = """
    SELECT p.pidn, p.propadr, p.aprtotal, p.saledt, p.price
    FROM staging.parcels p
    WHERE p.owner_full = ANY(%(names)s)
      AND p.valid_to IS NULL
"""


def _format_date(val) -> str:
    """Format a date value to ISO string, or empty string."""
    if val is None:
        return ""
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return str(val)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_intelligence_common.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pipelines/countyiq/lib/intelligence_common.py pipelines/tests/test_intelligence_common.py
git commit -m "feat: shared intelligence context module with SQL helpers"
```

---

### Task 2: Pass 1 — Entity Verification

**Files:**
- Create: `pipelines/countyiq/lib/pass1_entity_verification.py`
- Create: `pipelines/countyiq/assets/enrichment/entity_verification.py`
- Create: `pipelines/tests/test_pass1_entity.py`
- Create: `pipelines/tests/fixtures/entity_cluster_sample.json`

Pass 1 cross-references owner identities across all sources and builds a relationship graph. It has two stages: SQL pre-filter (finds candidate clusters) and LLM reasoning (verifies each cluster).

- [ ] **Step 1: Create test fixture**

```json
// pipelines/tests/fixtures/entity_cluster_sample.json
{
  "cluster_id": "cluster_001",
  "records": {
    "parcels": [
      {"pidn": "4500112340000", "owner_full": "SMITH JOHN A", "propadr": "1520 MOUNT ROSE AVE", "municipality": "West Manchester Township", "saledt": "2024-03-15", "price": 185000, "previous_owner": "SMITH MARGARET A"},
      {"pidn": "4500112350000", "owner_full": "SMITH JOHN A", "propadr": "1522 MOUNT ROSE AVE", "municipality": "West Manchester Township", "saledt": "2019-08-01", "price": 95000, "previous_owner": "FIRST NATIONAL BANK"}
    ],
    "tax_claims": [
      {"pidn": "4500112340000", "owner_name": "SMITH JOHN", "tax_year": 2022, "authority_name": "COUNTY", "total": 1200.0},
      {"pidn": "4500112340000", "owner_name": "SMITH JOHN", "tax_year": 2023, "authority_name": "COUNTY", "total": 1350.0},
      {"pidn": "4500118800000", "owner_name": "J A SMITH HOLDINGS LLC", "tax_year": 2021, "authority_name": "SCHOOL", "total": 4800.0}
    ],
    "plcb_licenses": [
      {"lid": "12345", "licensee": "MOUNT ROSE TAVERN INC", "premises_owner": "SMITH JOHN A", "premises_address": "1520 MOUNT ROSE AVE, YORK PA", "municipality": "WEST MANCHESTER TWP"}
    ],
    "corporate_entities": [
      {"entity_name": "J A SMITH HOLDINGS LLC", "entity_number": "6834765", "status": "Active", "formation_date": "2018-06-12", "office_address": "1520 Mount Rose Ave, York PA 17403"},
      {"entity_name": "MOUNT ROSE TAVERN INC", "entity_number": "7812345", "status": "Active", "formation_date": "2020-01-15", "office_address": "1520 Mount Rose Ave, York PA 17403"}
    ],
    "proceedings": [
      {"extraction_type": "conditional_use", "applicant_name": "J A SMITH HOLDINGS", "parcel_reference": "4500118800000", "decision": "approved", "meeting_date": "2025-10-02", "body_name": "West Manchester Township ZHB", "source_url": "https://example.com/zhb"}
    ]
  }
}
```

- [ ] **Step 2: Write failing tests**

```python
# pipelines/tests/test_pass1_entity.py
"""Tests for Pass 1: Entity Verification context and templates."""
import json
import os
import pytest
from countyiq.lib.pass1_entity_verification import (
    build_entity_cluster_prompt,
    parse_entity_verification_output,
    ENTITY_VERIFICATION_TEMPLATE,
)


@pytest.fixture
def sample_cluster():
    fixture_path = os.path.join(
        os.path.dirname(__file__), "fixtures", "entity_cluster_sample.json"
    )
    with open(fixture_path) as f:
        return json.load(f)


class TestBuildEntityClusterPrompt:
    def test_returns_string(self, sample_cluster):
        prompt = build_entity_cluster_prompt(sample_cluster["records"])
        assert isinstance(prompt, str)

    def test_includes_parcel_owner_names(self, sample_cluster):
        prompt = build_entity_cluster_prompt(sample_cluster["records"])
        assert "SMITH JOHN A" in prompt

    def test_includes_tax_claim_names(self, sample_cluster):
        prompt = build_entity_cluster_prompt(sample_cluster["records"])
        assert "J A SMITH HOLDINGS LLC" in prompt

    def test_includes_corporate_data(self, sample_cluster):
        prompt = build_entity_cluster_prompt(sample_cluster["records"])
        assert "1520 Mount Rose Ave" in prompt
        assert "Active" in prompt

    def test_includes_proceedings(self, sample_cluster):
        prompt = build_entity_cluster_prompt(sample_cluster["records"])
        assert "conditional_use" in prompt

    def test_includes_plcb_data(self, sample_cluster):
        prompt = build_entity_cluster_prompt(sample_cluster["records"])
        assert "MOUNT ROSE TAVERN" in prompt

    def test_omits_empty_sections(self):
        records = {"parcels": [{"pidn": "123", "owner_full": "TEST"}]}
        prompt = build_entity_cluster_prompt(records)
        assert "TAX CLAIM RECORDS" not in prompt
        assert "PLCB LICENSES" not in prompt


class TestParseEntityVerificationOutput:
    def test_valid_output(self):
        output = {
            "entities": [
                {
                    "canonical_name": "SMITH JOHN A",
                    "entity_type": "person",
                    "confidence": 0.95,
                    "reasoning": "Same name on two parcels at same address.",
                    "linked_records": [
                        {"source": "parcels", "id": "4500112340000"},
                        {"source": "tax_claims", "id": "4500112340000"},
                    ],
                    "relationships": [
                        {"related_entity": "J A SMITH HOLDINGS LLC", "relationship": "owner_of"}
                    ],
                    "portfolio_summary": "2 parcels, 1 delinquent"
                }
            ],
            "rejected_matches": [
                {"record_a": "SMITH JOHN A", "record_b": "SMITH JAMES", "reason": "Different first name"}
            ]
        }
        result = parse_entity_verification_output(output)
        assert len(result["entities"]) == 1
        assert result["entities"][0]["canonical_name"] == "SMITH JOHN A"
        assert len(result["rejected_matches"]) == 1

    def test_empty_entities(self):
        output = {"entities": [], "rejected_matches": []}
        result = parse_entity_verification_output(output)
        assert result["entities"] == []

    def test_missing_keys_returns_error(self):
        output = {"bad_key": "value"}
        result = parse_entity_verification_output(output)
        assert result.get("error") is not None


class TestEntityVerificationTemplate:
    def test_template_has_required_sections(self):
        assert "PARCEL RECORDS" in ENTITY_VERIFICATION_TEMPLATE
        assert "TASKS" in ENTITY_VERIFICATION_TEMPLATE
        assert "OUTPUT FORMAT" in ENTITY_VERIFICATION_TEMPLATE
        assert "canonical_name" in ENTITY_VERIFICATION_TEMPLATE
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_pass1_entity.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 4: Write implementation**

```python
# pipelines/countyiq/lib/pass1_entity_verification.py
"""Pass 1: Entity Verification — context gatherer, template, and output parser.

Determines which records across parcel ownership, tax claims, PLCB licenses,
PA business registrations, corporate entities, and public proceedings belong
to the same real-world person or entity. Builds a relationship graph.
"""
import json


ENTITY_VERIFICATION_TEMPLATE = """You are an entity resolution analyst for York County, PA property records.

CANDIDATE CLUSTER:
Records that may belong to the same entity or related entities.

PARCEL RECORDS:
{parcel_section}

{tax_claims_section}

{plcb_section}

{corporate_section}

{proceedings_section}

TASKS:
1. Which records belong to the same real-world person or entity? Group them and explain your reasoning.
2. For each group, what is the relationship structure? (e.g., individual owns LLC, LLC holds properties)
3. Are there any records that look similar but are likely DIFFERENT entities? Flag those with reasoning.
4. What is the portfolio picture? (total parcels, total delinquency, business connections)

Answer each question using ONLY the data provided above. Do not invent facts.

OUTPUT FORMAT:
{{
  "entities": [
    {{
      "canonical_name": "preferred name for this entity",
      "entity_type": "person|business|trust|government",
      "confidence": 0.0-1.0,
      "reasoning": "why you believe these records are the same entity",
      "linked_records": [
        {{"source": "parcels|tax_claims|plcb|corporate|proceedings", "id": "identifier"}}
      ],
      "relationships": [
        {{"related_entity": "name", "relationship": "owner_of|subsidiary|previous_identity|tenant|lender"}}
      ],
      "portfolio_summary": "brief summary of holdings and status"
    }}
  ],
  "rejected_matches": [
    {{"record_a": "name A", "record_b": "name B", "reason": "why these are NOT the same entity"}}
  ]
}}"""


def build_entity_cluster_prompt(records: dict) -> str:
    """Build the Pass 1 prompt from a cluster of candidate records.

    Args:
        records: Dict with keys 'parcels', 'tax_claims', 'plcb_licenses',
                 'corporate_entities', 'proceedings' — each a list of dicts.

    Returns:
        Formatted prompt string ready for LLM invocation.
    """
    parcel_section = _format_parcel_records(records.get("parcels", []))
    tax_section = _format_tax_claims(records.get("tax_claims", []))
    plcb_section = _format_plcb(records.get("plcb_licenses", []))
    corporate_section = _format_corporate(records.get("corporate_entities", []))
    proceedings_section = _format_proceedings(records.get("proceedings", []))

    return ENTITY_VERIFICATION_TEMPLATE.format(
        parcel_section=parcel_section,
        tax_claims_section=tax_section,
        plcb_section=plcb_section,
        corporate_section=corporate_section,
        proceedings_section=proceedings_section,
    )


def parse_entity_verification_output(output: dict) -> dict:
    """Validate and normalize the LLM's entity verification output.

    Args:
        output: Parsed JSON from LLM response.

    Returns:
        Dict with 'entities' and 'rejected_matches' lists, or 'error' key.
    """
    if "entities" not in output:
        return {"error": "Missing 'entities' key in LLM output", "entities": [], "rejected_matches": []}

    entities = []
    for e in output.get("entities", []):
        entities.append({
            "canonical_name": e.get("canonical_name", ""),
            "entity_type": e.get("entity_type", "unknown"),
            "confidence": min(max(float(e.get("confidence", 0)), 0.0), 1.0),
            "reasoning": e.get("reasoning", ""),
            "linked_records": e.get("linked_records", []),
            "relationships": e.get("relationships", []),
            "portfolio_summary": e.get("portfolio_summary", ""),
        })

    rejected = []
    for r in output.get("rejected_matches", []):
        rejected.append({
            "record_a": r.get("record_a", ""),
            "record_b": r.get("record_b", ""),
            "reason": r.get("reason", ""),
        })

    return {"entities": entities, "rejected_matches": rejected}


# --- SQL for candidate cluster identification ---

CANDIDATE_CLUSTERS_QUERY = """
WITH owner_names AS (
    -- All unique owner names from parcels
    SELECT DISTINCT owner_full AS name, municipality
    FROM staging.parcels
    WHERE valid_to IS NULL AND owner_full IS NOT NULL AND owner_full != ''
),
-- Find names with pg_trgm similarity > 0.5 within same municipality
name_pairs AS (
    SELECT a.name AS name_a, b.name AS name_b, a.municipality,
           similarity(a.name, b.name) AS sim
    FROM owner_names a
    JOIN owner_names b ON a.name < b.name
      AND a.municipality = b.municipality
      AND similarity(a.name, b.name) > 0.5
),
-- Find names sharing office address via corporate entities
office_matches AS (
    SELECT a.entity_name AS name_a, b.entity_name AS name_b,
           a.office_address
    FROM staging.corporate_entities a
    JOIN staging.corporate_entities b
      ON a.office_address = b.office_address
      AND a.entity_name < b.entity_name
      AND a.valid_to IS NULL AND b.valid_to IS NULL
      AND a.office_address IS NOT NULL AND a.office_address != ''
)
SELECT * FROM name_pairs
UNION ALL
SELECT name_a, name_b, '' AS municipality, 1.0 AS sim FROM office_matches
ORDER BY sim DESC
"""

CLUSTER_RECORDS_QUERY_PARCELS = """
    SELECT pidn, owner_full, propadr, municipality, saledt, price,
           previous_owner, deed_book, deed_page, source_url
    FROM staging.parcels
    WHERE owner_full = ANY(%(names)s) AND valid_to IS NULL
"""

CLUSTER_RECORDS_QUERY_TAX = """
    SELECT pidn, owner_name, tax_year, authority_name, total
    FROM staging.tax_claims
    WHERE owner_name = ANY(%(names)s) AND valid_to IS NULL
"""

CLUSTER_RECORDS_QUERY_PLCB = """
    SELECT lid, licensee, premises_owner, premises_address, municipality
    FROM staging.plcb_licenses
    WHERE (licensee = ANY(%(names)s) OR premises_owner = ANY(%(names)s))
      AND valid_to IS NULL
"""

CLUSTER_RECORDS_QUERY_CORPORATE = """
    SELECT entity_name, entity_number, status, formation_date,
           office_address, source_url
    FROM staging.corporate_entities
    WHERE entity_name = ANY(%(names)s) AND valid_to IS NULL
"""

CLUSTER_RECORDS_QUERY_PROCEEDINGS = """
    SELECT pe.extraction_type, pe.applicant_name, pe.parcel_reference,
           pe.decision, pp.meeting_date, pp.body_name, pp.source_url
    FROM staging.proceeding_extractions pe
    JOIN staging.public_proceedings pp ON pe.proceeding_id = pp.id
    WHERE pe.applicant_name = ANY(%(names)s)
    ORDER BY pp.meeting_date DESC
"""


def gather_cluster_records(cursor, names: list[str]) -> dict:
    """Gather all records for a candidate entity cluster from all sources.

    Args:
        cursor: Database cursor.
        names: List of candidate entity names in this cluster.

    Returns:
        Dict with keys: parcels, tax_claims, plcb_licenses,
        corporate_entities, proceedings.
    """
    params = {"names": names}
    records = {}

    cursor.execute(CLUSTER_RECORDS_QUERY_PARCELS, params)
    records["parcels"] = [dict(row) for row in cursor.fetchall()]

    cursor.execute(CLUSTER_RECORDS_QUERY_TAX, params)
    records["tax_claims"] = [dict(row) for row in cursor.fetchall()]

    cursor.execute(CLUSTER_RECORDS_QUERY_PLCB, params)
    records["plcb_licenses"] = [dict(row) for row in cursor.fetchall()]

    cursor.execute(CLUSTER_RECORDS_QUERY_CORPORATE, params)
    records["corporate_entities"] = [dict(row) for row in cursor.fetchall()]

    cursor.execute(CLUSTER_RECORDS_QUERY_PROCEEDINGS, params)
    records["proceedings"] = [dict(row) for row in cursor.fetchall()]

    return records


# --- Formatting helpers ---

def _format_parcel_records(parcels: list[dict]) -> str:
    if not parcels:
        return "(no parcel records)"
    lines = []
    for p in parcels:
        parts = [f"PIDN {p.get('pidn', '?')}"]
        if p.get("owner_full"):
            parts.append(f"Owner: {p['owner_full']}")
        if p.get("propadr"):
            parts.append(p["propadr"])
        if p.get("saledt"):
            parts.append(f"Sold {p['saledt']} for ${p.get('price', '?'):,}")
        if p.get("previous_owner"):
            parts.append(f"Previous owner: {p['previous_owner']}")
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)


def _format_tax_claims(claims: list[dict]) -> str:
    if not claims:
        return ""
    lines = ["TAX CLAIM RECORDS:"]
    for c in claims:
        lines.append(
            f"- PIDN {c.get('pidn', '?')} | Owner: {c.get('owner_name', '?')} | "
            f"{c.get('authority_name', '?')} tax {c.get('tax_year', '?')}: ${c.get('total', 0):,.0f}"
        )
    return "\n".join(lines)


def _format_plcb(licenses: list[dict]) -> str:
    if not licenses:
        return ""
    lines = ["PLCB LICENSES:"]
    for lic in licenses:
        lines.append(
            f"- License #{lic.get('lid', '?')} | Licensee: {lic.get('licensee', '?')} | "
            f"Premises owner: {lic.get('premises_owner', '?')} | {lic.get('premises_address', '?')}"
        )
    return "\n".join(lines)


def _format_corporate(entities: list[dict]) -> str:
    if not entities:
        return ""
    lines = ["PA DOS CORPORATE RECORDS:"]
    for e in entities:
        lines.append(
            f"- {e.get('entity_name', '?')} (#{e.get('entity_number', '?')}) | "
            f"Status: {e.get('status', '?')} | Formed: {e.get('formation_date', '?')} | "
            f"Office: {e.get('office_address', '?')}"
        )
    return "\n".join(lines)


def _format_proceedings(procs: list[dict]) -> str:
    if not procs:
        return ""
    lines = ["PUBLIC PROCEEDINGS:"]
    for p in procs:
        lines.append(
            f"- {p.get('extraction_type', '?')} by {p.get('applicant_name', '?')} | "
            f"Re: {p.get('parcel_reference', '?')} | Decision: {p.get('decision', '?')} | "
            f"{p.get('body_name', '?')} {p.get('meeting_date', '?')}"
        )
    return "\n".join(lines)
```

- [ ] **Step 5: Run tests**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_pass1_entity.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Write the Pass 1 Dagster asset**

```python
# pipelines/countyiq/assets/enrichment/entity_verification.py
"""Pass 1: Entity Verification — Dagster asset.

Identifies candidate entity clusters via SQL pre-filter, then sends
each cluster through the LLM for reasoning about entity matches.
Results stored in public.entity_graph.
"""
import os
import json
from dagster import asset, AssetExecutionContext, MaterializeResult, MetadataValue

from countyiq.lib.pass1_entity_verification import (
    build_entity_cluster_prompt,
    parse_entity_verification_output,
    gather_cluster_records,
    CANDIDATE_CLUSTERS_QUERY,
)
from countyiq.lib.intelligence_common import compute_input_hash
from countyiq.resources.database import DatabaseResource

MODEL_PATH = os.environ.get("COUNTYIQ_TEXT_MODEL", "")


@asset(
    group_name="enrichment",
    deps=["pa_dos_entities", "proceeding_extraction", "development_signals"],
    description="Pass 1: verify entity matches across sources, build relationship graph",
    kinds={"postgres", "llm"},
)
def entity_verification(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    if not MODEL_PATH:
        context.log.warning("COUNTYIQ_TEXT_MODEL not set — skipping Pass 1")
        return MaterializeResult(metadata={"status": MetadataValue.text("skipped")})

    from countyiq.lib.llm_harness import HarnessConfig, invoke_with_retry

    config = HarnessConfig(
        model_path=MODEL_PATH,
        n_ctx=4096,
        n_gpu_layers=int(os.environ.get("COUNTYIQ_GPU_LAYERS", "-1")),
        temperature=0.1,
        max_tokens=2048,
    )

    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        # Stage A: SQL pre-filter — find candidate clusters
        context.log.info("Pass 1 Stage A: identifying candidate entity clusters")
        cur.execute(CANDIDATE_CLUSTERS_QUERY)
        pairs = cur.fetchall()
        context.log.info(f"Found {len(pairs)} candidate name pairs")

        # Group pairs into clusters (connected components)
        clusters = _build_clusters(pairs)
        context.log.info(f"Grouped into {len(clusters)} clusters")

        # Stage B: LLM reasoning per cluster
        entities_created = 0
        errors = 0

        for i, cluster_names in enumerate(clusters):
            # Check if this cluster was already processed (input hash)
            records = gather_cluster_records(cur, cluster_names)
            input_hash = compute_input_hash(records)

            cur.execute("""
                SELECT input_hash FROM meta.intelligence_passes
                WHERE pidn = %(cluster_key)s AND pass_number = 1
                  AND status = 'complete' AND input_hash = %(hash)s
            """, {"cluster_key": cluster_names[0], "hash": input_hash})

            if cur.fetchone():
                continue  # Skip — already processed with same data

            # Update pass tracking
            cur.execute("""
                INSERT INTO meta.intelligence_passes (pidn, pass_number, status, last_run_at, input_hash)
                VALUES (%(key)s, 1, 'running', NOW(), %(hash)s)
                ON CONFLICT (pidn, pass_number) DO UPDATE
                SET status = 'running', last_run_at = NOW(), input_hash = %(hash)s
            """, {"key": cluster_names[0], "hash": input_hash})
            conn.commit()

            try:
                prompt = build_entity_cluster_prompt(records)
                result = invoke_with_retry(config, prompt, retries=1)

                if not result.success:
                    context.log.warning(f"Pass 1 failed for cluster {cluster_names[0]}: {result.error}")
                    cur.execute("""
                        UPDATE meta.intelligence_passes
                        SET status = 'failed', error_message = %(err)s
                        WHERE pidn = %(key)s AND pass_number = 1
                    """, {"key": cluster_names[0], "err": result.error})
                    conn.commit()
                    errors += 1
                    continue

                parsed = parse_entity_verification_output(result.parsed)

                if parsed.get("error"):
                    context.log.warning(f"Parse error for cluster {cluster_names[0]}: {parsed['error']}")
                    errors += 1
                    continue

                # Upsert entities to public.entity_graph
                for entity in parsed["entities"]:
                    cur.execute("""
                        INSERT INTO public.entity_graph
                            (canonical_name, entity_type, linked_names, linked_sources,
                             relationships, verification_status, verification_reasoning, verified_at)
                        VALUES (%(name)s, %(type)s, %(linked)s, %(sources)s,
                                %(rels)s, 'verified', %(reasoning)s, NOW())
                        ON CONFLICT (entity_id) DO NOTHING
                    """, {
                        "name": entity["canonical_name"],
                        "type": entity["entity_type"],
                        "linked": cluster_names,
                        "sources": json.dumps(entity["linked_records"]),
                        "rels": json.dumps(entity["relationships"]),
                        "reasoning": entity["reasoning"],
                    })
                    entities_created += 1

                # Mark pass complete
                cur.execute("""
                    UPDATE meta.intelligence_passes
                    SET status = 'complete', error_message = NULL
                    WHERE pidn = %(key)s AND pass_number = 1
                """, {"key": cluster_names[0]})
                conn.commit()

            except Exception as e:
                context.log.warning(f"Error processing cluster {cluster_names[0]}: {e}")
                conn.rollback()
                errors += 1

            if (i + 1) % 100 == 0:
                context.log.info(f"Processed {i + 1}/{len(clusters)} clusters")

    finally:
        if was_autocommit:
            conn.autocommit = True
        cur.close()

    return MaterializeResult(metadata={
        "clusters_processed": MetadataValue.int(len(clusters)),
        "entities_created": MetadataValue.int(entities_created),
        "errors": MetadataValue.int(errors),
    })


def _build_clusters(pairs) -> list[list[str]]:
    """Build connected components from name pairs using union-find."""
    parent = {}

    def find(x):
        if x not in parent:
            parent[x] = x
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for row in pairs:
        name_a = row[0] if isinstance(row, (list, tuple)) else row.get("name_a", "")
        name_b = row[1] if isinstance(row, (list, tuple)) else row.get("name_b", "")
        if name_a and name_b:
            union(name_a, name_b)

    groups = {}
    for name in parent:
        root = find(name)
        groups.setdefault(root, []).append(name)

    return list(groups.values())
```

- [ ] **Step 7: Verify asset loads**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "from countyiq.assets.enrichment.entity_verification import entity_verification; print('OK')"
```

Expected: OK.

- [ ] **Step 8: Commit**

```bash
git add pipelines/countyiq/lib/pass1_entity_verification.py pipelines/countyiq/assets/enrichment/entity_verification.py pipelines/tests/test_pass1_entity.py pipelines/tests/fixtures/entity_cluster_sample.json
git commit -m "feat: Pass 1 entity verification — context gatherer, template, and Dagster asset"
```

---

### Task 3: Pass 2 — Signal Validation

**Files:**
- Create: `pipelines/countyiq/lib/pass2_signal_validation.py`
- Create: `pipelines/countyiq/assets/enrichment/signal_validation.py`
- Create: `pipelines/tests/test_pass2_signals.py`
- Create: `pipelines/tests/fixtures/signal_context_sample.json`

Pass 2 interrogates each signal on each parcel to determine if it's actually meaningful. Each signal type has static base questions and conditional questions based on available data.

- [ ] **Step 1: Create test fixture**

```json
// pipelines/tests/fixtures/signal_context_sample.json
{
  "pidn": "4500112340000",
  "signal": {
    "signal_key": "active_subdivision",
    "signal_weight": 0.30,
    "source_table": "staging.planning_subdivisions",
    "distance_m": 180.0,
    "evidence": {
      "plan_title": "Meadowbrook Phase 3",
      "date_rcvd": "2025-11-14",
      "prop_lots": 48,
      "prop_du": 48,
      "total_acres": 22.5,
      "pt_land_dev": true
    }
  },
  "parcel": {
    "pidn": "4500112340000",
    "owner": "SMITH JOHN A",
    "address": "1520 MOUNT ROSE AVE",
    "assessed_value": 185000,
    "acres": 4.2,
    "property_class": "C",
    "municipality": "West Manchester Township"
  },
  "entity": {"found": true, "canonical_name": "SMITH JOHN A", "entity_type": "person"},
  "tax_claims": [
    {"year": 2022, "authority": "COUNTY", "amount": 1200.0},
    {"year": 2023, "authority": "COUNTY", "amount": 1350.0}
  ],
  "proceedings": [
    {"type": "subdivision_review", "applicant": "MEADOWBROOK DEV", "decision": "approved", "meeting_date": "2025-12-03"}
  ],
  "neighbors": [],
  "corporate": []
}
```

- [ ] **Step 2: Write failing tests**

```python
# pipelines/tests/test_pass2_signals.py
"""Tests for Pass 2: Signal Validation context and templates."""
import json
import os
import pytest
from countyiq.lib.pass2_signal_validation import (
    SIGNAL_TEMPLATES,
    build_signal_validation_prompt,
    parse_signal_validation_output,
)


@pytest.fixture
def sample_context():
    fixture_path = os.path.join(
        os.path.dirname(__file__), "fixtures", "signal_context_sample.json"
    )
    with open(fixture_path) as f:
        return json.load(f)


class TestSignalTemplates:
    def test_all_signal_types_have_templates(self):
        expected = [
            "active_subdivision", "ecodev_candidate", "zoning_mismatch",
            "ownership_change", "vacancy", "tax_distress", "assemblage",
            "penndot_project", "cdbg_investment", "growth_area",
            "flood_zone", "conservation_easement", "ag_security",
        ]
        for sig in expected:
            assert sig in SIGNAL_TEMPLATES, f"Missing template for {sig}"

    def test_each_template_has_base_questions(self):
        for key, tmpl in SIGNAL_TEMPLATES.items():
            assert "base_questions" in tmpl, f"{key} missing base_questions"
            assert len(tmpl["base_questions"]) > 0, f"{key} has empty base_questions"

    def test_each_template_has_conditional_questions(self):
        for key, tmpl in SIGNAL_TEMPLATES.items():
            assert "conditional_questions" in tmpl, f"{key} missing conditional_questions"


class TestBuildSignalValidationPrompt:
    def test_returns_string(self, sample_context):
        prompt = build_signal_validation_prompt(sample_context)
        assert isinstance(prompt, str)

    def test_includes_signal_key(self, sample_context):
        prompt = build_signal_validation_prompt(sample_context)
        assert "active_subdivision" in prompt

    def test_includes_parcel_context(self, sample_context):
        prompt = build_signal_validation_prompt(sample_context)
        assert "4500112340000" in prompt
        assert "SMITH JOHN A" in prompt

    def test_includes_evidence(self, sample_context):
        prompt = build_signal_validation_prompt(sample_context)
        assert "Meadowbrook Phase 3" in prompt

    def test_includes_conditional_questions_when_data_present(self, sample_context):
        prompt = build_signal_validation_prompt(sample_context)
        # Has proceedings → should include proceedings-related question
        assert "proceedings" in prompt.lower() or "Proceedings" in prompt

    def test_excludes_sections_without_data(self, sample_context):
        sample_context["neighbors"] = []
        sample_context["corporate"] = []
        prompt = build_signal_validation_prompt(sample_context)
        assert "ADJACENT PARCELS" not in prompt
        assert "CORPORATE RECORDS" not in prompt


class TestParseSignalValidationOutput:
    def test_valid_output(self):
        output = {
            "signal_key": "active_subdivision",
            "validation_status": "confirmed",
            "adjusted_significance": "high",
            "reasoning": "48-lot land development filed 5 months ago, 180m away.",
            "key_facts": ["48-lot land development", "filed 5 months ago"],
            "cross_references": ["ZHB approval 2025-12-03"],
        }
        result = parse_signal_validation_output(output)
        assert result["validation_status"] == "confirmed"
        assert result["adjusted_significance"] == "high"

    def test_clamps_invalid_status(self):
        output = {
            "signal_key": "test",
            "validation_status": "SUPER_GOOD",
            "adjusted_significance": "mega_high",
            "reasoning": "test",
        }
        result = parse_signal_validation_output(output)
        assert result["validation_status"] == "confirmed"  # default
        assert result["adjusted_significance"] == "medium"  # default

    def test_missing_reasoning_returns_error(self):
        output = {"signal_key": "test"}
        result = parse_signal_validation_output(output)
        assert result.get("error") is not None
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_pass2_signals.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 4: Write implementation**

```python
# pipelines/countyiq/lib/pass2_signal_validation.py
"""Pass 2: Signal Validation — context gatherer, templates, and output parser.

For each signal on each parcel, interrogates whether it's actually meaningful
using signal-type-specific validation questions. Context is gathered via SQL;
the LLM reasons about the assembled evidence.
"""
import json
from countyiq.lib.intelligence_common import (
    PARCEL_QUERY, TAX_CLAIMS_QUERY, PROCEEDINGS_FOR_PARCEL_QUERY,
    PROCEEDINGS_FOR_ENTITY_QUERY, NEIGHBORS_QUERY, CORPORATE_FOR_NAMES_QUERY,
    ENTITY_GRAPH_QUERY, PORTFOLIO_QUERY,
    format_parcel_context, format_tax_claims_context,
    format_entity_context, format_portfolio_context,
    format_proceedings_context, format_neighbors_context,
    format_corporate_context,
)

VALID_STATUSES = {"confirmed", "upgraded", "downgraded", "stale", "irrelevant"}
VALID_SIGNIFICANCE = {"high", "medium", "low", "none"}

# --- Signal-specific validation templates ---

SIGNAL_TEMPLATES = {
    "active_subdivision": {
        "base_questions": [
            "Is this plan recent enough to indicate active development pressure? Plans older than 2 years with no follow-up may be stale.",
            "Is the scale significant? A 3-lot minor subdivision is different from a 48-lot land development.",
            "Is the distance close enough to affect the subject parcel? 180m is adjacent, 800m+ may not matter.",
            "Does the plan type match the subject parcel's development potential?",
        ],
        "conditional_questions": {
            "has_proceedings": "Proceedings records mention this plan or applicant. Has it been approved, denied, tabled, or modified? Do any conditions affect feasibility?",
            "has_corporate": "The applicant is a registered entity. Is it newly formed (speculative) or established (credible)?",
        },
    },
    "tax_distress": {
        "base_questions": [
            "Is this chronic distress (multi-year, escalating) or a one-time miss?",
            "Is the amount significant relative to assessed value?",
            "How close is this to judicial sale threshold (typically 3-5 years of delinquency)?",
        ],
        "conditional_questions": {
            "has_portfolio": "This owner controls other parcels. Are those also delinquent? Is this systemic financial distress?",
            "has_corporate": "Is the owning entity still active per PA DOS, or dissolved/forfeited?",
            "has_deeds": "Are there recent deed transfers suggesting an attempted exit?",
        },
    },
    "ownership_change": {
        "base_questions": [
            "Is this a market transaction or a non-arm's-length transfer? Bank-to-LLC suggests foreclosure acquisition.",
            "Does the price suggest distressed acquisition?",
            "Is the buyer connected to other development activity via the entity graph?",
        ],
        "conditional_questions": {
            "has_proceedings": "Any post-acquisition proceedings or permit filings by this entity?",
            "has_corporate": "Is the buyer entity newly formed or established? LLC buyer often indicates investor interest.",
        },
    },
    "zoning_mismatch": {
        "base_questions": [
            "Is this a meaningful mismatch or a labeling artifact? R-1 vs General Commercial is real. R-2 vs R-3 is noise.",
            "Is the future land use plan recent enough to reflect current municipal intentions?",
            "Are adjacent parcels also mismatched? A corridor-wide mismatch is more significant than a single outlier.",
        ],
        "conditional_questions": {
            "has_proceedings": "Have any rezoning applications been filed for this parcel or this corridor?",
            "has_neighbors": "Do adjacent parcels show the same mismatch pattern?",
        },
    },
    "vacancy": {
        "base_questions": [
            "Is this genuinely vacant or does the structures data have gaps? Check acreage vs assessed value for consistency.",
            "How long has it been vacant? No sale activity for 10+ years suggests long-term underutilization.",
            "Is the assessed value consistent with vacant land for this area?",
        ],
        "conditional_questions": {
            "has_proceedings": "Any demolition permits or environmental remediation in proceedings?",
        },
    },
    "assemblage": {
        "base_questions": [
            "Does entity resolution change the ownership fragmentation picture?",
            "Are the delinquent neighbors in deep distress (multi-year) or light distress (1-year small amounts)?",
            "Is the total acreage meaningful for development given the zoning?",
        ],
        "conditional_questions": {
            "has_neighbors": "Is any entity in this cluster already acquiring adjacent parcels?",
            "has_corporate": "Do any adjacent owners share the same registered office address?",
        },
    },
    "ecodev_candidate": {
        "base_questions": [
            "Is the YCPC data current? When was this parcel last evaluated?",
            "How underutilized is the parcel (percent_underutilized)?",
            "Is sewer/water infrastructure available?",
        ],
        "conditional_questions": {},
    },
    "penndot_project": {
        "base_questions": [
            "Is this PennDOT project still active or was it completed?",
            "Is the proximity close enough to be a development catalyst?",
        ],
        "conditional_questions": {},
    },
    "cdbg_investment": {
        "base_questions": [
            "Is this CDBG project current or historical?",
            "Is the proximity relevant to the subject parcel?",
        ],
        "conditional_questions": {},
    },
    "growth_area": {
        "base_questions": [
            "Is this a Primary Growth Area (PGA) or Secondary Growth Area (SGA)?",
            "Note: this is a tiebreaker signal only — low weight.",
        ],
        "conditional_questions": {},
    },
    "flood_zone": {
        "base_questions": [
            "How much of the parcel is in the SFHA zone? Partial overlap is less constraining.",
            "Does this discount the opportunity or eliminate it?",
        ],
        "conditional_questions": {},
    },
    "conservation_easement": {
        "base_questions": [
            "Confirm the restriction is still active.",
            "This is a hard exclusion — no development possible.",
        ],
        "conditional_questions": {
            "has_proceedings": "Have any removal or modification requests been filed?",
        },
    },
    "ag_security": {
        "base_questions": [
            "Confirm the agricultural security enrollment is still active.",
            "This is a hard exclusion — restricted from development.",
        ],
        "conditional_questions": {
            "has_proceedings": "Have any withdrawal requests been filed?",
        },
    },
}


SIGNAL_VALIDATION_PROMPT = """You are a real estate intelligence analyst for York County, PA.

SIGNAL: {signal_key}
EVIDENCE:
{evidence_section}

PARCEL:
{parcel_section}

ENTITY CONTEXT:
{entity_section}

{optional_sections}

VALIDATION QUESTIONS:
{questions_section}

Answer each question using ONLY the data provided above. Do not invent facts.
If the data is insufficient to answer a question, say so.

OUTPUT FORMAT:
{{
  "signal_key": "{signal_key}",
  "validation_status": "confirmed|upgraded|downgraded|stale|irrelevant",
  "adjusted_significance": "high|medium|low|none",
  "reasoning": "your explanation of the validation judgment",
  "key_facts": ["list of key facts that informed your judgment"],
  "cross_references": ["list of cross-references found"]
}}"""


def build_signal_validation_prompt(context: dict) -> str:
    """Build the Pass 2 prompt from signal context.

    Args:
        context: Dict with keys: pidn, signal, parcel, entity,
                 tax_claims, proceedings, neighbors, corporate.
    """
    signal = context["signal"]
    signal_key = signal.get("signal_key", "unknown")
    template = SIGNAL_TEMPLATES.get(signal_key, {"base_questions": ["Validate this signal."], "conditional_questions": {}})

    # Build questions list
    questions = list(template["base_questions"])
    conditionals = template.get("conditional_questions", {})

    if context.get("proceedings") and "has_proceedings" in conditionals:
        questions.append(conditionals["has_proceedings"])
    if context.get("corporate") and "has_corporate" in conditionals:
        questions.append(conditionals["has_corporate"])
    if context.get("neighbors") and "has_neighbors" in conditionals:
        questions.append(conditionals["has_neighbors"])
    if context.get("portfolio") and "has_portfolio" in conditionals:
        questions.append(conditionals["has_portfolio"])

    # Build optional sections
    optional_parts = []
    if context.get("tax_claims"):
        lines = ["TAX CLAIMS:"]
        for tc in context["tax_claims"]:
            lines.append(f"- {tc.get('authority', '?')} {tc.get('year', '?')}: ${tc.get('amount', 0):,.0f}")
        optional_parts.append("\n".join(lines))
    if context.get("proceedings"):
        lines = ["PROCEEDINGS:"]
        for p in context["proceedings"]:
            lines.append(f"- {p.get('type', '?')} by {p.get('applicant', '?')} | Decision: {p.get('decision', '?')} | {p.get('meeting_date', '?')}")
        optional_parts.append("\n".join(lines))
    if context.get("neighbors"):
        lines = ["ADJACENT PARCELS:"]
        for n in context["neighbors"]:
            lines.append(f"- {n.get('pidn', '?')} | Owner: {n.get('owner', '?')} | Owed: ${n.get('total_owed', 0):,.0f}")
        optional_parts.append("\n".join(lines))
    if context.get("corporate"):
        lines = ["CORPORATE RECORDS:"]
        for c in context["corporate"]:
            lines.append(f"- {c.get('entity_name', '?')} | Status: {c.get('status', '?')} | Office: {c.get('office_address', '?')}")
        optional_parts.append("\n".join(lines))
    if context.get("portfolio"):
        lines = [f"OWNER PORTFOLIO ({len(context['portfolio'])} other parcels):"]
        for p in context["portfolio"][:5]:
            lines.append(f"- {p.get('pidn', '?')} | {p.get('address', '?')} | ${p.get('assessed_value', 0):,}")
        optional_parts.append("\n".join(lines))

    # Format evidence
    evidence = signal.get("evidence", {})
    evidence_lines = [f"- {k}: {v}" for k, v in evidence.items()]
    if signal.get("distance_m") is not None:
        evidence_lines.append(f"- distance: {signal['distance_m']:.0f}m")

    parcel = context.get("parcel", {})
    parcel_lines = [
        f"PIDN: {parcel.get('pidn', '?')}",
        f"Owner: {parcel.get('owner', '?')}",
        f"Address: {parcel.get('address', '?')}",
        f"Municipality: {parcel.get('municipality', '?')}",
        f"Acres: {parcel.get('acres', '?')}",
        f"Class: {parcel.get('property_class', '?')}",
        f"Assessed: ${parcel.get('assessed_value', 0):,}",
    ]

    entity = context.get("entity", {})
    if entity.get("found"):
        entity_lines = [
            f"Name: {entity.get('canonical_name', '?')}",
            f"Type: {entity.get('entity_type', '?')}",
            f"Linked names: {', '.join(entity.get('linked_names', []))}",
        ]
    else:
        entity_lines = ["No entity resolution data available."]

    return SIGNAL_VALIDATION_PROMPT.format(
        signal_key=signal_key,
        evidence_section="\n".join(evidence_lines),
        parcel_section="\n".join(parcel_lines),
        entity_section="\n".join(entity_lines),
        optional_sections="\n\n".join(optional_parts),
        questions_section="\n".join(f"{i+1}. {q}" for i, q in enumerate(questions)),
    )


def gather_signal_context(cursor, pidn: str, signal: dict) -> dict:
    """Gather all context needed for signal validation.

    Args:
        cursor: Database cursor (must be RealDictCursor or return dicts).
        pidn: Parcel identifier.
        signal: Raw signal dict from public.development_signals.

    Returns:
        Dict with all context needed by build_signal_validation_prompt.
    """
    # Parcel fundamentals
    cursor.execute(PARCEL_QUERY, {"pidn": pidn})
    parcel_row = cursor.fetchone()
    parcel = format_parcel_context(dict(parcel_row)) if parcel_row else {}

    # Entity graph
    owner_name = parcel.get("owner", "")
    cursor.execute(ENTITY_GRAPH_QUERY, {"name": owner_name})
    entity_row = cursor.fetchone()
    entity = format_entity_context(dict(entity_row) if entity_row else None)

    # Tax claims
    cursor.execute(TAX_CLAIMS_QUERY, {"pidn": pidn})
    tax_claims = format_tax_claims_context([dict(r) for r in cursor.fetchall()])

    # Proceedings for this parcel or entity
    linked_names = entity.get("linked_names", [owner_name]) if entity.get("found") else [owner_name]
    cursor.execute(PROCEEDINGS_FOR_PARCEL_QUERY, {"pidn": pidn})
    parcel_procs = cursor.fetchall()
    cursor.execute(PROCEEDINGS_FOR_ENTITY_QUERY, {"names": linked_names})
    entity_procs = cursor.fetchall()
    all_procs = list({p[0]: p for p in [*parcel_procs, *entity_procs]}.values())  # dedupe
    proceedings = format_proceedings_context([dict(r) for r in all_procs])

    # Adjacent parcels
    cursor.execute(NEIGHBORS_QUERY, {"pidn": pidn})
    neighbors = format_neighbors_context([dict(r) for r in cursor.fetchall()])

    # Corporate records (if owner is business)
    corporate = []
    if entity.get("entity_type") == "business" or any(
        kw in owner_name.upper() for kw in ["LLC", "INC", "CORP", "LP", "LTD"]
    ):
        cursor.execute(CORPORATE_FOR_NAMES_QUERY, {"names": linked_names})
        corporate = format_corporate_context([dict(r) for r in cursor.fetchall()])

    # Portfolio
    portfolio = []
    if entity.get("found") and len(linked_names) > 0:
        cursor.execute(PORTFOLIO_QUERY, {"names": linked_names})
        portfolio = format_portfolio_context([dict(r) for r in cursor.fetchall()])

    return {
        "pidn": pidn,
        "signal": signal,
        "parcel": parcel,
        "entity": entity,
        "tax_claims": tax_claims,
        "proceedings": proceedings,
        "neighbors": neighbors,
        "corporate": corporate,
        "portfolio": portfolio,
    }


def parse_signal_validation_output(output: dict) -> dict:
    """Validate and normalize the LLM's signal validation output."""
    if "reasoning" not in output and "validation_status" not in output:
        return {"error": "Missing required fields in LLM output"}

    status = output.get("validation_status", "confirmed")
    if status not in VALID_STATUSES:
        status = "confirmed"

    significance = output.get("adjusted_significance", "medium")
    if significance not in VALID_SIGNIFICANCE:
        significance = "medium"

    return {
        "signal_key": output.get("signal_key", ""),
        "validation_status": status,
        "adjusted_significance": significance,
        "reasoning": output.get("reasoning", ""),
        "key_facts": output.get("key_facts", []),
        "cross_references": output.get("cross_references", []),
    }
```

- [ ] **Step 5: Run tests**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_pass2_signals.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Write the Pass 2 Dagster asset**

```python
# pipelines/countyiq/assets/enrichment/signal_validation.py
"""Pass 2: Signal Validation — Dagster asset.

For each signal on each parcel, gathers context via SQL and sends
to the LLM for validation. Results stored in public.evidence.
"""
import os
import json
from dagster import asset, AssetExecutionContext, MaterializeResult, MetadataValue

from countyiq.lib.pass2_signal_validation import (
    gather_signal_context,
    build_signal_validation_prompt,
    parse_signal_validation_output,
)
from countyiq.lib.intelligence_common import compute_input_hash
from countyiq.resources.database import DatabaseResource

MODEL_PATH = os.environ.get("COUNTYIQ_TEXT_MODEL", "")


@asset(
    group_name="enrichment",
    deps=["entity_verification", "development_signals"],
    description="Pass 2: validate each signal on each parcel via LLM reasoning",
    kinds={"postgres", "llm"},
)
def signal_validation(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    if not MODEL_PATH:
        context.log.warning("COUNTYIQ_TEXT_MODEL not set — skipping Pass 2")
        return MaterializeResult(metadata={"status": MetadataValue.text("skipped")})

    from countyiq.lib.llm_harness import HarnessConfig, invoke_with_retry

    config = HarnessConfig(
        model_path=MODEL_PATH,
        n_ctx=4096,
        n_gpu_layers=int(os.environ.get("COUNTYIQ_GPU_LAYERS", "-1")),
        temperature=0.1,
        max_tokens=1024,
    )

    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        # Get all signals that need validation
        cur.execute("""
            SELECT ds.pidn, ds.signal_key, ds.signal_weight,
                   ds.source_table, ds.source_id, ds.distance_m, ds.evidence
            FROM public.development_signals ds
            LEFT JOIN public.evidence e
              ON ds.pidn = e.pidn AND ds.signal_key = e.signal_key
            WHERE e.id IS NULL
            ORDER BY ds.pidn
        """)
        signals = [dict(row) for row in cur.fetchall()]
        context.log.info(f"Found {len(signals)} signals to validate")

        validated = 0
        errors = 0
        skipped = 0

        for i, signal in enumerate(signals):
            pidn = signal["pidn"]
            signal_key = signal["signal_key"]

            # Check input hash for incremental processing
            input_data = {"pidn": pidn, "signal": signal}
            input_hash = compute_input_hash(input_data)

            cur.execute("""
                SELECT input_hash FROM meta.intelligence_passes
                WHERE pidn = %(pidn)s AND pass_number = 2
                  AND status = 'complete' AND input_hash = %(hash)s
            """, {"pidn": pidn, "hash": input_hash})

            if cur.fetchone():
                skipped += 1
                continue

            try:
                # Gather context
                signal_context = gather_signal_context(cur, pidn, signal)

                # Build prompt
                prompt = build_signal_validation_prompt(signal_context)

                # Invoke LLM
                result = invoke_with_retry(config, prompt, retries=1)

                if not result.success:
                    context.log.warning(f"Pass 2 failed for {pidn}/{signal_key}: {result.error}")
                    errors += 1
                    continue

                parsed = parse_signal_validation_output(result.parsed)

                if parsed.get("error"):
                    context.log.warning(f"Parse error for {pidn}/{signal_key}: {parsed['error']}")
                    errors += 1
                    continue

                # Upsert to public.evidence
                cur.execute("""
                    INSERT INTO public.evidence
                        (pidn, signal_key, claim, evidence_data, source_url,
                         internal_url, validation_status, adjusted_significance,
                         validation_reasoning, cross_references, validated_at)
                    VALUES (%(pidn)s, %(key)s, %(claim)s, %(data)s, %(src)s,
                            %(int_url)s, %(status)s, %(sig)s,
                            %(reasoning)s, %(xref)s, NOW())
                    ON CONFLICT (pidn, signal_key) DO UPDATE SET
                        validation_status = EXCLUDED.validation_status,
                        adjusted_significance = EXCLUDED.adjusted_significance,
                        validation_reasoning = EXCLUDED.validation_reasoning,
                        cross_references = EXCLUDED.cross_references,
                        validated_at = NOW()
                """, {
                    "pidn": pidn,
                    "key": signal_key,
                    "claim": "; ".join(parsed.get("key_facts", [])),
                    "data": json.dumps(signal.get("evidence", {})),
                    "src": signal_context.get("parcel", {}).get("source_url", ""),
                    "int_url": f"/property/{pidn}",
                    "status": parsed["validation_status"],
                    "sig": parsed["adjusted_significance"],
                    "reasoning": parsed["reasoning"],
                    "xref": json.dumps(parsed.get("cross_references", [])),
                })
                validated += 1
                conn.commit()

            except Exception as e:
                context.log.warning(f"Error validating {pidn}/{signal_key}: {e}")
                conn.rollback()
                errors += 1

            if (i + 1) % 200 == 0:
                context.log.info(f"Processed {i + 1}/{len(signals)} signals ({validated} validated, {errors} errors)")

    finally:
        if was_autocommit:
            conn.autocommit = True
        cur.close()

    return MaterializeResult(metadata={
        "signals_total": MetadataValue.int(len(signals)),
        "validated": MetadataValue.int(validated),
        "skipped": MetadataValue.int(skipped),
        "errors": MetadataValue.int(errors),
    })
```

- [ ] **Step 7: Verify asset loads**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "from countyiq.assets.enrichment.signal_validation import signal_validation; print('OK')"
```

- [ ] **Step 8: Commit**

```bash
git add pipelines/countyiq/lib/pass2_signal_validation.py pipelines/countyiq/assets/enrichment/signal_validation.py pipelines/tests/test_pass2_signals.py pipelines/tests/fixtures/signal_context_sample.json
git commit -m "feat: Pass 2 signal validation — templates for 13 signal types + Dagster asset"
```

---

### Task 4: Pass 3 — Brief Generation

**Files:**
- Create: `pipelines/countyiq/lib/pass3_brief_generation.py`
- Create: `pipelines/countyiq/assets/enrichment/brief_generation.py`
- Create: `pipelines/tests/test_pass3_briefs.py`
- Create: `pipelines/tests/fixtures/validated_signals_sample.json`

Pass 3 synthesizes validated signals into an intelligence brief. Only parcels with at least one medium or high significance validated signal get a brief.

- [ ] **Step 1: Create test fixture**

```json
// pipelines/tests/fixtures/validated_signals_sample.json
{
  "pidn": "4500112340000",
  "parcel": {
    "pidn": "4500112340000",
    "owner": "SMITH JOHN A",
    "address": "1520 MOUNT ROSE AVE",
    "assessed_value": 185000,
    "acres": 4.2,
    "property_class": "C",
    "municipality": "West Manchester Township",
    "source_url": "https://example.com/parcels"
  },
  "entity": {
    "found": true,
    "canonical_name": "SMITH JOHN A",
    "entity_type": "person",
    "linked_names": ["SMITH JOHN A", "J A SMITH HOLDINGS LLC"],
    "relationships": [{"related_entity": "J A SMITH HOLDINGS LLC", "relationship": "owner_of"}]
  },
  "portfolio_count": 4,
  "portfolio_value": 520000,
  "portfolio_delinquency": 41200,
  "validated_signals": [
    {
      "signal_key": "active_subdivision",
      "validation_status": "confirmed",
      "adjusted_significance": "high",
      "reasoning": "48-lot land development filed 5 months ago, 180m away.",
      "key_facts": ["48-lot land development", "filed 5 months ago", "180m away"],
      "cross_references": ["ZHB approval 2025-12-03"],
      "source_url": "https://example.com/subdivisions",
      "internal_url": "/property/4500112340000"
    },
    {
      "signal_key": "zoning_mismatch",
      "validation_status": "confirmed",
      "adjusted_significance": "medium",
      "reasoning": "R-1 vs General Commercial — real upzone signal.",
      "key_facts": ["R-1 to General Commercial"],
      "cross_references": [],
      "source_url": "https://example.com/zoning",
      "internal_url": "/property/4500112340000"
    },
    {
      "signal_key": "flood_zone",
      "validation_status": "confirmed",
      "adjusted_significance": "low",
      "reasoning": "Eastern 0.8 acres in SFHA Zone AE.",
      "key_facts": ["0.8 acres in SFHA Zone AE"],
      "cross_references": [],
      "source_url": "https://example.com/fema",
      "internal_url": "/property/4500112340000"
    }
  ]
}
```

- [ ] **Step 2: Write failing tests**

```python
# pipelines/tests/test_pass3_briefs.py
"""Tests for Pass 3: Brief Generation context and templates."""
import json
import os
import pytest
from countyiq.lib.pass3_brief_generation import (
    BRIEF_GENERATION_TEMPLATE,
    build_brief_generation_prompt,
    parse_brief_output,
    should_generate_brief,
)


@pytest.fixture
def sample_context():
    fixture_path = os.path.join(
        os.path.dirname(__file__), "fixtures", "validated_signals_sample.json"
    )
    with open(fixture_path) as f:
        return json.load(f)


class TestShouldGenerateBrief:
    def test_yes_with_high_signal(self, sample_context):
        assert should_generate_brief(sample_context["validated_signals"]) is True

    def test_no_with_all_low_signals(self):
        signals = [{"adjusted_significance": "low"}, {"adjusted_significance": "none"}]
        assert should_generate_brief(signals) is False

    def test_no_with_empty_signals(self):
        assert should_generate_brief([]) is False

    def test_yes_with_medium_signal(self):
        signals = [{"adjusted_significance": "medium"}]
        assert should_generate_brief(signals) is True


class TestBuildBriefGenerationPrompt:
    def test_returns_string(self, sample_context):
        prompt = build_brief_generation_prompt(sample_context)
        assert isinstance(prompt, str)

    def test_includes_parcel_info(self, sample_context):
        prompt = build_brief_generation_prompt(sample_context)
        assert "4500112340000" in prompt
        assert "SMITH JOHN A" in prompt

    def test_includes_validated_signals(self, sample_context):
        prompt = build_brief_generation_prompt(sample_context)
        assert "active_subdivision" in prompt
        assert "confirmed" in prompt

    def test_includes_citation_constraint(self, sample_context):
        prompt = build_brief_generation_prompt(sample_context)
        assert "[Signal:" in prompt or "signal_key" in prompt

    def test_includes_assessment_categories(self, sample_context):
        prompt = build_brief_generation_prompt(sample_context)
        assert "strong_opportunity" in prompt
        assert "not_actionable" in prompt


class TestParseBriefOutput:
    def test_valid_output(self):
        output = {
            "brief": "This parcel has strong development signals.",
            "assessment": "strong_opportunity",
            "assessment_reasoning": "Multiple high signals converging.",
            "key_questions": ["Verify stormwater capacity"],
            "citations": [
                {"claim": "48-lot development", "signal_key": "active_subdivision"}
            ],
        }
        result = parse_brief_output(output)
        assert result["assessment"] == "strong_opportunity"
        assert result["brief_text"] == "This parcel has strong development signals."
        assert len(result["key_questions"]) == 1

    def test_invalid_assessment_defaults(self):
        output = {"brief": "text", "assessment": "AMAZING", "assessment_reasoning": "r"}
        result = parse_brief_output(output)
        assert result["assessment"] == "speculative"  # default

    def test_missing_brief_returns_error(self):
        output = {"assessment": "emerging"}
        result = parse_brief_output(output)
        assert result.get("error") is not None


class TestBriefGenerationTemplate:
    def test_template_has_constraints(self):
        assert "CONSTRAINTS" in BRIEF_GENERATION_TEMPLATE
        assert "Do not invent" in BRIEF_GENERATION_TEMPLATE or "do not invent" in BRIEF_GENERATION_TEMPLATE.lower()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_pass3_briefs.py -v
```

- [ ] **Step 4: Write implementation**

```python
# pipelines/countyiq/lib/pass3_brief_generation.py
"""Pass 3: Brief Generation — context gatherer, template, and output parser.

Synthesizes validated signals into an intelligence brief that a
developer can act on. Only runs for parcels with at least one
medium or high significance validated signal.
"""

VALID_ASSESSMENTS = {
    "strong_opportunity", "emerging", "speculative", "constrained", "not_actionable"
}


BRIEF_GENERATION_TEMPLATE = """You are writing an intelligence brief for a real estate professional about a specific parcel in York County, PA.

PARCEL:
- PIDN: {pidn}
- Address: {address}
- Owner: {owner} ({entity_type})
- Municipality: {municipality}
- Acreage: {acres}
- Property Class: {property_class}
- Assessed Value: ${assessed_value:,}
- Last Sale: {sale_date} for ${sale_price:,}

ENTITY PROFILE:
{entity_summary}

VALIDATED SIGNALS:
{signals_section}

CONSTRAINTS:
1. Every factual claim in your brief MUST reference a specific signal above using [Signal: signal_key] notation.
2. Do not invent market values, projections, timelines, or comparables. You do not have market data.
3. Do not give legal or financial advice. State observations and let the reader draw conclusions.
4. If signals conflict (e.g., development pressure but flood zone constraint), address the tension directly.

TASKS:

1. NARRATIVE BRIEF (2-4 paragraphs):
   Write a clear, professional intelligence brief that:
   - Opens with the single most important thing about this parcel
   - Explains what's happening (activity signals)
   - Explains the opportunity or risk (what the signals mean together)
   - Notes constraints or risks that qualify the opportunity
   - Every sentence with a factual claim includes [Signal: signal_key] citation

2. ASSESSMENT:
   Classify as one of: strong_opportunity, emerging, speculative, constrained, not_actionable
   Explain in 1-2 sentences.

3. KEY QUESTIONS:
   List 2-3 things a developer should verify before acting — information you DON'T have.

OUTPUT FORMAT:
{{
  "brief": "The narrative text with [Signal: key] citations...",
  "assessment": "strong_opportunity|emerging|speculative|constrained|not_actionable",
  "assessment_reasoning": "Why this assessment...",
  "key_questions": ["question 1", "question 2"],
  "citations": [
    {{
      "claim": "the specific claim text",
      "signal_key": "which signal supports it"
    }}
  ]
}}"""


def should_generate_brief(validated_signals: list[dict]) -> bool:
    """Check if a parcel has enough validated signals to warrant a brief."""
    return any(
        s.get("adjusted_significance") in ("high", "medium")
        for s in validated_signals
    )


def build_brief_generation_prompt(context: dict) -> str:
    """Build the Pass 3 prompt from validated signal context.

    Args:
        context: Dict with keys: pidn, parcel, entity, portfolio_count,
                 portfolio_value, portfolio_delinquency, validated_signals.
    """
    parcel = context.get("parcel", {})
    entity = context.get("entity", {})

    # Entity summary
    entity_parts = []
    if entity.get("found"):
        entity_parts.append(f"Canonical name: {entity.get('canonical_name', '?')}")
        entity_parts.append(f"Type: {entity.get('entity_type', '?')}")
        if entity.get("linked_names"):
            entity_parts.append(f"Also known as: {', '.join(entity['linked_names'])}")
        if entity.get("relationships"):
            for rel in entity["relationships"]:
                entity_parts.append(
                    f"Relationship: {rel.get('relationship', '?')} → {rel.get('related_entity', '?')}"
                )
    entity_parts.append(
        f"Portfolio: {context.get('portfolio_count', '?')} parcels, "
        f"${context.get('portfolio_value', 0):,} assessed, "
        f"${context.get('portfolio_delinquency', 0):,} delinquent"
    )
    entity_summary = "\n".join(entity_parts)

    # Validated signals
    signal_lines = []
    for sig in context.get("validated_signals", []):
        signal_lines.append("---")
        signal_lines.append(f"Signal: {sig.get('signal_key', '?')}")
        signal_lines.append(f"Status: {sig.get('validation_status', '?')} (significance: {sig.get('adjusted_significance', '?')})")
        signal_lines.append(f"Reasoning: {sig.get('reasoning', '?')}")
        if sig.get("key_facts"):
            signal_lines.append(f"Key Facts: {', '.join(sig['key_facts'])}")
        if sig.get("cross_references"):
            signal_lines.append(f"Cross-References: {', '.join(sig['cross_references'])}")
        signal_lines.append(f"Source: {sig.get('source_url', '?')}")
        signal_lines.append(f"Internal: {sig.get('internal_url', '?')}")
    signals_section = "\n".join(signal_lines) if signal_lines else "(no validated signals)"

    return BRIEF_GENERATION_TEMPLATE.format(
        pidn=parcel.get("pidn", "?"),
        address=parcel.get("address", "?"),
        owner=parcel.get("owner", "?"),
        entity_type=entity.get("entity_type", "unknown"),
        municipality=parcel.get("municipality", "?"),
        acres=parcel.get("acres", "?"),
        property_class=parcel.get("property_class", "?"),
        assessed_value=parcel.get("assessed_value", 0),
        sale_date=parcel.get("sale_date", "?"),
        sale_price=parcel.get("sale_price", 0),
        entity_summary=entity_summary,
        signals_section=signals_section,
    )


def gather_brief_context(cursor, pidn: str) -> dict:
    """Gather all context needed for brief generation.

    Args:
        cursor: Database cursor.
        pidn: Parcel identifier.

    Returns:
        Dict with all context needed by build_brief_generation_prompt.
    """
    from countyiq.lib.intelligence_common import (
        PARCEL_QUERY, ENTITY_GRAPH_QUERY, PORTFOLIO_QUERY,
        format_parcel_context, format_entity_context,
    )

    # Parcel
    cursor.execute(PARCEL_QUERY, {"pidn": pidn})
    parcel_row = cursor.fetchone()
    parcel = format_parcel_context(dict(parcel_row)) if parcel_row else {}

    # Entity
    owner_name = parcel.get("owner", "")
    cursor.execute(ENTITY_GRAPH_QUERY, {"name": owner_name})
    entity_row = cursor.fetchone()
    entity = format_entity_context(dict(entity_row) if entity_row else None)

    # Portfolio stats
    linked_names = entity.get("linked_names", [owner_name]) if entity.get("found") else [owner_name]
    cursor.execute(PORTFOLIO_QUERY, {"names": linked_names})
    portfolio_rows = cursor.fetchall()
    portfolio_count = len(portfolio_rows)
    portfolio_value = sum(r.get("aprtotal", 0) or 0 for r in portfolio_rows)

    cursor.execute("""
        SELECT COALESCE(SUM(total), 0) as total_owed
        FROM staging.tax_claims
        WHERE pidn = ANY(%(pidns)s) AND valid_to IS NULL
    """, {"pidns": [r.get("pidn") for r in portfolio_rows]})
    delinquency_row = cursor.fetchone()
    portfolio_delinquency = delinquency_row.get("total_owed", 0) if delinquency_row else 0

    # Validated signals
    cursor.execute("""
        SELECT signal_key, validation_status, adjusted_significance,
               validation_reasoning, claim, cross_references,
               source_url, internal_url
        FROM public.evidence
        WHERE pidn = %(pidn)s
          AND validation_status != 'irrelevant'
        ORDER BY
          CASE adjusted_significance
            WHEN 'high' THEN 1 WHEN 'medium' THEN 2
            WHEN 'low' THEN 3 ELSE 4
          END
    """, {"pidn": pidn})
    signals = []
    for row in cursor.fetchall():
        r = dict(row)
        signals.append({
            "signal_key": r.get("signal_key", ""),
            "validation_status": r.get("validation_status", ""),
            "adjusted_significance": r.get("adjusted_significance", ""),
            "reasoning": r.get("validation_reasoning", ""),
            "key_facts": r.get("claim", "").split("; ") if r.get("claim") else [],
            "cross_references": r.get("cross_references") or [],
            "source_url": r.get("source_url", ""),
            "internal_url": r.get("internal_url", ""),
        })

    return {
        "pidn": pidn,
        "parcel": parcel,
        "entity": entity,
        "portfolio_count": portfolio_count,
        "portfolio_value": portfolio_value,
        "portfolio_delinquency": portfolio_delinquency,
        "validated_signals": signals,
    }


def parse_brief_output(output: dict) -> dict:
    """Validate and normalize the LLM's brief generation output."""
    if "brief" not in output:
        return {"error": "Missing 'brief' key in LLM output"}

    assessment = output.get("assessment", "speculative")
    if assessment not in VALID_ASSESSMENTS:
        assessment = "speculative"

    return {
        "brief_text": output["brief"],
        "assessment": assessment,
        "assessment_reasoning": output.get("assessment_reasoning", ""),
        "key_questions": output.get("key_questions", []),
        "citations": output.get("citations", []),
    }
```

- [ ] **Step 5: Run tests**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_pass3_briefs.py -v
```

- [ ] **Step 6: Write the Pass 3 Dagster asset**

```python
# pipelines/countyiq/assets/enrichment/brief_generation.py
"""Pass 3: Brief Generation — Dagster asset.

Synthesizes validated signals into intelligence briefs.
Only generates briefs for parcels with medium+ validated signals.
"""
import os
import json
from dagster import asset, AssetExecutionContext, MaterializeResult, MetadataValue

from countyiq.lib.pass3_brief_generation import (
    gather_brief_context,
    build_brief_generation_prompt,
    parse_brief_output,
    should_generate_brief,
)
from countyiq.resources.database import DatabaseResource

MODEL_PATH = os.environ.get("COUNTYIQ_TEXT_MODEL", "")


@asset(
    group_name="enrichment",
    deps=["signal_validation"],
    description="Pass 3: generate intelligence briefs from validated signals",
    kinds={"postgres", "llm"},
)
def brief_generation(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    if not MODEL_PATH:
        context.log.warning("COUNTYIQ_TEXT_MODEL not set — skipping Pass 3")
        return MaterializeResult(metadata={"status": MetadataValue.text("skipped")})

    from countyiq.lib.llm_harness import HarnessConfig, invoke_with_retry

    config = HarnessConfig(
        model_path=MODEL_PATH,
        n_ctx=4096,
        n_gpu_layers=int(os.environ.get("COUNTYIQ_GPU_LAYERS", "-1")),
        temperature=0.2,
        max_tokens=2048,
    )

    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        # Find parcels with validated signals but no brief yet
        cur.execute("""
            SELECT DISTINCT e.pidn
            FROM public.evidence e
            LEFT JOIN public.parcel_briefs pb ON e.pidn = pb.pidn
            WHERE e.adjusted_significance IN ('high', 'medium')
              AND pb.pidn IS NULL
        """)
        pidns = [row[0] for row in cur.fetchall()]
        context.log.info(f"Found {len(pidns)} parcels needing briefs")

        briefs_created = 0
        skipped = 0
        errors = 0

        for i, pidn in enumerate(pidns):
            try:
                brief_context = gather_brief_context(cur, pidn)

                if not should_generate_brief(brief_context["validated_signals"]):
                    skipped += 1
                    continue

                prompt = build_brief_generation_prompt(brief_context)
                result = invoke_with_retry(config, prompt, retries=1)

                if not result.success:
                    context.log.warning(f"Pass 3 failed for {pidn}: {result.error}")
                    errors += 1
                    continue

                parsed = parse_brief_output(result.parsed)

                if parsed.get("error"):
                    context.log.warning(f"Parse error for {pidn}: {parsed['error']}")
                    errors += 1
                    continue

                cur.execute("""
                    INSERT INTO public.parcel_briefs
                        (pidn, brief_text, assessment, assessment_reasoning,
                         key_questions, signal_count, citations,
                         brief_version, generated_at, pass_metadata)
                    VALUES (%(pidn)s, %(text)s, %(assessment)s, %(reasoning)s,
                            %(questions)s, %(count)s, %(citations)s,
                            1, NOW(), %(meta)s)
                    ON CONFLICT (pidn) DO UPDATE SET
                        brief_text = EXCLUDED.brief_text,
                        assessment = EXCLUDED.assessment,
                        assessment_reasoning = EXCLUDED.assessment_reasoning,
                        key_questions = EXCLUDED.key_questions,
                        signal_count = EXCLUDED.signal_count,
                        citations = EXCLUDED.citations,
                        brief_version = public.parcel_briefs.brief_version + 1,
                        generated_at = NOW(),
                        pass_metadata = EXCLUDED.pass_metadata
                """, {
                    "pidn": pidn,
                    "text": parsed["brief_text"],
                    "assessment": parsed["assessment"],
                    "reasoning": parsed["assessment_reasoning"],
                    "questions": parsed["key_questions"],
                    "count": len(brief_context["validated_signals"]),
                    "citations": json.dumps(parsed["citations"]),
                    "meta": json.dumps({
                        "model": os.path.basename(MODEL_PATH),
                        "pass_versions": {"pass1": 1, "pass2": 1, "pass3": 1},
                    }),
                })
                briefs_created += 1
                conn.commit()

            except Exception as e:
                context.log.warning(f"Error generating brief for {pidn}: {e}")
                conn.rollback()
                errors += 1

            if (i + 1) % 50 == 0:
                context.log.info(f"Processed {i + 1}/{len(pidns)} parcels")

    finally:
        if was_autocommit:
            conn.autocommit = True
        cur.close()

    return MaterializeResult(metadata={
        "parcels_eligible": MetadataValue.int(len(pidns)),
        "briefs_created": MetadataValue.int(briefs_created),
        "skipped": MetadataValue.int(skipped),
        "errors": MetadataValue.int(errors),
    })
```

- [ ] **Step 7: Verify asset loads and commit**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "from countyiq.assets.enrichment.brief_generation import brief_generation; print('OK')"
git add pipelines/countyiq/lib/pass3_brief_generation.py pipelines/countyiq/assets/enrichment/brief_generation.py pipelines/tests/test_pass3_briefs.py pipelines/tests/fixtures/validated_signals_sample.json
git commit -m "feat: Pass 3 brief generation — template, context gatherer, and Dagster asset"
```

---

### Task 5: Pass 4 — County Narratives

**Files:**
- Create: `pipelines/countyiq/lib/pass4_county_narratives.py`
- Create: `pipelines/countyiq/assets/enrichment/county_narratives.py`
- Create: `pipelines/tests/test_pass4_narratives.py`

Pass 4 detects cross-parcel patterns via 4 scans: corridor activity, owner portfolio, municipal trends, distress migration. Each scan has its own SQL + prompt template.

This task follows the same pattern as Tasks 2-4 but with 4 scan types instead of 1. The context-gathering SQL for each scan was detailed in the spec (Section: Pass 4 County Narratives).

- [ ] **Step 1: Write failing tests**

```python
# pipelines/tests/test_pass4_narratives.py
"""Tests for Pass 4: County Narratives scan functions and templates."""
import pytest
from countyiq.lib.pass4_county_narratives import (
    CORRIDOR_TEMPLATE,
    PORTFOLIO_TEMPLATE,
    MUNICIPAL_TEMPLATE,
    DISTRESS_TEMPLATE,
    build_corridor_prompt,
    build_portfolio_prompt,
    build_municipal_prompt,
    build_distress_prompt,
    parse_narrative_output,
)


class TestCorridorTemplate:
    def test_template_has_required_sections(self):
        assert "corridor" in CORRIDOR_TEMPLATE.lower()
        assert "TASKS" in CORRIDOR_TEMPLATE
        assert "OUTPUT FORMAT" in CORRIDOR_TEMPLATE

    def test_build_prompt_returns_string(self):
        cluster = {
            "signal_key": "active_subdivision",
            "cluster_size": 5,
            "municipality": "West Manchester Township",
            "parcels": [
                {"pidn": "123", "address": "100 Main St", "assessment": "emerging", "brief_excerpt": "Active subdivision nearby."},
            ],
            "proceedings": [],
        }
        prompt = build_corridor_prompt(cluster)
        assert isinstance(prompt, str)
        assert "West Manchester" in prompt
        assert "active_subdivision" in prompt


class TestPortfolioTemplate:
    def test_template_has_required_sections(self):
        assert "portfolio" in PORTFOLIO_TEMPLATE.lower() or "entity" in PORTFOLIO_TEMPLATE.lower()
        assert "OUTPUT FORMAT" in PORTFOLIO_TEMPLATE

    def test_build_prompt_returns_string(self):
        portfolio = {
            "canonical_name": "SMITH HOLDINGS LLC",
            "entity_type": "business",
            "relationships": [],
            "briefed_parcels": 5,
            "municipalities": 3,
            "total_acres": 22.0,
            "parcels": [
                {"pidn": "123", "address": "100 Main", "municipality": "York", "assessment": "emerging", "brief_excerpt": "Tax distress."},
            ],
            "deeds": [],
        }
        prompt = build_portfolio_prompt(portfolio)
        assert isinstance(prompt, str)
        assert "SMITH HOLDINGS" in prompt


class TestMunicipalTemplate:
    def test_template_has_required_sections(self):
        assert "OUTPUT FORMAT" in MUNICIPAL_TEMPLATE

    def test_build_prompt_returns_string(self):
        data = {
            "municipality": "West Manchester Township",
            "assessment_distribution": {"strong_opportunity": 5, "emerging": 12},
            "signal_distribution": {"active_subdivision": 8, "tax_distress": 15},
            "zhb_decisions": [],
            "distress_summary": {"delinquent_parcels": 45, "total_owed": 120000, "oldest_year": 2019},
        }
        prompt = build_municipal_prompt(data)
        assert isinstance(prompt, str)
        assert "West Manchester" in prompt


class TestDistressTemplate:
    def test_template_has_required_sections(self):
        assert "OUTPUT FORMAT" in DISTRESS_TEMPLATE

    def test_build_prompt_returns_string(self):
        data = {
            "changes": [
                {
                    "municipality": "York City",
                    "school_district": "York City SD",
                    "current_delinquent": 150, "current_owed": 500000,
                    "prior_delinquent": 130, "prior_owed": 420000,
                    "parcel_delta": 20, "owed_delta": 80000,
                },
            ],
        }
        prompt = build_distress_prompt(data)
        assert isinstance(prompt, str)
        assert "York City" in prompt


class TestParseNarrativeOutput:
    def test_valid_output(self):
        output = {
            "title": "Route 30 Corridor Heating Up",
            "narrative": "Five parcels along Route 30...",
            "narrative_type": "corridor",
            "trajectory": "accelerating",
            "affected_pidns": ["123", "456"],
            "key_entities": ["SMITH LLC"],
            "citations": [],
        }
        result = parse_narrative_output(output)
        assert result["title"] == "Route 30 Corridor Heating Up"
        assert result["narrative_type"] == "corridor"

    def test_missing_title_returns_error(self):
        output = {"narrative": "text"}
        result = parse_narrative_output(output)
        assert result.get("error") is not None

    def test_invalid_type_defaults(self):
        output = {"title": "t", "narrative": "n", "narrative_type": "INVALID", "trajectory": "x"}
        result = parse_narrative_output(output)
        assert result["narrative_type"] == "corridor"  # default
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_pass4_narratives.py -v
```

- [ ] **Step 3: Write implementation**

Create `pipelines/countyiq/lib/pass4_county_narratives.py` with:

- `CORRIDOR_TEMPLATE` — prompt for corridor activity narratives
- `PORTFOLIO_TEMPLATE` — prompt for owner portfolio narratives
- `MUNICIPAL_TEMPLATE` — prompt for municipal trend narratives
- `DISTRESS_TEMPLATE` — prompt for distress migration narratives
- `build_corridor_prompt(cluster)` — formats corridor scan data into prompt
- `build_portfolio_prompt(portfolio)` — formats portfolio scan data into prompt
- `build_municipal_prompt(data)` — formats municipal scan data into prompt
- `build_distress_prompt(data)` — formats distress scan data into prompt
- `parse_narrative_output(output)` — validates and normalizes LLM narrative output
- SQL query constants for each scan type (corridor clusters, interesting portfolios, municipal aggregates, distress movement)

Each template follows the pattern established in Passes 1-3: structured context section, explicit tasks, JSON output format. Each build function assembles SQL results into the template. The parse function validates output shape.

The SQL queries for each scan were detailed in the spec design doc under "Pass 4: County Narratives — Detailed Harness Design":

- **Corridor scan:** Groups parcels with shared signal types within 500m using ST_DWithin, requires 3+ parcels per cluster
- **Portfolio scan:** Identifies entities with 3+ briefed parcels AND (2+ distressed OR 2+ recent acquisitions OR 3+ municipalities)
- **Municipal scan:** Per-municipality aggregation of assessment distribution, signal distribution, ZHB decisions, distress summary
- **Distress scan:** Compares current vs 90-day-prior tax distress using SCD Type 2 valid_from/valid_to

The implementation should follow these SQL patterns from the spec but use the established patterns (database.cursor(), dict(row), etc.).

- [ ] **Step 4: Run tests**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_pass4_narratives.py -v
```

- [ ] **Step 5: Write the Pass 4 Dagster asset**

Create `pipelines/countyiq/assets/enrichment/county_narratives.py` following the same pattern as Pass 3's asset:

- Depends on `brief_generation`
- Skips if `COUNTYIQ_TEXT_MODEL` not set
- Runs all 4 scans sequentially
- For each scan result, invokes LLM with the appropriate template
- Stores narratives in `public.county_narratives` with `expires_at = NOW() + INTERVAL '14 days'`
- Returns MaterializeResult with counts per scan type

- [ ] **Step 6: Verify assets load and commit**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "from countyiq.assets.enrichment.county_narratives import county_narratives; print('OK')"
git add pipelines/countyiq/lib/pass4_county_narratives.py pipelines/countyiq/assets/enrichment/county_narratives.py pipelines/tests/test_pass4_narratives.py
git commit -m "feat: Pass 4 county narratives — 4 scan types with templates and Dagster asset"
```

---

### Task 6: Dagster Pipeline Wiring

**Files:**
- Modify: `pipelines/countyiq/jobs/__init__.py`

- [ ] **Step 1: Add intelligence pass jobs**

Add these jobs to `pipelines/countyiq/jobs/__init__.py`:

```python
entity_verification_refresh = define_asset_job(
    name="entity_verification_refresh",
    selection=AssetSelection.assets("entity_verification"),
    description="Pass 1: entity verification across all sources",
)

signal_validation_refresh = define_asset_job(
    name="signal_validation_refresh",
    selection=AssetSelection.assets("signal_validation"),
    description="Pass 2: validate each signal on each parcel",
)

brief_generation_refresh = define_asset_job(
    name="brief_generation_refresh",
    selection=AssetSelection.assets("brief_generation"),
    description="Pass 3: generate intelligence briefs from validated signals",
)

county_narratives_refresh = define_asset_job(
    name="county_narratives_refresh",
    selection=AssetSelection.assets("county_narratives"),
    description="Pass 4: detect cross-parcel patterns and generate county narratives",
)

intelligence_full_pipeline = define_asset_job(
    name="intelligence_full_pipeline",
    selection=AssetSelection.assets(
        "entity_verification", "signal_validation",
        "brief_generation", "county_narratives",
    ),
    description="Full intelligence pipeline: Passes 1-4",
)
```

- [ ] **Step 2: Verify jobs load**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "
from countyiq.jobs import (
    entity_verification_refresh, signal_validation_refresh,
    brief_generation_refresh, county_narratives_refresh,
    intelligence_full_pipeline
)
print('All 5 intelligence pipeline jobs loaded')
"
```

- [ ] **Step 3: Commit**

```bash
git add pipelines/countyiq/jobs/__init__.py
git commit -m "feat: Dagster jobs for intelligence passes 1-4"
```

---

### Task 7: Model Evaluation Framework

**Files:**
- Create: `pipelines/eval/eval_runner.py`
- Create: `pipelines/eval/eval_dataset.sql`
- Create: `pipelines/eval/eval_report.py`

This is the framework for empirically testing different GGUF models against the same prompts and comparing output quality.

- [ ] **Step 1: Create the test dataset extraction SQL**

```sql
-- pipelines/eval/eval_dataset.sql
-- Extract ~100 parcels with diverse signal profiles for model evaluation.
-- Run against Docker Postgres or production to generate the test set.

-- Parcels with 3+ signals (most interesting for brief quality testing)
SELECT pidn, signal_count, top_signal
FROM (
    SELECT ds.pidn,
           COUNT(*) as signal_count,
           MAX(CASE WHEN ds.signal_weight = (
               SELECT MAX(signal_weight) FROM public.development_signals ds2
               WHERE ds2.pidn = ds.pidn
           ) THEN ds.signal_key END) as top_signal
    FROM public.development_signals ds
    GROUP BY ds.pidn
    HAVING COUNT(*) >= 3
    ORDER BY RANDOM()
    LIMIT 50
) multi_signal

UNION ALL

-- Parcels with tax distress signals (for distress validation testing)
SELECT ds.pidn, 1 as signal_count, 'tax_distress' as top_signal
FROM public.development_signals ds
WHERE ds.signal_key = 'tax_distress'
ORDER BY RANDOM()
LIMIT 20

UNION ALL

-- Parcels with exclusion signals (for constraint handling testing)
SELECT ds.pidn, 1 as signal_count, ds.signal_key as top_signal
FROM public.development_signals ds
WHERE ds.signal_key IN ('conservation_easement', 'ag_security')
ORDER BY RANDOM()
LIMIT 10

UNION ALL

-- Parcels with assemblage signals (for cross-parcel testing)
SELECT ds.pidn, 1 as signal_count, 'assemblage' as top_signal
FROM public.development_signals ds
WHERE ds.signal_key = 'assemblage'
ORDER BY RANDOM()
LIMIT 20;
```

- [ ] **Step 2: Create the eval runner**

```python
# pipelines/eval/eval_runner.py
"""Model evaluation runner for CountyIQ intelligence pipeline.

Downloads GGUF models, runs them through the same prompts,
and stores results for comparison.

Usage:
    python eval_runner.py --model /path/to/model.gguf --pass 2 --limit 10
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from countyiq.lib.llm_harness import HarnessConfig, invoke_with_retry
from countyiq.lib.pass2_signal_validation import (
    gather_signal_context,
    build_signal_validation_prompt,
    parse_signal_validation_output,
)
from countyiq.lib.pass3_brief_generation import (
    gather_brief_context,
    build_brief_generation_prompt,
    parse_brief_output,
)
from countyiq.resources.database import make_database_resource


def run_eval(model_path: str, pass_number: int, limit: int, output_dir: str):
    """Run evaluation for a single model on a single pass type."""
    config = HarnessConfig(
        model_path=model_path,
        n_ctx=4096,
        n_gpu_layers=-1,
        temperature=0.1,
        max_tokens=2048,
    )

    db = make_database_resource()
    cur = db.cursor()
    model_name = Path(model_path).stem

    # Get test parcels
    cur.execute("""
        SELECT DISTINCT ds.pidn
        FROM public.development_signals ds
        ORDER BY RANDOM()
        LIMIT %s
    """, (limit,))
    test_pidns = [row[0] for row in cur.fetchall()]

    results = []
    for i, pidn in enumerate(test_pidns):
        print(f"[{i+1}/{len(test_pidns)}] {pidn}...")
        start = time.time()

        try:
            if pass_number == 2:
                # Get signals for this parcel
                cur.execute("""
                    SELECT pidn, signal_key, signal_weight, source_table,
                           source_id, distance_m, evidence
                    FROM public.development_signals
                    WHERE pidn = %s LIMIT 1
                """, (pidn,))
                signal_row = cur.fetchone()
                if not signal_row:
                    continue
                signal = dict(signal_row)
                context = gather_signal_context(cur, pidn, signal)
                prompt = build_signal_validation_prompt(context)
                result = invoke_with_retry(config, prompt, retries=1)
                parsed = parse_signal_validation_output(result.parsed) if result.success else None

            elif pass_number == 3:
                context = gather_brief_context(cur, pidn)
                prompt = build_brief_generation_prompt(context)
                result = invoke_with_retry(config, prompt, retries=1)
                parsed = parse_brief_output(result.parsed) if result.success else None

            elapsed = time.time() - start

            results.append({
                "pidn": pidn,
                "model": model_name,
                "pass": pass_number,
                "success": result.success,
                "elapsed_seconds": round(elapsed, 2),
                "raw_output": result.raw_output[:500],
                "parsed": parsed,
                "error": result.error,
            })

        except Exception as e:
            results.append({
                "pidn": pidn,
                "model": model_name,
                "pass": pass_number,
                "success": False,
                "error": str(e),
            })

    # Save results
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"eval_{model_name}_pass{pass_number}.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Print summary
    successes = sum(1 for r in results if r.get("success"))
    avg_time = sum(r.get("elapsed_seconds", 0) for r in results) / max(len(results), 1)
    print(f"\n--- {model_name} Pass {pass_number} ---")
    print(f"Success: {successes}/{len(results)}")
    print(f"Avg time: {avg_time:.1f}s")
    print(f"Results saved to: {output_file}")

    cur.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate LLM models for CountyIQ")
    parser.add_argument("--model", required=True, help="Path to GGUF model file")
    parser.add_argument("--pass", type=int, required=True, dest="pass_number", help="Pass number (2 or 3)")
    parser.add_argument("--limit", type=int, default=10, help="Number of test parcels")
    parser.add_argument("--output", default="pipelines/eval/results", help="Output directory")
    args = parser.parse_args()

    run_eval(args.model, args.pass_number, args.limit, args.output)
```

- [ ] **Step 3: Create the eval report generator**

```python
# pipelines/eval/eval_report.py
"""Compare evaluation results across models.

Usage:
    python eval_report.py pipelines/eval/results/
"""
import json
import os
import sys
from pathlib import Path


def generate_report(results_dir: str):
    """Compare all eval results in a directory."""
    result_files = sorted(Path(results_dir).glob("eval_*.json"))
    if not result_files:
        print(f"No eval results found in {results_dir}")
        return

    models = {}
    for f in result_files:
        with open(f) as fh:
            results = json.load(fh)
        if not results:
            continue
        model = results[0].get("model", "unknown")
        pass_num = results[0].get("pass", 0)
        key = f"{model}_pass{pass_num}"

        successes = sum(1 for r in results if r.get("success"))
        avg_time = sum(r.get("elapsed_seconds", 0) for r in results) / max(len(results), 1)
        json_valid = sum(1 for r in results if r.get("parsed") is not None)

        models[key] = {
            "model": model,
            "pass": pass_num,
            "total": len(results),
            "successes": successes,
            "success_rate": f"{successes/max(len(results),1)*100:.0f}%",
            "avg_time": f"{avg_time:.1f}s",
            "json_valid": json_valid,
            "json_rate": f"{json_valid/max(len(results),1)*100:.0f}%",
        }

    # Print comparison table
    print(f"\n{'Model':<35} {'Pass':<6} {'Success':<10} {'JSON Valid':<12} {'Avg Time':<10}")
    print("-" * 75)
    for key, m in sorted(models.items()):
        print(f"{m['model']:<35} {m['pass']:<6} {m['success_rate']:<10} {m['json_rate']:<12} {m['avg_time']:<10}")


if __name__ == "__main__":
    results_dir = sys.argv[1] if len(sys.argv) > 1 else "pipelines/eval/results"
    generate_report(results_dir)
```

- [ ] **Step 4: Commit**

```bash
git add pipelines/eval/
git commit -m "feat: model evaluation framework — runner, dataset SQL, and report generator"
```

---

### Task 8: Integration Verification

- [ ] **Step 1: Verify all assets load**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "
from countyiq.definitions import defs
specs = list(defs.get_all_asset_specs())
print(f'Total assets: {len(specs)}')
new_assets = [
    'entity_verification', 'signal_validation',
    'brief_generation', 'county_narratives',
]
for name in new_assets:
    found = any(name in str(s.key) for s in specs)
    print(f'  Pass {new_assets.index(name)+1}: {name} — {\"FOUND\" if found else \"MISSING\"}')
"
```

Expected: All 4 new assets found, total assets ~37.

- [ ] **Step 2: Run all tests**

```bash
cd pipelines && source .venv/bin/activate
pytest tests/test_intelligence_common.py tests/test_pass1_entity.py tests/test_pass2_signals.py tests/test_pass3_briefs.py tests/test_pass4_narratives.py tests/test_pa_dos_parser.py tests/test_proceedings_parser.py tests/test_proceeding_extraction.py -v
```

Expected: All tests pass.

- [ ] **Step 3: Verify Dagster dependency chain**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "
from countyiq.definitions import defs
for spec in defs.get_all_asset_specs():
    key = spec.key.to_user_string()
    if key in ('entity_verification', 'signal_validation', 'brief_generation', 'county_narratives'):
        deps = [str(d) for d in (spec.deps or [])]
        print(f'{key} depends on: {deps}')
"
```

Expected dependency chain:
- entity_verification → [pa_dos_entities, proceeding_extraction, development_signals]
- signal_validation → [entity_verification, development_signals]
- brief_generation → [signal_validation]
- county_narratives → [brief_generation]

- [ ] **Step 4: Verify jobs load**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "
from countyiq.jobs import (
    intelligence_full_pipeline,
    entity_verification_refresh,
    signal_validation_refresh,
    brief_generation_refresh,
    county_narratives_refresh,
)
print('All 5 intelligence pipeline jobs loaded')
"
```

- [ ] **Step 5: Final commit if needed**

```bash
git status
```

---

## Phase 2 Complete Checklist

After all tasks:

- [ ] Shared intelligence context module with SQL helpers and formatters
- [ ] Pass 1: Entity verification — context gatherer, template, output parser, Dagster asset
- [ ] Pass 2: Signal validation — 13 signal-type templates, context gatherer, output parser, Dagster asset
- [ ] Pass 3: Brief generation — template with citation constraints, context gatherer, output parser, Dagster asset
- [ ] Pass 4: County narratives — 4 scan types (corridor, portfolio, municipal, distress), templates, Dagster asset
- [ ] All Dagster assets load and follow the dependency chain
- [ ] 5 new Dagster jobs for individual passes + full pipeline
- [ ] Model evaluation framework (runner + dataset SQL + report generator)
- [ ] All tests pass

## Next Steps After Phase 2

1. **Download GGUF models** to test (Qwen 3.5, Gemma 4, Llama 4, etc.)
2. **Run evaluation:** `python eval/eval_runner.py --model /path/to/model.gguf --pass 2 --limit 20`
3. **Compare results:** `python eval/eval_report.py eval/results/`
4. **Select model** based on structured output quality, reasoning accuracy, and speed
5. **Phase 3 plan:** API endpoints + frontend transformation
