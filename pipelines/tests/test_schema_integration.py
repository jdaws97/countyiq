"""Database-schema contracts that require migrated local Postgres."""

from __future__ import annotations

import os

import psycopg2
import pytest

from countyiq.lib.county_config import get_county_config
from countyiq.lib.source_rights import authorize_municipality_sources
from countyiq.lib.source_rights import record_municipality_source_health


def _connect():
    return psycopg2.connect(
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", "5433")),
        dbname=os.environ.get("DATABASE_NAME", "countyiq"),
        user=os.environ.get("DATABASE_USER", "dagster_admin"),
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )


class _IntegrationDatabase:
    """Minimal DatabaseResource-compatible adapter over the test connection."""

    def __init__(self, connection):
        self.connection = connection
        self.connection.autocommit = True

    def execute(self, sql: str, params=None):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall() if cursor.description else None


class _TransactionalDatabase:
    """Adapter used when an integration assertion must roll back its fixture."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql: str, params=None):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall() if cursor.description else None


@pytest.mark.integration
def test_unused_legacy_meta_tables_are_absent() -> None:
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT to_regclass(name)
                FROM unnest(%s::text[]) AS names(name)
                ORDER BY name
                """,
                (
                    [
                        "meta.data_quality_checks",
                        "meta.infra_metrics",
                        "meta.pipeline_status",
                    ],
                ),
            )
            assert cursor.fetchall() == [(None,), (None,), (None,)]
    finally:
        connection.close()


@pytest.mark.integration
def test_source_governance_and_site_readiness_schema() -> None:
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT to_regclass(name)
                FROM unnest(%s::text[]) AS names(name)
                ORDER BY name
                """,
                ([
                    "meta.source_rights",
                    "meta.source_rights_audit",
                    "meta.municipality_source_rights",
                    "meta.municipality_source_audit",
                    "meta.municipality_source_health",
                    "staging.economic_development_parks",
                    "staging.environmental_diligence_sites",
                    "staging.local_traffic_counts",
                    "staging.soils",
                    "staging.zoning_overlays",
                ],),
            )
            assert all(row[0] is not None for row in cursor.fetchall())

            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'meta'
                  AND table_name = 'source_rights_audit'
                  AND column_name IN (
                      'policy_version', 'policy_fingerprint', 'policy_snapshot'
                  )
                """
            )
            assert {row[0] for row in cursor.fetchall()} == {
                "policy_version", "policy_fingerprint", "policy_snapshot"
            }

            cursor.execute(
                """
                SELECT rights_status, COUNT(*)
                FROM meta.source_rights
                GROUP BY rights_status
                ORDER BY rights_status
                """
            )
            assert dict(cursor.fetchall()) == {
                "conditional": 4,
                "green": 5,
                "paused": 3,
            }

            cursor.execute(
                """
                SELECT rights_status, COUNT(*)
                FROM meta.municipality_source_rights
                GROUP BY rights_status
                ORDER BY rights_status
                """
            )
            assert dict(cursor.fetchall()) == {
                "conditional": 110,
                "paused": 12,
            }

            cursor.execute(
                """
                SELECT COUNT(DISTINCT municipality_name)
                FROM meta.municipality_source_rights
                WHERE municipality_name IS NOT NULL
                """
            )
            assert cursor.fetchone()[0] == 72

            cursor.execute(
                """
                SELECT municipality_name
                FROM meta.municipality_source_rights
                WHERE source_key = 'hanover_borough_council'
                """
            )
            assert cursor.fetchone()[0] == "HANOVER BORO"

            cursor.execute(
                """
                SELECT source_key, municipality_name
                FROM meta.municipality_source_rights
                WHERE rights_status = 'paused'
                ORDER BY source_key
                """
            )
            assert dict(cursor.fetchall()) == {
                "cross_roads_borough_council": "CROSS ROADS BORO",
                "dover_twp_board_of_supervisors": "DOVER TWP",
                "dover_twp_zoning_hearing_board": "DOVER TWP",
                "franklintown_borough_council": "FRANKLINTOWN BORO",
                "newberry_twp_board_of_supervisors": "NEWBERRY TWP",
                "railroad_borough_council": "RAILROAD BORO",
                "shrewsbury_twp_board_of_supervisors": "SHREWSBURY TWP",
                "west_manheim_twp_board_of_supervisors": "WEST MANHEIM TWP",
                "west_manheim_twp_planning_commission": "WEST MANHEIM TWP",
                "west_manheim_twp_zoning_hearing_board": "WEST MANHEIM TWP",
                "west_york_borough_council": "WEST YORK BORO",
                "washington_twp_board_of_supervisors": "WASHINGTON TWP",
            }

            cursor.execute(
                """
                SELECT allowed_origins
                FROM meta.municipality_source_rights
                WHERE source_key = 'hanover_borough_council'
                """
            )
            assert cursor.fetchone()[0] == ["https://hanoverboroughpa.gov"]

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM meta.municipality_source_rights
                WHERE municipality_name LIKE '%% BORO BORO'
                   OR municipality_name LIKE '%% CITY CITY'
                """
            )
            assert cursor.fetchone()[0] == 0

            cursor.execute(
                """
                SELECT is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'development_momentum'
                  AND column_name = 'site_readiness_score'
                """
            )
            nullable, default = cursor.fetchone()
            assert nullable == "NO"
            assert default == "0"
    finally:
        connection.close()


@pytest.mark.integration
def test_source_audit_ledgers_are_append_only() -> None:
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO meta.source_rights_audit (
                    source_key, asset_key, acquisition_method, allowed, reason
                ) VALUES ('york_open_data', 'integration_test', 'arcgis_rest', TRUE, 'test')
                RETURNING id
                """
            )
            audit_id = cursor.fetchone()[0]
            with pytest.raises(psycopg2.errors.RaiseException, match="append-only"):
                cursor.execute(
                    "UPDATE meta.source_rights_audit SET reason = 'changed' WHERE id = %s",
                    (audit_id,),
                )
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_municipality_authorization_executes_against_migrated_schema() -> None:
    connection = _connect()
    run_id = "schema-integration-municipality-authorization"
    try:
        county = get_county_config()
        entry = next(
            source
            for source in county.municipality_websites
            if source[0] == "Hanover Borough Council"
        )
        authorizations = authorize_municipality_sources(
            _IntegrationDatabase(connection),
            entries=(entry,),
            acquisition_method="official_document_direct",
            asset_key="schema_integration",
            dagster_run_id=run_id,
        )

        assert authorizations["hanover_borough_council"].listing_url == entry[1]
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT allowed, reason, policy_version,
                       length(policy_fingerprint), policy_snapshot->>'source_key'
                FROM meta.municipality_source_audit
                WHERE dagster_run_id = %s
                ORDER BY checked_at DESC, id DESC
                LIMIT 1
                """,
                (run_id,),
            )
            assert cursor.fetchone() == (
                True, "authorized", 1, 64, "hanover_borough_council"
            )
    finally:
        connection.close()


@pytest.mark.integration
def test_site_readiness_score_rebuild_uses_replacement_signals() -> None:
    from dagster import build_asset_context

    from countyiq.assets.enrichment.development_momentum import development_momentum
    from countyiq.resources.database import DatabaseResource

    pidn = "SRTEST0000001"
    connection = _connect()
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE public.development_momentum")
            cursor.execute("TRUNCATE public.development_signals RESTART IDENTITY")
            cursor.execute(
                """
                INSERT INTO public.development_signals (
                    pidn, signal_key, signal_weight, source_table, source_id, evidence
                ) VALUES
                    (%s, 'economic_development_park', 0.18,
                     'staging.economic_development_parks', 'industrial:1',
                     '{"park_types":["industrial"]}'::jsonb),
                    (%s, 'growth_area', 0.02,
                     'staging.growth_areas', 'growth:1',
                     '{"ga_type":"PGA"}'::jsonb),
                    (%s, 'soil_constraint', -0.08,
                     'staging.soils', 'soil:1',
                     '{"drainage":"Poorly drained"}'::jsonb)
                """,
                (pidn, pidn, pidn),
            )

        database = DatabaseResource(
            host=os.environ.get("DATABASE_HOST", "localhost"),
            port=int(os.environ.get("DATABASE_PORT", "5433")),
            dbname=os.environ.get("DATABASE_NAME", "countyiq"),
            user=os.environ.get("DATABASE_USER", "dagster_admin"),
            password=os.environ.get("DATABASE_PASSWORD", "localtest"),
        )
        database._conn = None
        development_momentum.node_def.compute_fn.decorated_fn(
            build_asset_context(), database
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT score, opportunity_score, site_readiness_score,
                       eligible, score_version
                FROM public.development_momentum
                WHERE pidn = %s
                """,
                (pidn,),
            )
            assert cursor.fetchone() == (12, 12, 70, True, 5)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE public.development_momentum")
            cursor.execute("TRUNCATE public.development_signals RESTART IDENTITY")
        connection.close()


@pytest.mark.integration
def test_not_modified_health_preserves_last_document_count() -> None:
    connection = _connect()
    database = _TransactionalDatabase(connection)
    source_key = "hanover_borough_council"
    try:
        record_municipality_source_health(
            database,
            source_key=source_key,
            listing_status="ok",
            robots_allowed=True,
            robots_reason="robots_missing",
            http_status=200,
            document_count=7,
        )
        record_municipality_source_health(
            database,
            source_key=source_key,
            listing_status="not_modified",
            robots_allowed=True,
            robots_reason="robots_missing",
            http_status=304,
            document_count=0,
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT listing_status, document_count
                FROM meta.municipality_source_health
                WHERE source_key = %s
                """,
                (source_key,),
            )
            assert cursor.fetchone() == ("not_modified", 7)
    finally:
        connection.rollback()
        connection.close()
