from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import psycopg2
import pytest
from fastapi.testclient import TestClient
from psycopg2.extras import Json


REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINES_DIR = REPO_ROOT / "pipelines"

# Tests use a DEDICATED database. _reset_tables TRUNCATEs staging tables,
# and the main `countyiq` database on this container now doubles as the
# local backfill data store (176K real parcels) — pointing tests at it
# would wipe hours of fetched data.
DB_ENV = {
    "DATABASE_HOST": "localhost",
    "DATABASE_PORT": "5433",
    "DATABASE_NAME": "countyiq_test",
    "DATABASE_USER": "dagster_admin",
    "DATABASE_PASSWORD": "localtest",
    "DATABASE_URL": "postgresql://dagster_admin:localtest@localhost:5433/countyiq_test",
}

TEST_PIDN = "0000000000001"
SECOND_PIDN = "0000000000002"
OTHER_PIDN = "0000000000003"
TEST_MUNICIPALITY = "Test TWP"
TEST_DISTRICT = "TEST TOWNSHIP"


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _ensure_test_database() -> None:
    """Create countyiq_test (extensions + schemas) if it doesn't exist."""
    conn = psycopg2.connect(
        host=DB_ENV["DATABASE_HOST"],
        port=DB_ENV["DATABASE_PORT"],
        dbname="countyiq",
        user=DB_ENV["DATABASE_USER"],
        password=DB_ENV["DATABASE_PASSWORD"],
    )
    conn.autocommit = True  # CREATE DATABASE can't run inside a transaction
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (DB_ENV["DATABASE_NAME"],),
            )
            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{DB_ENV["DATABASE_NAME"]}"')
    finally:
        conn.close()

    with psycopg2.connect(
        host=DB_ENV["DATABASE_HOST"],
        port=DB_ENV["DATABASE_PORT"],
        dbname=DB_ENV["DATABASE_NAME"],
        user=DB_ENV["DATABASE_USER"],
        password=DB_ENV["DATABASE_PASSWORD"],
    ) as conn2:
        with conn2.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            cur.execute("CREATE SCHEMA IF NOT EXISTS staging")
            cur.execute("CREATE SCHEMA IF NOT EXISTS meta")
        conn2.commit()


def _wait_for_database() -> None:
    deadline = time.time() + 30
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            # Wait on the maintenance DB — countyiq_test may not exist yet.
            with psycopg2.connect(
                host=DB_ENV["DATABASE_HOST"],
                port=DB_ENV["DATABASE_PORT"],
                dbname="countyiq",
                user=DB_ENV["DATABASE_USER"],
                password=DB_ENV["DATABASE_PASSWORD"],
            ):
                return
        except psycopg2.OperationalError as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError("Timed out waiting for postgres-test to accept connections") from last_error


def _reset_tables(cur) -> None:
    cur.execute(
        """
        TRUNCATE TABLE
            staging.proceeding_extractions,
            staging.public_proceedings,
            meta.intelligence_passes,
            public.intelligence_events,
            public.owner_briefs,
            public.owner_source_links,
            public.owners,
            public.parcel_briefs,
            public.county_narratives,
            public.development_momentum,
            staging.structures,
            staging.flood_zones,
            staging.plcb_licenses,
            staging.tax_claims,
            staging.parcels,
            staging.municipalities
        RESTART IDENTITY CASCADE
        """
    )


def _seed_contract_data(cur) -> None:
    municipality_geom = "MULTIPOLYGON(((-76.8000 39.9000, -76.8000 39.9200, -76.7800 39.9200, -76.7800 39.9000, -76.8000 39.9000)))"
    parcel_one_geom = "MULTIPOLYGON(((-76.7990 39.9010, -76.7990 39.9050, -76.7950 39.9050, -76.7950 39.9010, -76.7990 39.9010)))"
    parcel_two_geom = "MULTIPOLYGON(((-76.7940 39.9010, -76.7940 39.9050, -76.7900 39.9050, -76.7900 39.9010, -76.7940 39.9010)))"
    parcel_three_geom = "MULTIPOLYGON(((-76.7890 39.9010, -76.7890 39.9050, -76.7850 39.9050, -76.7850 39.9010, -76.7890 39.9010)))"
    structure_geom = "MULTIPOLYGON(((-76.7985 39.9015, -76.7985 39.9040, -76.7960 39.9040, -76.7960 39.9015, -76.7985 39.9015)))"
    flood_geom = parcel_one_geom

    cur.execute(
        """
        INSERT INTO staging.municipalities (name, muni_type, county, geom, source_url)
        VALUES
            (%s, %s, %s, ST_GeomFromText(%s, 4326), %s),
            (%s, %s, %s, ST_GeomFromText(%s, 4326), %s)
        """,
        (
            TEST_MUNICIPALITY,
            "Township",
            "York",
            municipality_geom,
            "https://example.com/municipalities/test",
            "Other TWP",
            "Township",
            "York",
            municipality_geom,
            "https://example.com/municipalities/other",
        ),
    )

    cur.execute(
        """
        INSERT INTO staging.parcels (
            pidn,
            owner_full,
            own_name1,
            propadr,
            municipality,
            school_dis,
            "class",
            acres,
            aprland,
            aprbldg,
            aprtotal,
            saledt,
            price,
            deed_bk,
            deed_pg,
            geom,
            source_url
        )
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s),
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s),
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s)
        """,
        (
            TEST_PIDN,
            "Alpha Holdings LLC",
            "Alpha Holdings LLC",
            "1 Main St",
            TEST_MUNICIPALITY,
            "YORK",
            "C",
            1.25,
            50000.0,
            150000.0,
            200000.0,
            "01-JAN-2024",
            210000.0,
            "123",
            "456",
            parcel_one_geom,
            "https://example.com/parcels/1",
            SECOND_PIDN,
            "Beta Investments LLC",
            "Beta Investments LLC",
            "2 Main St",
            TEST_MUNICIPALITY,
            "YORK",
            "I",
            2.0,
            40000.0,
            60000.0,
            100000.0,
            "10-FEB-2023",
            95000.0,
            "124",
            "457",
            parcel_two_geom,
            "https://example.com/parcels/2",
            OTHER_PIDN,
            "Gamma Group LLC",
            "Gamma Group LLC",
            "3 Side St",
            "Other TWP",
            "YORK",
            "C",
            3.0,
            70000.0,
            110000.0,
            180000.0,
            "12-MAR-2022",
            175000.0,
            "125",
            "458",
            parcel_three_geom,
            "https://example.com/parcels/3",
        ),
    )

    cur.execute(
        """
        INSERT INTO staging.tax_claims (
            pidn,
            parcel_id_raw,
            tax_district_name,
            owner_name,
            property_address,
            tax_year,
            authority_name,
            tax_owed,
            penalty_owed,
            interest_owed,
            fees_owed,
            total,
            report_date,
            source_url
        )
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s),
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            TEST_PIDN,
            TEST_PIDN,
            TEST_DISTRICT,
            "Alpha Holdings LLC",
            "1 Main St",
            2024,
            "COUNTY",
            1200.00,
            100.00,
            50.00,
            25.00,
            1375.00,
            "2026-04-19",
            "https://example.com/tax/1",
            SECOND_PIDN,
            SECOND_PIDN,
            TEST_DISTRICT,
            "Beta Investments LLC",
            "2 Main St",
            2023,
            "COUNTY",
            600.00,
            50.00,
            25.00,
            25.00,
            700.00,
            "2026-04-19",
            "https://example.com/tax/2",
        ),
    )

    cur.execute(
        """
        INSERT INTO staging.plcb_licenses (
            lid,
            license_number,
            license_type,
            status,
            licensee,
            premises_name,
            premises_address,
            municipality,
            last_issue_date,
            expiration_date,
            source_url
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            "LIC-1",
            "R-100",
            "Restaurant",
            "Active",
            "Main Street Hospitality LLC",
            "Main Street Tavern",
            "1 Main St",
            TEST_MUNICIPALITY,
            "2026-01-01",
            "2027-01-01",
            "https://example.com/licenses/1",
        ),
    )

    cur.execute(
        """
        INSERT INTO staging.structures (
            objectid,
            index_id,
            building_type,
            geom,
            source_url
        )
        VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326), %s)
        """,
        (
            1,
            TEST_PIDN,
            "Commercial",
            structure_geom,
            "https://example.com/structures/1",
        ),
    )

    cur.execute(
        """
        INSERT INTO staging.flood_zones (
            fld_zone,
            zone_subty,
            sfha_tf,
            fld_ar_id,
            geom,
            source_url
        )
        VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s)
        """,
        (
            "AE",
            "FLOODWAY",
            "T",
            "FLOOD-1",
            flood_geom,
            "https://example.com/flood/1",
        ),
    )

    signals = Json(
        {
            "growth_area": {"weight": 1.2, "evidence": {"ga_type": "PGA"}},
            "ownership_change": {
                "weight": 0.8,
                "validation_reasoning": "Private Person sold the parcel.",
                "evidence": {"price": 210000, "prev_owner": "Private Person"},
            },
        }
    )
    cur.execute(
        """
        INSERT INTO public.development_momentum (
            pidn,
            score,
            opportunity_score,
            has_active_plan,
            eligible,
            exclusion_reasons,
            signals,
            top_signal,
            signal_count,
            score_version,
            computed_at
        )
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()),
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()),
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        (
            TEST_PIDN,
            72,
            64,
            False,
            True,
            Json([]),
            signals,
            "growth_area",
            2,
            2,
            SECOND_PIDN,
            55,
            35,
            False,
            True,
            Json([]),
            signals,
            "ownership_change",
            2,
            2,
            OTHER_PIDN,
            81,
            20,
            True,
            True,
            Json([]),
            signals,
            "growth_area",
            2,
            2,
        ),
    )

    cur.execute(
        """
        INSERT INTO public.parcel_briefs (
            pidn,
            brief_text,
            assessment,
            assessment_reasoning,
            key_questions,
            signal_count,
            citations,
            brief_version,
            generated_at,
            pass_metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        """,
        (
            TEST_PIDN,
            "Signal-rich commercial parcel with recent ownership change.",
            "promising",
            "Growth-area and ownership-change signals align.",
            ["Is the adjacent parcel also available?"],
            2,
            Json(["Proceedings packet", "County narrative"]),
            1,
            Json({"model": "test"}),
        ),
    )

    cur.execute(
        """
        INSERT INTO public.county_narratives (
            title,
            body,
            narrative_type,
            trajectory,
            affected_pidns,
            key_entities,
            citations,
            generated_at,
            narrative_key
        )
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, NOW(), %s),
            (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        """,
        (
            "Main Street corridor accelerating",
            "Commercial momentum is building along Main Street.",
            "corridor",
            "accelerating",
            [TEST_PIDN],
            ["Alpha Holdings LLC"],
            Json(["ZHB packet"]),
            "corridor-main-street",
            "Township delinquencies remain stable",
            "Delinquent parcels remain concentrated in one corridor.",
            "municipal",
            "stable",
            [SECOND_PIDN],
            ["Beta Investments LLC"],
            Json(["Tax claims report"]),
            "municipal-test-twp",
        ),
    )

    cur.execute(
        """
        INSERT INTO meta.intelligence_passes (
            pidn,
            pass_number,
            status,
            last_run_at,
            cross_signal_insight,
            signals_validated_count
        )
        VALUES (%s, %s, %s, NOW(), %s, %s)
        """,
        (
            TEST_PIDN,
            2,
            "complete",
            "Ownership change and zoning activity reinforce one another.",
            2,
        ),
    )

    cur.execute(
        """
        INSERT INTO staging.public_proceedings (
            body_name,
            meeting_date,
            proceeding_type,
            raw_text,
            source_url,
            document_url,
            content_hash
        )
        VALUES
            (%s, %s, %s, %s, %s, %s, %s),
            (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            "Test Township ZHB",
            "2026-04-10",
            "zoning_hearing",
            "Variance packet",
            "https://example.com/proceedings/1",
            "https://example.com/proceedings/1.pdf",
            "hash-1",
            "Test Township Planning Commission",
            "2026-04-15",
            "planning_commission",
            "Subdivision packet",
            "https://example.com/proceedings/2",
            "https://example.com/proceedings/2.pdf",
            "hash-2",
        ),
    )
    proceeding_ids = [row[0] for row in cur.fetchall()]

    cur.execute(
        """
        INSERT INTO staging.proceeding_extractions (
            proceeding_id,
            extraction_type,
            applicant_name,
            parcel_reference,
            current_zoning,
            proposed_zoning,
            decision,
            supporting_text,
            extraction_confidence,
            model_used,
            source_url
        )
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s),
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            proceeding_ids[0],
            "variance_request",
            "Alpha Holdings LLC",
            TEST_PIDN,
            "C-1",
            "C-2",
            "approved",
            "Requested reduced setback for redevelopment.",
            0.92,
            "test-model",
            "https://example.com/extractions/1",
            proceeding_ids[1],
            "subdivision_plan",
            "Alpha Holdings LLC",
            "1 Main St",
            "C-1",
            None,
            "tabled",
            "Planning commission reviewed a two-lot split.",
            0.85,
            "test-model",
            "https://example.com/extractions/2",
        ),
    )

    cur.execute(
        """
        INSERT INTO public.intelligence_events (
            event_key, source_kind, source_record_id, category, event_type,
            event_tags, title, what_happened, why_it_matters,
            what_happens_next, event_date, detected_at, confidence,
            municipality, project_key, project_name, related_entities,
            related_pidns, source_evidence, interpretation_kind,
            interpretation_model, interpretation_generated_at
        )
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE, NOW(), %s,
             %s, NULL, NULL, %s, %s, %s, %s, NULL, NULL),
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE, NOW(), %s,
             %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        (
            "parcel:test-transfer",
            "parcel_event",
            "1",
            "parcel",
            "transfer",
            ["transfer"],
            "Ownership activity at 1 Main St",
            "The county parcel record changed ownership.",
            "Ownership changes can precede later development activity.",
            "Monitor later deed and municipal records.",
            0.95,
            TEST_MUNICIPALITY,
            ["Alpha Holdings LLC"],
            [TEST_PIDN],
            Json([{
                "label": "York County parcel record",
                "url": "https://example.com/parcels/1",
                "document_url": None,
                "excerpt": None,
                "details": {"owner_full": {"old": "Old Owner", "new": "Alpha Holdings LLC"}},
            }]),
            "deterministic",
            "development:test-project",
            "proceeding_extraction",
            "1",
            "development",
            "approval",
            ["application", "hearing", "approval", "condition"],
            "Approval: Main Street redevelopment",
            "The zoning hearing board approved the requested variance.",
            "The approval advances the matter subject to stated conditions.",
            "Monitor satisfaction of conditions and later permits.",
            0.92,
            TEST_MUNICIPALITY,
            "project:test-main-street",
            "Main Street redevelopment",
            ["Alpha Holdings LLC"],
            [TEST_PIDN],
            Json([{
                "label": "Test Township ZHB",
                "url": "https://example.com/proceedings/1",
                "document_url": "https://example.com/proceedings/1.pdf",
                "excerpt": "The board approved the variance with conditions.",
                "details": {"decision": "approved", "conditions": ["traffic review"]},
            }]),
            "llm",
            "test-model",
        ),
    )

    # Owner resolution + portfolio brief for the owner-profile contract.
    cur.execute(
        """
        INSERT INTO public.owners (canonical_name, entity_type, parcel_count, municipality)
        VALUES (%s, %s, %s, %s)
        RETURNING owner_id
        """,
        ("Alpha Holdings LLC", "llc", 1, TEST_MUNICIPALITY),
    )
    owner_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO public.owner_source_links
            (owner_id, source_type, source_id, source_name, confidence, match_tier)
        VALUES (%s, 'parcel', %s, %s, 1.0, 'exact_name')
        """,
        (owner_id, TEST_PIDN, "Alpha Holdings LLC"),
    )
    cur.execute(
        """
        INSERT INTO public.owner_briefs (
            canonical_name, owner_id, brief_text, portfolio_strategy,
            concentration_notes, key_pattern, recommendation, urgency,
            top_risk, evidence_strength, n_parcels,
            model_version, prompt_version, n_trials, trial_agreement, confidence
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            "Alpha Holdings LLC",
            owner_id,
            "Alpha Holdings is consolidating along Main Street. [Parcel: 0000000000001]",
            "accumulator",
            "Single-corridor concentration.",
            "Recent acquisition plus zoning activity suggests active expansion.",
            "monitor",
            "near_term_90d",
            "Competing buyers in the same corridor.",
            "moderate",
            1,
            "test-model",
            "testprompt123",
            1,
            None,
            0.72,
        ),
    )


@pytest.fixture(scope="session", autouse=True)
def prepared_database() -> None:
    os.environ.update(DB_ENV)
    _run(["docker", "compose", "up", "-d", "postgres-test"], cwd=PIPELINES_DIR)
    _wait_for_database()
    _ensure_test_database()

    env = os.environ.copy()
    env.update(DB_ENV)
    _run(["uv", "run", "alembic", "upgrade", "head"], cwd=PIPELINES_DIR, env=env)

    with psycopg2.connect(
        host=DB_ENV["DATABASE_HOST"],
        port=DB_ENV["DATABASE_PORT"],
        dbname=DB_ENV["DATABASE_NAME"],
        user=DB_ENV["DATABASE_USER"],
        password=DB_ENV["DATABASE_PASSWORD"],
    ) as conn:
        with conn.cursor() as cur:
            _reset_tables(cur)
            _seed_contract_data(cur)
        conn.commit()


@pytest.fixture()
def client(prepared_database: None) -> TestClient:
    from api.main import app

    with TestClient(app) as test_client:
        yield test_client
