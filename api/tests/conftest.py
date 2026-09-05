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
TEST_DATABASE_PORT = int(os.environ.get("COUNTYIQ_TEST_DATABASE_PORT", "5433"))
if not 1 <= TEST_DATABASE_PORT <= 65535:
    raise ValueError("COUNTYIQ_TEST_DATABASE_PORT must be a valid TCP port")

DB_ENV = {
    "DATABASE_HOST": "localhost",
    "DATABASE_PORT": str(TEST_DATABASE_PORT),
    "DATABASE_NAME": "countyiq_test",
    "DATABASE_USER": "dagster_admin",
    "DATABASE_PASSWORD": "localtest",
    "DATABASE_URL": f"postgresql://dagster_admin:localtest@localhost:{TEST_DATABASE_PORT}/countyiq_test",
}
API_DB_USER = "countyiq_api_test"
API_DB_PASSWORD = "test-api-role-password-000000000000000000000000"

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
    raise RuntimeError(
        "Timed out waiting for postgres-test to accept connections"
    ) from last_error


def _provision_api_role() -> None:
    _run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "-e",
            f"DATABASE_API_USER={API_DB_USER}",
            "-e",
            f"DATABASE_API_PASSWORD={API_DB_PASSWORD}",
            "-e",
            f"POSTGRES_DB={DB_ENV['DATABASE_NAME']}",
            "postgres-test",
            "bash",
            "/docker-entrypoint-initdb.d/03-api-role.sh",
        ],
        cwd=PIPELINES_DIR,
    )


def _reset_tables(cur) -> None:
    cur.execute(
        """
        TRUNCATE TABLE
            public.app_users,
            public.watchspaces,
            staging.proceeding_extractions,
            staging.public_proceedings,
            meta.job_run_status,
            meta.intelligence_passes,
            public.intelligence_events,
            public.owner_briefs,
            public.entity_graph,
            public.evidence,
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
            staging.zoning,
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
        INSERT INTO staging.zoning (
            zrecid, muni_name, zcode, zname, ztype, gen_zcode, gen_zname, geom
        )
        VALUES (1, %s, 'HC', 'Highway Commercial', 'C', 'C', 'Commercial', ST_GeomFromText(%s, 4326))
        """,
        (TEST_MUNICIPALITY, municipality_geom),
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
        UPDATE staging.parcels
        SET heatsys = 1, fuel = 2
        WHERE pidn = %s
        """,
        (TEST_PIDN,),
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
            "growth_area": {
                "weight": 1.2,
                "source_url": "https://example.com/growth/1",
                "validation_status": "confirmed",
                "adjusted_significance": "high",
                "validation_reasoning": "The parcel intersects the official growth-area layer.",
                "evidence": {"ga_type": "PGA"},
            },
            "ownership_change": {
                "weight": 0.8,
                "source_url": "https://example.com/parcels/1",
                "validation_status": "confirmed",
                "adjusted_significance": "medium",
                "validation_reasoning": "Private Person sold the parcel.",
                "evidence": {"price": 210000, "prev_owner": "Private Person"},
            },
        }
    )

    cur.execute(
        """
        INSERT INTO public.evidence (
            pidn, signal_key, claim, evidence_data, source_url, internal_url,
            validation_status, adjusted_significance, validation_reasoning,
            validated_at, confidence
        )
        VALUES
            (%s, 'growth_area', %s, %s, %s, %s, 'confirmed', 'high', %s, NOW(), 0.95),
            (%s, 'ownership_change', %s, %s, %s, %s, 'confirmed', 'medium', %s, NOW(), 0.88)
        """,
        (
            TEST_PIDN,
            "Parcel intersects the primary growth area.",
            Json({"ga_type": "PGA"}),
            "https://example.com/growth/1",
            f"/property/{TEST_PIDN}",
            "Confirmed by the official growth-area layer.",
            TEST_PIDN,
            "A recent ownership change was recorded.",
            Json({"price": 210000, "saledt": "01-JAN-2024"}),
            "https://example.com/parcels/1",
            f"/property/{TEST_PIDN}",
            "Confirmed by the versioned parcel record.",
        ),
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
            "Signal-rich commercial parcel in a growth area [Signal: growth_area] with a recent ownership change [Signal: ownership_change].",
            "promising",
            "Growth-area [Signal: growth_area] and ownership-change [Signal: ownership_change] signals align.",
            ["Is the adjacent parcel also available?"],
            2,
            Json(["growth_area", "ownership_change"]),
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
            "Hanover Borough Council",
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
    # Synthetic parcels and both proceeding bodies share the fixture jurisdiction.
    # Keep the named Hanover policy so policy-revocation tests exercise it.
    cur.execute("""
        UPDATE meta.municipality_source_rights
        SET municipality_name=%s, derived_product_allowed=TRUE,
            rights_status='conditional', review_due_on=CURRENT_DATE+30
        WHERE source_key='hanover_borough_council'
    """, (TEST_MUNICIPALITY,))
    cur.execute("""
        INSERT INTO meta.municipality_source_rights
            (source_key,municipality_name,body_name,proceeding_type,rights_status,
             derived_product_allowed,terms_review_status,reviewed_on,review_due_on)
        VALUES ('test_township_planning_commission',%s,'Test Township Planning Commission',
                'planning_commission','conditional',TRUE,'reviewed',CURRENT_DATE,CURRENT_DATE+30)
        ON CONFLICT (source_key) DO UPDATE SET municipality_name=EXCLUDED.municipality_name,
            derived_product_allowed=TRUE, rights_status='conditional',review_due_on=EXCLUDED.review_due_on
    """, (TEST_MUNICIPALITY,))
    cur.execute("UPDATE staging.public_proceedings SET metadata_quality=%s WHERE id=ANY(%s)",
                (Json({"status": "ready", "version": "test-fixture"}), proceeding_ids))

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
            f"Parcel ID: {TEST_PIDN}-00000",
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
            Json(
                [
                    {
                        "label": "York County parcel record",
                        "url": "https://example.com/parcels/1",
                        "document_url": None,
                        "excerpt": None,
                        "details": {
                            "owner_full": {
                                "old": "Old Owner",
                                "new": "Alpha Holdings LLC",
                            }
                        },
                    }
                ]
            ),
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
            Json(
                [
                    {
                        "label": "Hanover Borough Council",
                        "url": "https://example.com/proceedings/1",
                        "document_url": "https://example.com/proceedings/1.pdf",
                        "excerpt": "The board approved the variance with conditions.",
                        "details": {
                            "decision": "approved",
                            "conditions": ["traffic review"],
                        },
                    }
                ]
            ),
            "llm",
            "test-model",
        ),
    )

    # Owner resolution + portfolio brief for the owner-profile contract.
    cur.execute(
        """
        INSERT INTO public.owners (
            canonical_name, entity_type, parcel_count, municipality, aliases,
            verification_status, verification_reasoning, verified_at
        )
        VALUES (%s, %s, %s, %s, %s, 'verified', %s, NOW())
        RETURNING owner_id
        """,
        (
            "Alpha Holdings LLC",
            "business",
            1,
            TEST_MUNICIPALITY,
            ["Alpha Holdings"],
            f"The entity owns the cited county parcel [Evidence: parcels:{TEST_PIDN}].",
        ),
    )
    owner_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO public.entity_graph (
            canonical_name, entity_type, linked_names, linked_sources,
            relationships, verification_status, verification_reasoning, verified_at
        )
        VALUES (%s, 'llc', %s, %s, '[]'::jsonb, 'verified', %s, NOW())
        """,
        (
            "Alpha Holdings LLC",
            ["Alpha Holdings LLC", "Alpha Holdings"],
            Json({"parcels": [TEST_PIDN]}),
            f"The entity owns the cited county parcel [Evidence: parcels:{TEST_PIDN}].",
        ),
    )
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
            top_risk, evidence_strength, citations, parcel_citations, n_parcels,
            model_version, prompt_version, n_trials, trial_agreement, confidence
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            "Alpha Holdings LLC",
            owner_id,
            f"Alpha Holdings is consolidating along Main Street [Signal: growth_area] [Parcel: {TEST_PIDN}].",
            "accumulator",
            "Single-corridor concentration.",
            "Recent acquisition plus zoning activity suggests active expansion [Signal: growth_area].",
            "monitor",
            "near_term_90d",
            f"Competing buyers may target the same corridor [Parcel: {TEST_PIDN}].",
            "moderate",
            Json(["growth_area"]),
            Json([TEST_PIDN]),
            1,
            "test-model",
            "testprompt123",
            1,
            None,
            0.72,
        ),
    )

    cur.execute(
        """
        INSERT INTO meta.job_run_status (
            job_name, run_id, status, started_at, finished_at, last_success_at
        )
        VALUES (
            'arcgis_refresh', 'api-contract-arcgis', 'success',
            NOW() - INTERVAL '1 minute', NOW(), NOW()
        )
        """
    )


def _contract_owner_context_ref(cur):
    import hashlib
    import json
    cur.execute("""
        SELECT o.owner_id,o.canonical_name,o.entity_type,
               array_agg(DISTINCT osl.source_id ORDER BY osl.source_id),
               count(DISTINCT osl.source_id)
        FROM public.owners o JOIN public.owner_source_links osl
          ON osl.owner_id=o.owner_id AND osl.source_type='parcel'
        WHERE o.canonical_name='Alpha Holdings LLC'
        GROUP BY o.owner_id,o.canonical_name,o.entity_type
    """)
    context = dict(zip(("owner_id","canonical_name","entity_type","pidns","n_parcels"), cur.fetchone()))
    cur.execute("""
        SELECT DISTINCT e.pidn,p.municipality FROM public.evidence e
        LEFT JOIN staging.parcels p ON p.pidn=e.pidn AND p.valid_to IS NULL
        WHERE e.pidn=%s AND e.validation_status IN ('confirmed','upgraded','downgraded')
    """, (TEST_PIDN,))
    context["signal_municipalities"] = {pidn: municipality or None for pidn, municipality in cur.fetchall()}
    return "owner-context:v2:" + hashlib.sha256(
        json.dumps(context,sort_keys=True,separators=(",",":"),default=str).encode()
    ).hexdigest()


def _contract_brief_payload(cur, kind):
    """Synthetic accepted output matching the persisted customer-facing claims."""
    if kind == "parcel_brief":
        cur.execute("SELECT to_jsonb(b) FROM public.parcel_briefs b WHERE pidn=%s", (TEST_PIDN,))
        payload = cur.fetchone()[0]
        payload["brief"] = payload.pop("brief_text")
        payload["recommendation"] = "watch"
    else:
        cur.execute("SELECT to_jsonb(b) FROM public.owner_briefs b WHERE canonical_name='Alpha Holdings LLC'")
        payload = cur.fetchone()[0]
    return payload


def _bind_contract_brief_versions(cur):
    """Attach synthetic accepted history to the current contract signal versions."""
    import hashlib
    owner_subject = "owner_brief:" + hashlib.sha256(b"Alpha Holdings LLC").hexdigest()[:20]
    cur.execute("SELECT signal_key,active_inference_id FROM public.evidence WHERE pidn=%s ORDER BY signal_key", (TEST_PIDN,))
    refs = [f"signal-version:{TEST_PIDN}:{key}:{version}" for key, version in cur.fetchall()]
    owner_ref = _contract_owner_context_ref(cur)
    cur.execute("SELECT meta.parcel_brief_source_fingerprint(%s)", (TEST_PIDN,))
    parcel_ref = "parcel-context:v1:" + cur.fetchone()[0]
    for kind in ("parcel_brief", "owner_brief"):
        cur.execute("""
            INSERT INTO meta.intelligence_inference_history
              (subject_key,pass_number,output_kind,decision_key,source_hash,input_hash,
               requested_model,prompt_version,output_hash,decision_fingerprint,
               payload,evidence_refs,disposition)
            VALUES (%s,3,%s,'contract','fixture','fixture','fixture','fixture',
                    'fixture','fixture',%s,%s,'accepted') RETURNING inference_id
        """, (owner_subject if kind == "owner_brief" else TEST_PIDN, kind, Json(_contract_brief_payload(cur, kind)), Json(refs + ([owner_ref] if kind == "owner_brief" else [parcel_ref]))))
        inference_id = cur.fetchone()[0]
        if kind == "parcel_brief":
            cur.execute("UPDATE public.parcel_briefs SET active_inference_id=%s WHERE pidn=%s", (inference_id,TEST_PIDN))
        else:
            cur.execute("UPDATE public.owner_briefs SET active_inference_id=%s WHERE canonical_name='Alpha Holdings LLC'", (inference_id,))


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
            cur.execute("""
                INSERT INTO meta.intelligence_inference_history
                  (subject_key,pass_number,output_kind,decision_key,source_hash,input_hash,
                   requested_model,prompt_version,output_hash,decision_fingerprint,
                   payload,evidence_refs,disposition)
                VALUES (%s,2,'signal_validation','contract','fixture','fixture','fixture',
                        'fixture','fixture','fixture',jsonb_build_object(
                            'validations',(SELECT jsonb_agg(jsonb_build_object('signal_key',signal_key,'validation_status',validation_status,'adjusted_significance',adjusted_significance)) FROM public.evidence WHERE pidn=%s),
                            'cross_signal_insight',(SELECT cross_signal_insight FROM meta.intelligence_passes WHERE pidn=%s AND pass_number=2)
                        ),'[]','accepted')
                RETURNING inference_id
            """, (TEST_PIDN,TEST_PIDN,TEST_PIDN))
            signal_inference = cur.fetchone()[0]
            cur.execute("UPDATE meta.intelligence_passes SET input_hash='fixture' WHERE pidn=%s AND pass_number=2",(TEST_PIDN,))
            cur.execute("UPDATE public.evidence SET active_inference_id=%s WHERE pidn=%s", (signal_inference,TEST_PIDN))
            _bind_contract_brief_versions(cur)
        conn.commit()

    _provision_api_role()
    os.environ.update(
        {
            "DATABASE_USER": API_DB_USER,
            "DATABASE_PASSWORD": API_DB_PASSWORD,
        }
    )


@pytest.fixture()
def client(prepared_database: None) -> TestClient:
    from api.main import app

    with TestClient(app) as test_client:
        yield test_client
