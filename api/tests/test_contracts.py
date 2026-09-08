from __future__ import annotations

import pytest

from api.tests.conftest import TEST_MUNICIPALITY, TEST_PIDN


def test_health_route(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_route_checks_database(client):
    response = client.get("/api/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_uses_dedicated_read_only_database_role(client):
    from api.lib.database import get_cursor

    with get_cursor() as cur:
        cur.execute(
            "SELECT current_user AS username, "
            "current_setting('transaction_read_only') AS read_only, "
            "current_setting('jit') AS jit"
        )
        row = cur.fetchone()

    assert row == {"username": "countyiq_api_test", "read_only": "on", "jit": "off"}


def test_ops_health_exposes_source_policy_review_state(client):
    from api.lib.auth import require_operator
    from api.main import app

    app.dependency_overrides[require_operator] = lambda: None
    try:
        response = client.get("/api/ops/health")
    finally:
        app.dependency_overrides.pop(require_operator, None)

    assert response.status_code == 200
    sources = response.json()["sources"]
    governance = sources["source_governance"]
    assert governance["configured_count"] == 11
    assert governance["active_count"] == 9
    assert governance["conditional_count"] == 4
    assert governance["paused_count"] == 2
    assert governance["overdue_count"] == 0
    assert governance["next_review_on"] == "2026-11-27"

    parcels = sources["parcels"]
    assert parcels["status"] == "green"
    assert parcels["status_reason"] == "healthy"
    assert parcels["last_run_status"] == "success"
    assert parcels["stale"] is False
    assert parcels["freshness_due_at"] is not None

    assert "pa_open_data" not in sources

    integrity = response.json()["intelligence_integrity"]
    assert integrity["status"] == "red"
    assert integrity["status_reason"] == "projection_unlinked"
    assert integrity["unlinked_projection_count"] > 0
    assert integrity["projection_mismatch_count"] == 0

    municipal = sources["municipal_proceedings"]
    assert (
        municipal["configured_count"] == 123
    )  # 122 configured sources plus the synthetic fixture body.
    assert municipal["active_count"] == 104
    assert municipal["healthy_count"] == 0
    assert municipal["blocked_count"] == 18
    assert municipal["unchecked_count"] == 104
    assert municipal["stale_count"] == 0
    assert municipal["record_count"] == 0
    assert municipal["status_reason"] == "run_not_observed"
    assert municipal["last_run_status"] == "unknown"


def test_address_search_does_not_surface_owner_name(client):
    response = client.get("/api/search", params={"q": "1 Main St"})

    assert response.status_code == 200
    parcel_results = [
        result
        for result in response.json()["results"]
        if result["result_type"] == "parcel"
    ]
    assert parcel_results
    assert parcel_results[0]["title"] == "1 Main St"
    assert "Alpha Holdings LLC" not in str(parcel_results)


def test_property_report_contract_includes_intelligence_layers(client):
    response = client.get(f"/api/parcels/{TEST_PIDN}")

    assert response.status_code == 200
    payload = response.json()

    assert payload["parcel"]["pidn"] == TEST_PIDN
    assert isinstance(payload["parcel"]["owner_id"], int)
    assert payload["parcel"]["owner_full"] == "Alpha Holdings LLC"
    assert payload["parcel"]["heatsys"] == 1
    assert payload["parcel"]["fuel"] == 2

    assert payload["tax_delinquency"]["is_delinquent"] is True
    assert payload["tax_delinquency"]["detail_available"] is False
    assert payload["tax_delinquency"]["total_owed"] is None
    assert payload["tax_delinquency"]["records"] == []

    assert payload["flood_zone"] == {
        "in_flood_zone": True,
        "zone": "AE",
        "sfha": True,
        "overlap_pct": 100.0,
    }
    assert payload["soil_profile"] == {
        "mapped_coverage_pct": 0,
        "units": [],
        "considerations": [],
        "source_record_ids": [],
        "source_url": None,
    }
    assert payload["structures"]["count"] == 1
    assert payload["structures"]["likely_vacant"] is False
    assert payload["zoning"]["code"] == "HC"
    assert payload["zoning"]["name"] == "Highway Commercial"
    assert payload["zoning"]["general_name"] == "Commercial"
    evidence_by_kind = {item["source_kind"]: item for item in payload["evidence"]}
    assert evidence_by_kind["official_zoning_layer"]["details"]["code"] == "HC"
    assert evidence_by_kind["official_parcel_record"]["source_record_id"] == TEST_PIDN
    assert (
        evidence_by_kind["official_parcel_record"]["url"]
        == "https://example.com/parcels/1"
    )
    assert evidence_by_kind["official_flood_layer"]["details"]["zones"] == ["AE"]
    assert (
        evidence_by_kind["official_flood_layer"]["details"]["parcel_overlap_pct"]
        == 100.0
    )
    assert (
        evidence_by_kind["official_structure_layer"]["details"]["footprint_count"] == 1
    )
    assert evidence_by_kind["official_tax_listing"]["details"] == {
        "delinquency_signal": True
    }

    assert payload["development_momentum"]["score"] == 72
    assert payload["development_momentum"]["opportunity_score"] == 64
    # Owner identity is public record: the prior owner named in the evidence
    # and the validation reasoning is served as-is.
    assert "Private Person" in str(payload["development_momentum"])
    assert payload["development_momentum"]["reason_signals"]

    # Generated prose is served under the ordinary derived-product use.
    assert payload["parcel_brief"]["recommendation"] == "watch"
    assert payload["parcel_brief"]["citations"] == ["growth_area", "ownership_change"]
    assert payload["parcel_brief"]["citation_evidence"]
    assert payload["intelligence_summary"]["signals_validated_count"] == 2
    # The seeded, unexpired Pass 4 narrative has no versioned dependencies.
    # Its presence in storage cannot certify it for the property report.
    assert payload["related_narratives"] == []

    match_types = {row["match_type"] for row in payload["linked_proceedings"]}
    assert match_types == {"pidn", "address"}
    assert all(
        row["applicant_name"] == "Alpha Holdings LLC"
        for row in payload["linked_proceedings"]
    )
    assert all(row["supporting_text"] for row in payload["linked_proceedings"])
    assert all(row["evidence"]["document_url"] for row in payload["linked_proceedings"])
    assert all(
        row["evidence"]["excerpt"] == row["supporting_text"]
        for row in payload["linked_proceedings"]
    )


def test_parcel_reference_normalizer_links_alphanumeric_pidns(client):
    """Migration 053: one rule for every proceeding-to-parcel linker."""
    from api.lib.database import get_cursor

    cases = {
        "20000NC0073A0": "20000NC0073A0",
        "20-000-NC-0073.A0": "20000NC0073A0",
        "Tax Map No. 20-000-NC-0073.A0-00000": "20000NC0073A0",
        "Parcel ID: 01-001-01-0002.00-00000": "0100101000200",
        "pidn # 0100101000200": "0100101000200",
        "1 Main St": "1MAINST",
        "   ": None,
    }
    with get_cursor() as cur:
        for raw, expected in cases.items():
            cur.execute("SELECT public.normalize_parcel_reference(%s) AS value", (raw,))
            assert cur.fetchone()["value"] == expected, raw


def test_municipality_profile_contract_is_page_complete(client):
    response = client.get(f"/api/municipalities/{TEST_MUNICIPALITY}")

    assert response.status_code == 200
    payload = response.json()

    assert payload["name"] == TEST_MUNICIPALITY
    assert payload["stats"] == {
        "parcel_count": 2,
        "total_assessed": 300000.0,
    }
    assert payload["delinquency"] == {
        "delinquent_parcels": 2,
        "total_delinquent": 2075.0,
        "oldest_delinquent_year": 2023,
        "delinquent_years": 2,
    }

    assert "top_delinquent_owners" not in payload

    assert len(payload["licenses"]) == 1
    assert payload["licenses"][0]["premises_name"] == "Main Street Tavern"


def test_feed_contract_combines_parcel_and_development_intelligence(client):
    all_response = client.get("/api/feed")
    development_response = client.get("/api/feed?category=development")
    approval_response = client.get("/api/feed?event_type=approval")
    parcel_response = client.get(f"/api/feed?pidns={TEST_PIDN}&category=parcel")
    project_response = client.get("/api/feed?project_keys=project:test-main-street")
    owner_id = client.get("/api/owners/top?limit=1").json()[0]["owner_id"]
    entity_response = client.get(f"/api/feed?entity_ids={owner_id}")
    invalid_response = client.get("/api/feed?event_type=not-a-real-event")
    # A plain municipality name matches both the county spelling stored on
    # parcel rows and the public-body spelling carried by extracted events.
    short_name_response = client.get(f"/api/feed?municipality={TEST_MUNICIPALITY}")
    long_name_response = client.get("/api/feed?municipality=Test Township")
    boosted_response = client.get("/api/feed?boost_municipalities=Test Township")

    assert all_response.status_code == 200
    assert short_name_response.status_code == 200
    assert long_name_response.status_code == 200
    assert boosted_response.status_code == 200
    assert len(short_name_response.json()["events"]) == 2
    assert len(long_name_response.json()["events"]) == 2
    assert all(
        "Watched subject" in event["importance_reasons"]
        for event in boosted_response.json()["events"]
    )
    assert development_response.status_code == 200
    assert approval_response.status_code == 200
    assert parcel_response.status_code == 200
    assert project_response.status_code == 200
    assert entity_response.status_code == 200
    assert invalid_response.status_code == 200

    all_payload = all_response.json()
    development_payload = development_response.json()
    approval_payload = approval_response.json()
    parcel_payload = parcel_response.json()
    project_payload = project_response.json()
    entity_payload = entity_response.json()
    invalid_payload = invalid_response.json()

    assert all_payload["limit"] == 50
    assert all_payload["has_more"] is False
    assert len(all_payload["events"]) == 2
    assert len(development_payload["events"]) == 1
    assert development_payload["events"][0]["category"] == "development"
    assert approval_payload["events"][0]["event_type"] == "approval"
    assert approval_payload["events"][0]["interpretation"]["kind"] == "llm"
    # Verified excerpts are public record and served with the receipt.
    assert approval_payload["events"][0]["sources"][0]["excerpt"] == (
        "The board approved the variance with conditions."
    )
    assert (
        approval_payload["events"][0]["sources"][0]["details"]["decision"] == "approved"
    )
    assert approval_payload["events"][0]["sources"][0]["source_record_id"]
    assert approval_payload["events"][0]["sources"][0]["method"]
    assert parcel_payload["events"][0]["category"] == "parcel"
    assert parcel_payload["events"][0]["confidence"] is None
    assert parcel_payload["events"][0]["sources"][0]["confidence"] is None
    assert project_payload["events"][0]["project"] == {
        "key": "project:test-main-street",
        "name": "Main Street redevelopment",
    }
    assert (
        project_payload["events"][0]["title"] == "Approval: Main Street redevelopment"
    )
    assert (
        "approved the requested variance"
        in project_payload["events"][0]["what_happened"]
    )
    assert project_payload["events"][0]["related_entities"] == ["Alpha Holdings LLC"]
    assert (
        entity_payload["events"][0]["entity_links"][0]["name"] == "Alpha Holdings LLC"
    )
    assert len(invalid_payload["events"]) == len(all_payload["events"])

    for event in all_payload["events"]:
        for key in (
            "what_happened",
            "related_entities",
            "entity_links",
            "related_pidns",
            "importance_score",
            "importance_reasons",
            "sources",
            "interpretation",
        ):
            assert key in event
        assert "why_it_matters" not in event
        assert "what_happens_next" not in event


def test_radar_routes(client):
    canonical = client.get("/api/radar/opportunity?min_score=30")
    readiness = client.get("/api/radar/site-readiness?min_score=0")
    canonical_munis = client.get(
        "/api/radar/municipalities?view=opportunity&min_score=30"
    )
    readiness_munis = client.get("/api/radar/municipalities?view=readiness&min_score=0")

    assert canonical.status_code == 200
    assert readiness.status_code == 200
    assert canonical_munis.status_code == 200
    assert readiness_munis.status_code == 200
    assert canonical.json()["parcels"][0]["pidn"] == TEST_PIDN
    assert "site_readiness_score" in readiness.json()["parcels"][0]
    assert readiness.json()["parcels"][0]["signal_count"] == len(
        readiness.json()["parcels"][0]["signals"]
    )
    assert readiness.json()["coverage"]["total_count"] == 7
    assert canonical_munis.json()["municipalities"] == [TEST_MUNICIPALITY]
    assert TEST_MUNICIPALITY in readiness_munis.json()["municipalities"]


def test_restricted_distress_routes_default_off(client):
    assert client.get("/api/delinquent/top-owners").status_code == 404
    assert client.get("/api/scores/distressed").status_code == 404


def test_owner_and_entity_profiles_serve_every_owner(client):
    top = client.get("/api/owners/top")
    assert top.status_code == 200
    owners = top.json()
    assert owners
    assert any(owner["entity_type"] == "business" for owner in owners)

    owner_id = owners[0]["owner_id"]
    profile = client.get(f"/api/owners/{owner_id}")
    entity_profile = client.get(f"/api/entities/{owner_id}")
    assert profile.status_code == 200
    assert entity_profile.status_code == 200
    assert profile.json()["owner"]["owner_id"] == owner_id
    # Restricted distress is off by default: the payload must say the rows
    # were withheld rather than report a zero balance as fact.
    assert profile.json()["delinquency"]["detail_available"] is False
    assert profile.json()["delinquency"]["records"] == []
    # The seeded owner brief is served; no per-row serving flag is exposed.
    assert profile.json()["brief"]["portfolio_strategy"] == "accumulator"
    verification = profile.json()["verification_evidence"]
    assert verification[0]["citation_key"] == f"evidence:parcels:{TEST_PIDN}"
    assert verification[0]["url"] == "https://example.com/parcels/1"


def test_parcels_near_answers_the_corridor_question(client):
    """Parcels around an anchor parcel or a project's linked parcels."""
    from api.tests.conftest import OTHER_PIDN, SECOND_PIDN

    wide = client.get(f"/api/parcels/near?pidn={TEST_PIDN}&radius_m=800")
    tight = client.get(f"/api/parcels/near?pidn={TEST_PIDN}&radius_m=200")
    by_project = client.get(
        "/api/parcels/near?project_key=project:test-main-street&radius_m=800"
    )
    missing = client.get("/api/parcels/near?radius_m=800")

    assert wide.status_code == 200
    assert missing.status_code == 422
    wide_payload = wide.json()
    assert wide_payload["anchor_pidns"] == [TEST_PIDN]
    assert wide_payload["anchor_lat"] is not None
    pidns = [row["pidn"] for row in wide_payload["parcels"]]
    assert set(pidns) == {SECOND_PIDN, OTHER_PIDN}
    assert TEST_PIDN not in pidns
    nearest = min(wide_payload["parcels"], key=lambda row: row["distance_m"])
    assert nearest["pidn"] == SECOND_PIDN
    for row in wide_payload["parcels"]:
        assert row["owner_label"]
        assert row["owner_kind"]
        assert "owner_full" not in row
        assert isinstance(row["likely_vacant"], bool)

    tight_pidns = [row["pidn"] for row in tight.json()["parcels"]]
    assert tight_pidns == [SECOND_PIDN]

    project_payload = by_project.json()
    assert project_payload["anchor_pidns"] == [TEST_PIDN]
    assert {row["pidn"] for row in project_payload["parcels"]} == {
        SECOND_PIDN,
        OTHER_PIDN,
    }


def test_feed_can_report_activity_near_watched_parcels(client):
    from api.tests.conftest import SECOND_PIDN

    response = client.get(
        f"/api/feed?near_pidns={SECOND_PIDN}&near_radius_m=400&since_days=3650"
    )
    far = client.get(
        f"/api/feed?near_pidns={SECOND_PIDN}&near_radius_m=50&since_days=3650"
    )

    assert response.status_code == 200
    events = response.json()["events"]
    assert events, "seeded events on the adjacent parcel should be within 400 m"
    assert all(SECOND_PIDN not in event["related_pidns"] for event in events)
    assert all(TEST_PIDN in event["related_pidns"] for event in events)
    assert far.json()["events"] == []


def test_parcels_summary_contract_for_watchlist(client):
    """Batch summary endpoint powering the client-side watchlist."""
    from api.tests.conftest import TEST_PIDN

    resp = client.get(f"/api/parcels/summary?pidns={TEST_PIDN},9999999999999")
    assert resp.status_code == 200
    body = resp.json()
    assert body["missing"] == ["9999999999999"]
    assert len(body["parcels"]) == 1
    parcel = body["parcels"][0]
    for key in (
        "pidn",
        "owner_full",
        "propadr",
        "municipality",
        "aprtotal",
        "changed_at",
        "changed_recently",
        "has_tax_delinquency",
        "momentum_score",
        "top_signal",
    ):
        assert key in parcel
    assert parcel["pidn"] == TEST_PIDN
    assert parcel["changed_recently"] is False  # first observation is not a change
    assert parcel["owner_full"] == "Alpha Holdings LLC"
    assert parcel["has_tax_delinquency"] is True


@pytest.mark.parametrize("days_ago,expected", [(1, True), (45, False)])
def test_watch_changes_require_recent_version_history(client, days_ago, expected):
    import psycopg2
    from api.tests.conftest import DB_ENV

    pidn = "0000000000987"
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO staging.parcels(pidn, owner_full, valid_from, valid_to)
                VALUES (%s, 'Prior owner', NOW() - INTERVAL '90 days', NOW() - %s * INTERVAL '1 day'),
                       (%s, 'Current owner', NOW() - %s * INTERVAL '1 day', NULL)""",
                (pidn, days_ago, pidn, days_ago),
            )
    try:
        response = client.get(f"/api/parcels/summary?pidns={pidn}")
        assert response.status_code == 200
        assert response.json()["parcels"][0]["changed_recently"] is expected
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM staging.parcels WHERE pidn = %s", (pidn,))


@pytest.mark.parametrize("legacy_reference", [None, "Multiple parcels in application"])
def test_structured_multiple_parcel_ids_report_id_match_method(
    client, legacy_reference
):
    import psycopg2
    from psycopg2.extras import Json
    from api.tests.conftest import DB_ENV, SECOND_PIDN

    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT pe.id,pe.parcel_reference,pe.extraction_details
                FROM staging.proceeding_extractions pe
                JOIN staging.public_proceedings pp ON pp.id=pe.proceeding_id
                WHERE pp.body_name='Hanover Borough Council' ORDER BY pe.id LIMIT 1
            """)
            extraction_id, reference, details = cursor.fetchone()
            cursor.execute(
                """
                UPDATE staging.proceeding_extractions
                SET parcel_reference=%s, extraction_details=%s
                WHERE id=%s
            """,
                (
                    legacy_reference,
                    Json({"parcel_references": [TEST_PIDN, SECOND_PIDN]}),
                    extraction_id,
                ),
            )
    try:
        response = client.get(f"/api/parcels/{TEST_PIDN}")
        assert response.status_code == 200, response.text
        linked = response.json()["linked_proceedings"]
        row = next(
            item for item in linked if item["body_name"] == "Hanover Borough Council"
        )
        assert row["match_type"] == "pidn"
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE staging.proceeding_extractions SET parcel_reference=%s,extraction_details=%s WHERE id=%s",
                    (reference, Json(details), extraction_id),
                )
