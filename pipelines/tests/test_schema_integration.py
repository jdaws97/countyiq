"""Database-schema contracts that require migrated local Postgres."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import psycopg2
import pytest
from countyiq.lib.county_config import get_county_config
from countyiq.lib.job_run_status import record_job_run_status
from countyiq.lib.source_rights import (
    authorize_municipality_sources,
    record_municipality_source_health,
)


def _connect():
    database_name = os.environ.get("DATABASE_NAME", "countyiq_test")
    if database_name != "countyiq_test":
        raise RuntimeError(
            "Schema integration tests are destructive and may only use "
            "the dedicated countyiq_test database"
        )
    return psycopg2.connect(
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", "5433")),
        dbname=database_name,
        user=os.environ.get("DATABASE_USER", "dagster_admin"),
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )


def test_schema_integration_connection_refuses_non_test_database(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_NAME", "countyiq")

    with pytest.raises(RuntimeError, match="dedicated countyiq_test database"):
        _connect()


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
@pytest.mark.parametrize("kind", ["signals", "momentum"])
@pytest.mark.parametrize("fail_publication", [False, True])
def test_rebuild_keeps_old_snapshot_readable_and_rolls_back_failed_publication(
    monkeypatch, kind, fail_publication
):
    from psycopg2 import sql
    from countyiq.assets.enrichment import development_signals as signal_module
    from countyiq.assets.enrichment import development_momentum as momentum_module
    from countyiq.resources.database import DatabaseResource
    from dagster import build_asset_context

    writer = _connect()
    reader = _connect()
    reader.autocommit = True
    pidn = "REFRESH000001"
    resource = DatabaseResource(
        host=writer.info.host,
        port=writer.info.port,
        dbname=writer.info.dbname,
        user=writer.info.user,
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )
    resource.setup_for_execution(None)
    pipeline_role = os.environ.get("DATABASE_PIPELINE_USER", "countyiq_pipeline_test")
    resource.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(pipeline_role)))
    # Deployment grants writes, not ownership of administrator-created tables
    # or sequences. Exercise publication under that same permission boundary.
    owner = resource.execute("""
        SELECT pg_get_userbyid(relowner) FROM pg_class
        WHERE oid='public.development_signals_id_seq'::regclass
    """)[0][0]
    assert owner != pipeline_role
    module = signal_module if kind == "signals" else momentum_module
    asset = (
        module.development_signals if kind == "signals" else module.development_momentum
    )
    monkeypatch.setattr(module, "authorize_source_uses", lambda *args, **kwargs: None)
    probed = []

    class ProbeCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def __getattr__(self, name):
            return getattr(self.cursor, name)

        def execute(self, query, params=None):
            if "/* computation probe */" in query:
                # This second real connection must see the old snapshot during
                # the writer's potentially slow computation, without waiting.
                with reader.cursor() as concurrent:
                    concurrent.execute("SET statement_timeout = '500ms'")
                    if kind == "signals":
                        concurrent.execute(
                            "SELECT source_id FROM public.development_signals WHERE pidn=%s",
                            (pidn,),
                        )
                        assert concurrent.fetchall() == [("old-source",)]
                    else:
                        concurrent.execute(
                            "SELECT score FROM public.development_momentum WHERE pidn=%s",
                            (pidn,),
                        )
                        assert concurrent.fetchall() == [(7,)]
                    probed.append(True)
            return self.cursor.execute(query, params)

    class ProbeDatabase:
        def cursor(self):
            return ProbeCursor(resource.cursor())

        def execute(self, query, params=None):
            return resource.execute(query, params)

    if kind == "signals":
        monkeypatch.setattr(
            module, "source_use_is_authorized", lambda *args, **kwargs: False
        )
        monkeypatch.setattr(
            module,
            "_SIGNALS",
            [
                (
                    "active_subdivision",
                    """
                /* computation probe */
                INSERT INTO public.development_signals
                  (pidn,signal_key,signal_weight,source_table,source_id,evidence)
                VALUES ('REFRESH000001','active_subdivision',0.3,'fixture','new-source','{}')
            """,
                ),
                (
                    "nearby_subdivision",
                    """
                INSERT INTO public.development_signals
                  (pidn,signal_key,signal_weight,source_table,evidence)
                SELECT 'REFRESH000001','nearby_subdivision',0.08,'fixture','{}'
                WHERE NOT EXISTS (SELECT 1 FROM public.development_signals
                    WHERE pidn='REFRESH000001' AND signal_key='active_subdivision')
            """,
                ),
            ],
        )
        if fail_publication:
            monkeypatch.setattr(module, "RETRACT_STALE_EVIDENCE_QUERY", "SELECT 1/0")
    else:
        original_build = module.build_rebuild_sql
        monkeypatch.setattr(
            module,
            "build_rebuild_sql",
            lambda: "/* computation probe */\n" + original_build(),
        )
        if fail_publication:
            monkeypatch.setattr(module, "APPEND_HISTORY_SQL", "SELECT 1/0")
    try:
        with writer.cursor() as cur:
            cur.execute(
                "TRUNCATE public.development_signals, public.development_momentum"
            )
            cur.execute(
                "DELETE FROM public.development_momentum_history WHERE pidn=%s", (pidn,)
            )
            cur.execute(
                """
                INSERT INTO public.development_signals
                  (pidn,signal_key,signal_weight,source_table,source_id,evidence)
                VALUES (%s,'growth_area',0.02,'fixture','old-source','{}')
            """,
                (pidn,),
            )
            cur.execute(
                "INSERT INTO public.development_momentum (pidn,score) VALUES (%s,7)",
                (pidn,),
            )
            cur.execute(
                """
                INSERT INTO public.development_momentum_history
                  (pidn,computed_at,score,opportunity_score,site_readiness_score,signal_count,score_version)
                VALUES (%s,NOW()-INTERVAL '2 days',5,0,50,1,7)
            """,
                (pidn,),
            )
        writer.commit()
        with build_asset_context() as context:
            if fail_publication:
                with pytest.raises(psycopg2.errors.DivisionByZero):
                    asset.node_def.compute_fn.decorated_fn(context, ProbeDatabase())
            else:
                asset.node_def.compute_fn.decorated_fn(context, ProbeDatabase())
        assert probed == [True]
        with reader.cursor() as cur:
            if kind == "signals":
                cur.execute(
                    "SELECT source_id FROM public.development_signals WHERE pidn=%s",
                    (pidn,),
                )
                assert cur.fetchall() == [
                    ("old-source" if fail_publication else "new-source",)
                ]
            else:
                cur.execute(
                    "SELECT score,previous_score,is_new FROM public.development_momentum WHERE pidn=%s",
                    (pidn,),
                )
                assert cur.fetchone() == (
                    (7, None, False) if fail_publication else (2, 5, False)
                )
    finally:
        resource.teardown_after_execution(None)
        writer.rollback()
        with writer.cursor() as cur:
            cur.execute("DELETE FROM public.development_signals WHERE pidn=%s", (pidn,))
            cur.execute(
                "DELETE FROM public.development_momentum WHERE pidn=%s", (pidn,)
            )
            cur.execute(
                "DELETE FROM public.development_momentum_history WHERE pidn=%s", (pidn,)
            )
        writer.commit()
        writer.close()
        reader.close()


@pytest.mark.integration
def test_retired_meta_tables_are_absent() -> None:
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
                        "meta.source_candidates",
                        "meta.source_observations",
                        "meta.source_registry",
                    ],
                ),
            )
            assert cursor.fetchall() == [(None,)] * 6
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
                (
                    [
                        "meta.source_rights",
                        "meta.source_rights_audit",
                        "meta.municipality_source_rights",
                        "meta.municipality_source_audit",
                        "meta.municipality_source_health",
                        "meta.job_run_status",
                        "staging.economic_development_parks",
                        "staging.environmental_diligence_sites",
                        "staging.local_traffic_counts",
                        "staging.soils",
                        "staging.zoning_overlays",
                    ],
                ),
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
                "policy_version",
                "policy_fingerprint",
                "policy_snapshot",
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
                "paused": 2,
            }

            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM meta.source_rights
                    WHERE source_key = 'county_scout'
                )
                """
            )
            assert cursor.fetchone()[0] is False

            cursor.execute(
                """
                SELECT rights_status, COUNT(*)
                FROM meta.municipality_source_rights
                GROUP BY rights_status
                ORDER BY rights_status
                """
            )
            # Revision 077 adds eight reviewed replacement bodies while the
            # original misidentified source keys remain paused.
            assert dict(cursor.fetchall()) == {
                "conditional": 112,
                "paused": 18,
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
                "railroad_borough_council": "RAILROAD BORO",
                "paradise_twp_board_of_supervisors": "PARADISE TWP",
                "paradise_twp_planning_commission": "PARADISE TWP",
                "paradise_twp_zoning_hearing_board": "PARADISE TWP",
                "penn_twp_board_of_supervisors": "PENN TWP",
                "penn_twp_planning_commission": "PENN TWP",
                "penn_twp_zoning_hearing_board": "PENN TWP",
                "windsor_twp_board_of_supervisors": "WINDSOR TWP",
                "windsor_twp_planning_commission": "WINDSOR TWP",
                "jackson_twp_board_of_supervisors": "JACKSON TWP",
                "shrewsbury_twp_board_of_supervisors": "SHREWSBURY TWP",
                "west_manheim_twp_board_of_supervisors": "WEST MANHEIM TWP",
                "west_manheim_twp_planning_commission": "WEST MANHEIM TWP",
                "west_manheim_twp_zoning_hearing_board": "WEST MANHEIM TWP",
                "west_york_borough_council": "WEST YORK BORO",
            }

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM meta.municipality_source_rights
                WHERE source_key IN (
                    'franklintown_borough_council',
                    'newberry_twp_board_of_supervisors',
                    'washington_twp_board_of_supervisors'
                )
                  AND rights_status = 'conditional'
                  AND acquisition_allowed
                  AND raw_retention_allowed
                  AND derived_product_allowed
                  AND NOT raw_export_allowed
                  AND terms_review_status = 'reviewed_risk_accepted'
                  AND evidence->>'robots_unavailable_risk_accepted' = 'true'
                  AND allowed_methods = ARRAY['official_document_direct']::TEXT[]
                  AND 'https://img1.wsimg.com' = ANY(allowed_origins)
                """
            )
            assert cursor.fetchone()[0] == 3

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
def test_job_run_status_preserves_last_success_after_failure() -> None:
    from datetime import datetime

    connection = _connect()
    database = _IntegrationDatabase(connection)
    job_name = "schema_integration_refresh"
    first_finished = datetime(2026, 8, 30, 10, tzinfo=UTC)
    second_finished = datetime(2026, 8, 30, 11, tzinfo=UTC)
    try:
        record_job_run_status(
            database,
            job_name=job_name,
            run_id="schema-success",
            status="success",
            started_at=datetime(2026, 8, 30, 9, tzinfo=UTC),
            finished_at=first_finished,
        )
        record_job_run_status(
            database,
            job_name=job_name,
            run_id="schema-failure",
            status="failure",
            started_at=datetime(2026, 8, 30, 10, 30, tzinfo=UTC),
            finished_at=second_finished,
            error_message="test failure",
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT run_id, status, finished_at, last_success_at, error_message
                FROM meta.job_run_status
                WHERE job_name = %s
                """,
                (job_name,),
            )
            assert cursor.fetchone() == (
                "schema-failure",
                "failure",
                second_finished,
                first_finished,
                "test failure",
            )
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM meta.job_run_status WHERE job_name = %s",
                (job_name,),
            )
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
                "SELECT policy_version FROM meta.municipality_source_rights WHERE source_key='hanover_borough_council'"
            )
            current_policy_version = cursor.fetchone()[0]
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
                True,
                "authorized",
                current_policy_version,
                64,
                "hanover_borough_council",
            )
    finally:
        connection.close()


@pytest.mark.integration
def test_godaddy_municipality_sources_authorize_with_bounded_origin() -> None:
    connection = _connect()
    run_id = "schema-integration-godaddy-municipality-authorization"
    expected_source_keys = {
        "franklintown_borough_council",
        "newberry_twp_board_of_supervisors",
        "washington_twp_board_of_supervisors",
    }
    try:
        entries = tuple(
            source
            for source in get_county_config().municipality_websites
            if source[0]
            in {
                "Franklintown Borough Council",
                "Newberry Twp Board of Supervisors",
                "Washington Twp Board of Supervisors",
            }
        )
        authorizations = authorize_municipality_sources(
            _IntegrationDatabase(connection),
            entries=entries,
            acquisition_method="official_document_direct",
            asset_key="schema_integration",
            dagster_run_id=run_id,
        )

        assert set(authorizations) == expected_source_keys
        for authorization in authorizations.values():
            assert authorization.raw_retention_allowed
            assert authorization.derived_product_allowed
            assert not authorization.raw_export_allowed
            assert authorization.robots_unavailable_risk_accepted
            assert "https://img1.wsimg.com" in authorization.allowed_origins
    finally:
        connection.close()


@pytest.mark.integration
def test_site_readiness_score_rebuild_uses_replacement_signals() -> None:
    from countyiq.assets.enrichment.development_momentum import development_momentum
    from countyiq.resources.database import DatabaseResource
    from dagster import build_asset_context

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
            dbname=os.environ.get("DATABASE_NAME", "countyiq_test"),
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
            # v7: momentum = park 0.18 + growth 0.02 = 20; opportunity uses the
            # back-tested weights park 0.22 + growth 0.05 + soil -0.03 = 24;
            # readiness = 50 + 25 + 10 - 15 = 70.
            assert cursor.fetchone() == (20, 24, 70, True, 7)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE public.development_momentum")
            cursor.execute("TRUNCATE public.development_signals RESTART IDENTITY")
            cursor.execute(
                "DELETE FROM public.development_momentum_history WHERE pidn = %s",
                (pidn,),
            )
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


@pytest.mark.integration
def test_wrong_county_sources_cannot_be_acquired_or_used_in_products():
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT rights_status, acquisition_allowed, derived_product_allowed,
                       raw_export_allowed, cardinality(allowed_methods)
                FROM meta.municipality_source_rights
                WHERE source_key IN (
                    'penn_twp_board_of_supervisors', 'penn_twp_planning_commission',
                    'penn_twp_zoning_hearing_board', 'paradise_twp_board_of_supervisors',
                    'paradise_twp_planning_commission', 'paradise_twp_zoning_hearing_board'
                )
            """)
            rows = cursor.fetchall()
            assert len(rows) == 6
            assert all(row == ("paused", False, False, False, 0) for row in rows)
    finally:
        connection.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    "policy",
    [
        "allowed",
        "paused",
        "expired",
        "denied",
        "unknown",
        "global_paused",
        "unreviewed",
        "review_required",
        "quarantined",
    ],
)
def test_retained_proceedings_context_obeys_current_policy(policy):
    from psycopg2.extras import Json

    from countyiq.lib.intelligence_common import (
        PROCEEDINGS_FOR_PARCEL_QUERY,
        PROCEEDINGS_FOR_ENTITY_QUERY,
    )
    from countyiq.lib.proceeding_quality import VERSION

    connection = _connect()
    try:
        with connection.cursor() as cursor:
            body = (
                "Hanover Borough Council"
                if policy != "unknown"
                else "Unknown review body"
            )
            # Attribution now requires a current parcel in the source jurisdiction.
            cursor.execute("""
                INSERT INTO staging.parcels (pidn, propadr, municipality)
                SELECT '999999999999', '123 FIXTURE ST', municipality_name
                FROM meta.municipality_source_rights
                WHERE source_key='hanover_borough_council'
            """)
            cursor.execute(
                """
                UPDATE meta.source_rights SET rights_status=%s, derived_product_allowed=TRUE,
                    review_due_on=CURRENT_DATE+30 WHERE source_key='public_proceedings'
            """,
                ("paused" if policy == "global_paused" else "conditional",),
            )
            cursor.execute(
                """
                UPDATE meta.municipality_source_rights SET rights_status=%s,
                    derived_product_allowed=%s, review_due_on=CURRENT_DATE+%s
                WHERE source_key='hanover_borough_council'
            """,
                (
                    "paused" if policy == "paused" else "conditional",
                    policy != "denied",
                    -1 if policy == "expired" else 30,
                ),
            )
            cursor.execute(
                """
                INSERT INTO staging.public_proceedings
                    (body_name,meeting_date,proceeding_type,raw_text,source_url,document_url,content_hash)
                VALUES (%s,CURRENT_DATE,'borough_council','Review fixture','https://example.test/review',
                    'https://example.test/review.pdf','context-policy-fixture') RETURNING id
            """,
                (body,),
            )
            proceeding_id = cursor.fetchone()[0]
            cursor.execute(
                "UPDATE staging.public_proceedings SET metadata_quality=%s::jsonb WHERE id=%s",
                (
                    Json(
                        {
                            "status": policy
                            if policy
                            in {"unreviewed", "review_required", "quarantined"}
                            else "ready",
                            "version": VERSION,
                        }
                    ),
                    proceeding_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO staging.proceeding_extractions
                    (proceeding_id,extraction_type,applicant_name,parcel_reference,decision,
                     supporting_text,extraction_confidence,model_used,source_url)
                VALUES (%s,'variance_request','Policy Fixture LLC','999999999999',
                    'pending','Fixture only',0.9,'fixture','https://example.test/review')
                RETURNING id
            """,
                (proceeding_id,),
            )
            extraction_id = cursor.fetchone()[0]
            for query, params in (
                (PROCEEDINGS_FOR_PARCEL_QUERY, {"pidn": "999999999999"}),
                (PROCEEDINGS_FOR_ENTITY_QUERY, {"names": ["Policy Fixture LLC"]}),
            ):
                cursor.execute(query, params)
                ids = {row[0] for row in cursor.fetchall()}
                assert (extraction_id in ids) is (policy == "allowed")
            from countyiq.assets.enrichment.proceeding_extraction import (
                PENDING_PROCEEDINGS_QUERY,
            )
            from countyiq.assets.enrichment.intelligence_events import (
                _DEVELOPMENT_EVENTS_SQL,
            )

            cursor.execute(PENDING_PROCEEDINGS_QUERY)
            assert (proceeding_id in {row[0] for row in cursor.fetchall()}) is (
                policy == "allowed"
            )
            cursor.execute(_DEVELOPMENT_EVENTS_SQL)
            assert (extraction_id in {row[0] for row in cursor.fetchall()}) is (
                policy == "allowed"
            )

    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_model_context_snapshot_is_consistent_read_only_and_released():
    import uuid
    from psycopg2 import sql
    from countyiq.resources.database import DatabaseResource

    writer = _connect()  # Enforces the dedicated test database guard.
    writer.autocommit = True
    resource = DatabaseResource(
        host=writer.info.host,
        port=writer.info.port,
        dbname=writer.info.dbname,
        user=writer.info.user,
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )
    resource.setup_for_execution(None)
    table = sql.Identifier("public", "review_snapshot_" + uuid.uuid4().hex)
    created = False
    try:
        with writer.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE TABLE {} (value integer NOT NULL)").format(table)
            )
            created = True
            cursor.execute(sql.SQL("INSERT INTO {} VALUES (1)").format(table))
        with resource.read_snapshot() as cursor:
            cursor.execute(sql.SQL("SELECT value FROM {}").format(table))
            assert cursor.fetchone()["value"] == 1
            with writer.cursor() as concurrent:
                concurrent.execute(sql.SQL("UPDATE {} SET value=2").format(table))
            cursor.execute(sql.SQL("SELECT value FROM {}").format(table))
            assert cursor.fetchone()["value"] == 1
            cursor.execute("SHOW transaction_read_only")
            assert next(iter(cursor.fetchone().values())) == "on"
        assert resource._get_conn().autocommit is True
        with resource.read_snapshot() as cursor:
            cursor.execute(sql.SQL("SELECT value FROM {}").format(table))
            assert cursor.fetchone()["value"] == 2
        with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
            with resource.read_snapshot() as cursor:
                cursor.execute(sql.SQL("UPDATE {} SET value=3").format(table))
        assert resource._get_conn().autocommit is True
        with resource.read_snapshot() as cursor:
            cursor.execute(sql.SQL("SELECT value FROM {}").format(table))
            assert cursor.fetchone()["value"] == 2
    finally:
        resource.teardown_after_execution(None)
        if created:
            with writer.cursor() as cursor:
                cursor.execute(sql.SQL("DROP TABLE {}").format(table))
        writer.close()


@pytest.mark.integration
def test_parcel_brief_context_matches_database_fingerprint():
    import uuid
    from psycopg2.extras import Json, RealDictCursor
    from countyiq.lib.pass3_brief_generation import (
        gather_brief_context,
        build_brief_generation_prompt,
    )

    pidn = str(uuid.uuid4().int % 10**12).zfill(13)
    owner = "Review context " + uuid.uuid4().hex
    connection = _connect()
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO staging.parcels
                  (pidn,owner_full,propadr,aprtotal,acres,price,municipality)
                VALUES (%s,%s,'Review address',123456,2.5,100000,'Review municipality')
            """,
                (pidn, owner),
            )
            for key in ("active_subdivision", "vacancy"):
                cursor.execute(
                    """
                    INSERT INTO public.evidence
                        (pidn, signal_key, claim, evidence_data, validation_status,
                         adjusted_significance, validation_reasoning, cross_references)
                    VALUES (%s,%s,'invented claim',%s,'confirmed','high',
                            'invented approval',%s)
                """,
                    (
                        pidn,
                        key,
                        Json(
                            {
                                "plan_title": "Recorded Plan",
                                "prop_lots": 1,
                                "prop_du": 0,
                                "buyer_is_llc": False,
                                "months_since_received": 2,
                            }
                        ),
                        Json(
                            [
                                {
                                    "source": "planning",
                                    "detail": "invented 900-unit approval",
                                }
                            ]
                        ),
                    ),
                )
            context = gather_brief_context(cursor, pidn)
            assert context["parcel"]["owner"] == owner
            assert context["parcel"]["assessed_value"] == 123456
            assert context["portfolio"]["portfolio_count"] == 1
            assert context["portfolio"]["portfolio_value"] == 123456
            assert context["portfolio"]["portfolio_delinquency"] == 0
            assert context["entity"] == {"found": False}
            assert [s["signal_key"] for s in context["validated_signals"]] == [
                "active_subdivision"
            ]
            prompt = build_brief_generation_prompt(context)
            assert "plan_title=Recorded Plan" in prompt
            assert "prop_lots=1" in prompt
            assert "prop_du=0" in prompt
            assert "buyer_is_llc=False" in prompt
            assert "invented" not in prompt
            assert "months_since_received" not in prompt
            cursor.execute(
                "SELECT meta.parcel_brief_source_fingerprint(%s) AS fingerprint",
                (pidn,),
            )
            assert context["source_fingerprint"] == cursor.fetchone()["fingerprint"]
            cursor.execute(
                "UPDATE staging.parcels SET aprtotal=123457 WHERE pidn=%s", (pidn,)
            )
            updated = gather_brief_context(cursor, pidn)
            assert updated["source_fingerprint"] != context["source_fingerprint"]
            assert updated["portfolio"]["portfolio_value"] == 123457
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_shared_retraction_removes_changed_and_missing_but_retains_aged_evidence():
    from psycopg2.extras import Json
    from countyiq.lib.intelligence_common import (
        RETRACT_STALE_EVIDENCE_QUERY,
        VOLATILE_EVIDENCE_KEYS,
    )

    connection = _connect()
    pidn = "9090000000009"
    try:
        with connection.cursor() as cursor:
            for key in ("missing", "changed", "aged", "vacancy"):
                cursor.execute(
                    """
                    INSERT INTO public.evidence (pidn,signal_key,claim,evidence_data,validation_status,adjusted_significance)
                    VALUES (%s,%s,'fixture',%s,'confirmed','high')
                """,
                    (pidn, key, Json({"fact": 1, "months_since_sale": 1})),
                )
            for key, fact in (("changed", 2), ("aged", 1), ("vacancy", 1)):
                cursor.execute(
                    """
                    INSERT INTO public.development_signals (pidn,signal_key,signal_weight,source_table,evidence)
                    VALUES (%s,%s,1,'fixture',%s)
                """,
                    (pidn, key, Json({"fact": fact, "months_since_sale": 2})),
                )
            cursor.execute(
                RETRACT_STALE_EVIDENCE_QUERY, {"volatile": list(VOLATILE_EVIDENCE_KEYS)}
            )
            removed = {key for parcel, key in cursor.fetchall() if parcel == pidn}
            assert removed == {"missing", "changed", "vacancy"}
            cursor.execute(
                "SELECT signal_key FROM public.evidence WHERE pidn=%s", (pidn,)
            )
            assert cursor.fetchall() == [("aged",)]
            cursor.execute(
                "SELECT COUNT(*) FROM public.development_signals WHERE pidn=%s AND signal_key='vacancy'",
                (pidn,),
            )
            assert cursor.fetchone()[0] == 1
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_footprint_context_does_not_create_a_paid_validation_candidate():
    import uuid
    from psycopg2.extras import RealDictCursor
    from countyiq.assets.enrichment.signal_validation_batched import (
        PARCELS_NEEDING_VALIDATION_QUERY,
        PARCELS_NEEDING_VALIDATION_FAST_QUERY,
    )
    from countyiq.lib.pass2_batched_validation import (
        gather_parcel_batch_context,
        build_batched_signal_prompt,
    )

    pidns = [str(uuid.uuid4().int % 10**12).zfill(13) for _ in range(2)]
    connection = _connect()
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            for index, pidn in enumerate(pidns):
                cursor.execute(
                    "INSERT INTO staging.parcels (pidn,owner_full) VALUES (%s,'Policy test owner')",
                    (pidn,),
                )
                keys = ["active_subdivision", "vacancy", "new_screen"]
                if index:
                    keys.append("ownership_change")
                for key in keys:
                    cursor.execute(
                        """
                        INSERT INTO public.development_signals
                            (pidn,signal_key,signal_weight,source_table,evidence)
                        VALUES (%s,%s,1,'fixture','{"structure_count":0}'::jsonb)
                    """,
                        (pidn, key),
                    )
            for query in (
                PARCELS_NEEDING_VALIDATION_QUERY,
                PARCELS_NEEDING_VALIDATION_FAST_QUERY,
            ):
                cursor.execute(query)
                selected = {row["pidn"] for row in cursor.fetchall()} & set(pidns)
                assert selected == {pidns[1]}
            context = gather_parcel_batch_context(cursor, pidns[1])
            assert {s["signal_key"] for s in context["signals"]} == {
                "active_subdivision",
                "ownership_change",
            }
            assert {s["signal_key"] for s in context["context_signals"]} == {
                "vacancy",
                "new_screen",
            }
            prompt = build_batched_signal_prompt(context)
            assert "context:vacancy" in prompt
            assert "structure_count=0" in prompt
            assert "2 signals" in prompt
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_validation_publication_rejects_stale_context_and_locks_signal_replacement():
    from psycopg2.extras import Json
    from countyiq.resources.database import DatabaseResource
    from countyiq.lib.pass2_batched_validation import (
        gather_parcel_batch_context,
        pass2_source_fingerprint,
        assert_current_validation_context,
        StaleValidationContext,
    )

    writer = _connect()
    writer.autocommit = True
    resource = DatabaseResource(
        host=writer.info.host,
        port=writer.info.port,
        dbname=writer.info.dbname,
        user=writer.info.user,
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )
    resource.setup_for_execution(None)
    pidn = "9090000000010"
    created = False
    try:
        with writer.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.development_signals
                  (pidn,signal_key,signal_weight,source_table,evidence)
                VALUES (%s,'growth_area',1,'fixture',%s)
            """,
                (pidn, Json({"fact": 1})),
            )
            created = True
        with resource.read_snapshot() as cursor:
            original_hash = pass2_source_fingerprint(
                gather_parcel_batch_context(cursor, pidn)
            )
        with writer.cursor() as cursor:
            cursor.execute(
                "UPDATE public.development_signals SET evidence=%s WHERE pidn=%s",
                (Json({"fact": 2}), pidn),
            )
        with pytest.raises(StaleValidationContext, match="publication deferred"):
            with resource.transaction(dict_rows=True) as cursor:
                assert_current_validation_context(cursor, pidn, original_hash)
        with resource.read_snapshot() as cursor:
            current_hash = pass2_source_fingerprint(
                gather_parcel_batch_context(cursor, pidn)
            )
        with resource.transaction(dict_rows=True) as cursor:
            assert_current_validation_context(cursor, pidn, current_hash)
            writer.autocommit = False
            try:
                with writer.cursor() as concurrent:
                    # TRUNCATE uses this lock: replacement cannot interleave
                    # between the publication check and evidence writes.
                    with pytest.raises(psycopg2.errors.LockNotAvailable):
                        concurrent.execute(
                            "LOCK TABLE public.development_signals IN ACCESS EXCLUSIVE MODE NOWAIT"
                        )
            finally:
                writer.rollback()
                writer.autocommit = True
        writer.autocommit = False
        try:
            with writer.cursor() as cursor:
                cursor.execute(
                    "LOCK TABLE public.development_signals IN ACCESS EXCLUSIVE MODE NOWAIT"
                )
        finally:
            writer.rollback()
            writer.autocommit = True
        assert resource._get_conn().autocommit is True
    finally:
        resource.teardown_after_execution(None)
        if created:
            with writer.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM public.development_signals WHERE pidn=%s", (pidn,)
                )
        writer.close()


@pytest.mark.integration
def test_proceeding_address_match_requires_number_and_unique_parcel():
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            municipality = "Review address specificity"
            for pidn, address in (
                ("9090000000021", "ORWIG RD"),
                ("9090000000022", "123 N MAIN ST"),
                ("9090000000023", "127 N WEST ST"),
                ("9090000000024", "127 N WEST ST"),
            ):
                cursor.execute(
                    "INSERT INTO staging.parcels (pidn,propadr,municipality) VALUES (%s,%s,%s)",
                    (pidn, address, municipality),
                )
            for reference, expected in (
                ("Orwig Road", None),
                ("Intersection of Orwig Road and Main Street", None),
                ("123 North Main Street, Suite 2", "9090000000022"),
                ("127 North West Street", None),
                ("0 Orwig Road", None),
            ):
                cursor.execute(
                    "SELECT public.proceeding_address_pidn(%s,%s)",
                    (reference, municipality),
                )
                assert cursor.fetchone()[0] == expected
            cursor.execute(
                "SELECT public.proceeding_address_pidn('123 N Main St','Other municipality')"
            )
            assert cursor.fetchone()[0] is None
            # Exercise the actual event query too: a broad location remains a
            # project-level record, without assigning parcels to it.
            cursor.execute(
                """
                UPDATE meta.municipality_source_rights SET municipality_name=%s,
                    rights_status='conditional',derived_product_allowed=TRUE,
                    review_due_on=CURRENT_DATE+30 WHERE source_key='hanover_borough_council'
            """,
                (municipality,),
            )
            cursor.execute("""
                INSERT INTO staging.public_proceedings
                  (body_name,meeting_date,proceeding_type,raw_text,source_url,
                   document_url,content_hash,metadata_quality)
                VALUES ('Hanover Borough Council',CURRENT_DATE,'borough_council',
                        'Fixture only','https://example.test','https://example.test/fixture.pdf',
                        'specific-address-fixture','{"status":"ready"}') RETURNING id
            """)
            proceeding_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO staging.proceeding_extractions
                  (proceeding_id,extraction_type,applicant_name,parcel_reference,
                   supporting_text,extraction_confidence,model_used,source_url)
                VALUES (%s,'variance_request','Specific Address LLC','Orwig Road',
                        'Fixture only',0.9,'fixture','https://example.test') RETURNING id
            """,
                (proceeding_id,),
            )
            extraction_id = cursor.fetchone()[0]
            from countyiq.assets.enrichment.intelligence_events import (
                _DEVELOPMENT_EVENTS_SQL,
            )
            from countyiq.lib.intelligence_common import PROCEEDINGS_FOR_PARCEL_QUERY

            for reference, expected_pidns in (
                ("Orwig Road", []),
                ("123 North Main Street", ["9090000000022"]),
                ("127 North West Street", []),
            ):
                cursor.execute(
                    "UPDATE staging.proceeding_extractions SET parcel_reference=%s WHERE id=%s",
                    (reference, extraction_id),
                )
                cursor.execute(_DEVELOPMENT_EVENTS_SQL)
                columns = [column.name for column in cursor.description]
                event = next(
                    dict(zip(columns, row))
                    for row in cursor.fetchall()
                    if row[0] == extraction_id
                )
                assert event["related_pidns"] == expected_pidns
                for pidn in ("9090000000021", "9090000000022", "9090000000023"):
                    cursor.execute(PROCEEDINGS_FOR_PARCEL_QUERY, {"pidn": pidn})
                    assert (extraction_id in {row[0] for row in cursor.fetchall()}) == (
                        pidn in expected_pidns
                    )
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    "event_type",
    [
        "policy_action",
        "recommendation",
        "update",
        "withdrawn",
        "removed",
        "scoped_decision",
    ],
)
def test_current_municipal_event_types_can_be_persisted(event_type):
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.intelligence_events
                    (event_key,source_kind,source_record_id,category,event_type,title,
                     what_happened,why_it_matters,what_happens_next,detected_at,interpretation_kind)
                VALUES (%s,'proceeding_extraction','schema-fixture','development',%s,
                        'Schema fixture','Source records an action','Verify scope',
                        'Check the source',NOW(),'llm')
                RETURNING event_type
            """,
                ("schema-contract:" + event_type, event_type),
            )
            assert cursor.fetchone()[0] == event_type
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
@pytest.mark.parametrize("caller_threshold", ["0.1", "0.9"])
def test_indexed_candidates_preserve_pairs_and_caller_settings(caller_threshold):
    connection = _connect()
    municipalities = ["CANDIDATE TEST A", "CANDIDATE TEST B"]
    try:
        with connection.cursor() as cursor:
            names = ["SMITH JOHN", "SMITH JOHN", "SMITH JOHN JR", "A", "A B", "", None]
            for index, name in enumerate(names):
                cursor.execute(
                    "INSERT INTO staging.parcels (pidn, owner_full, municipality) VALUES (%s,%s,%s)",
                    (f"candidate-test-{index}", name, municipalities[0]),
                )
            cursor.execute(
                "INSERT INTO staging.parcels (pidn, owner_full, municipality, valid_to) VALUES (%s,%s,%s,%s)",
                (
                    "candidate-expired",
                    "SMITH JOHN SR",
                    municipalities[0],
                    datetime.now(UTC),
                ),
            )
            cursor.execute(
                "INSERT INTO staging.parcels (pidn, owner_full, municipality) VALUES (%s,%s,%s)",
                ("candidate-other-town", "SMITH JOHN II", municipalities[1]),
            )
            cursor.execute("SELECT similarity('A','A B')")
            assert cursor.fetchone()[0] == 0.5
            cursor.execute(
                "SELECT set_config('pg_trgm.similarity_threshold',%s,true)",
                (caller_threshold,),
            )
            cursor.execute(
                """
                SELECT DISTINCT a.owner_full, b.owner_full, a.municipality,
                    similarity(a.owner_full,b.owner_full)
                FROM staging.parcels a JOIN staging.parcels b
                  ON a.municipality=b.municipality AND a.owner_full<b.owner_full
                  AND similarity(a.owner_full,b.owner_full)>0.5
                WHERE a.valid_to IS NULL AND b.valid_to IS NULL
                  AND a.owner_full IS NOT NULL AND b.owner_full IS NOT NULL
                  AND a.owner_full<>'' AND b.owner_full<>''
                  AND a.municipality = ANY(%s)
                ORDER BY 1,2,3,4
            """,
                (municipalities,),
            )
            original = cursor.fetchall()
            assert len(original) == 1
            cursor.execute(
                """
                SELECT * FROM public.compute_entity_candidate_pairs()
                WHERE municipality = ANY(%s) ORDER BY 1,2,3,4
            """,
                (municipalities,),
            )
            assert cursor.fetchall() == original
            cursor.execute("SHOW pg_trgm.similarity_threshold")
            assert cursor.fetchone()[0] == caller_threshold
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_pipeline_role_can_refresh_candidates_without_owning_source_tables():
    from psycopg2 import sql

    connection = _connect()
    role = os.environ.get("DATABASE_PIPELINE_USER", "countyiq_pipeline_test")
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT pg_get_userbyid(relowner) FROM pg_class
                WHERE oid='staging.parcels'::regclass
            """)
            assert cursor.fetchone()[0] != role
            cursor.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
            cursor.execute("REFRESH MATERIALIZED VIEW public.entity_candidate_pairs")
            cursor.execute("SELECT count(*) FROM public.entity_candidate_pairs")
            assert cursor.fetchone()[0] >= 0
    finally:
        connection.rollback()
        connection.close()
