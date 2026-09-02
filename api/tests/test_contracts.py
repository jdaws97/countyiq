from __future__ import annotations

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
            "current_setting('transaction_read_only') AS read_only"
        )
        row = cur.fetchone()

    assert row == {"username": "countyiq_api_test", "read_only": "on"}


def test_ops_health_exposes_source_policy_review_state(client):
    response = client.get("/api/ops/health")

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
    assert municipal["configured_count"] == 122
    assert municipal["active_count"] == 113
    assert municipal["healthy_count"] == 0
    assert municipal["blocked_count"] == 9
    assert municipal["unchecked_count"] == 113
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
    evidence_by_kind = {item["source_kind"]: item for item in payload["evidence"]}
    assert evidence_by_kind["official_parcel_record"]["source_record_id"] == TEST_PIDN
    assert evidence_by_kind["official_parcel_record"]["url"] == "https://example.com/parcels/1"
    assert evidence_by_kind["official_flood_layer"]["details"]["zones"] == ["AE"]
    assert evidence_by_kind["official_flood_layer"]["details"]["parcel_overlap_pct"] == 100.0
    assert evidence_by_kind["official_structure_layer"]["details"]["footprint_count"] == 1
    assert evidence_by_kind["official_tax_listing"]["details"] == {"delinquency_signal": True}

    assert payload["development_momentum"]["score"] == 72
    assert payload["development_momentum"]["opportunity_score"] == 64
    assert "Private Person" not in str(payload["development_momentum"])
    assert payload["development_momentum"]["reason_signals"]

    assert payload["parcel_brief"] is None
    assert payload["intelligence_summary"] is None
    assert payload["related_narratives"] == []

    match_types = {row["match_type"] for row in payload["linked_proceedings"]}
    assert match_types == {"pidn", "address"}
    assert all(row["applicant_name"] is None for row in payload["linked_proceedings"])
    assert all(row["supporting_text"] is None for row in payload["linked_proceedings"])
    assert all(row["evidence"]["document_url"] for row in payload["linked_proceedings"])
    assert all(row["evidence"]["excerpt"] is None for row in payload["linked_proceedings"])


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

    assert all_response.status_code == 200
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
    assert approval_payload["events"][0]["sources"][0]["excerpt"] is None
    assert approval_payload["events"][0]["sources"][0]["details"]["decision"] == "approved"
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
            "why_it_matters",
            "what_happens_next",
            "related_entities",
            "entity_links",
            "related_pidns",
            "importance_score",
            "importance_reasons",
            "sources",
            "interpretation",
        ):
            assert key in event


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


def test_owner_and_entity_profiles_keep_organizations_but_hide_people(client):
    top = client.get("/api/owners/top")
    assert top.status_code == 200
    owners = top.json()
    assert owners
    assert all(
        owner["entity_type"]
        in {"business", "llc", "corporation", "partnership", "nonprofit", "government"}
        for owner in owners
    )
    assert any(owner["entity_type"] == "business" for owner in owners)

    owner_id = owners[0]["owner_id"]
    profile = client.get(f"/api/owners/{owner_id}")
    entity_profile = client.get(f"/api/entities/{owner_id}")
    assert profile.status_code == 200
    assert entity_profile.status_code == 200
    assert profile.json()["owner"]["owner_id"] == owner_id
    verification = profile.json()["verification_evidence"]
    assert verification[0]["citation_key"] == f"evidence:parcels:{TEST_PIDN}"
    assert verification[0]["url"] == "https://example.com/parcels/1"


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
    assert parcel["changed_recently"] is True  # seeded rows are fresh
    assert parcel["owner_full"] == "Alpha Holdings LLC"
    assert parcel["has_tax_delinquency"] is True
