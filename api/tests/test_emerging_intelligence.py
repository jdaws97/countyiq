"""Source-current serving, explicit review, packet integrity and private work."""

import json
import os
import subprocess
from copy import deepcopy
from datetime import UTC, datetime

from api.tests.conftest import DB_ENV, PIPELINES_DIR, TEST_PIDN
from api.tests.test_municipal_evidence import writer
from api.tests.test_municipal_evidence_workflow import (
    add_source,  # noqa: F401
    project_current_sources,
)
from api.tests.test_watchspaces import create, watch_client  # noqa: F401

PIPELINE_SCRIPT = """
import json
import sys
from countyiq.lib.emerging_packets import build_packet, fetch_scope
from countyiq.lib.emerging_store import retain_analysis, review_analysis
from countyiq.resources.database import make_database_resource

database = make_database_resource()
database.setup_for_execution(None)
request = json.load(sys.stdin)
try:
    if request['action'] == 'export':
        with database.read_snapshot() as cur:
            cur.execute("SELECT bundle_key FROM public.current_municipal_matter_sources WHERE source->>'candidate_scope'=%s", ('property:' + request['pidn'],))
            packet = build_packet(fetch_scope(cur, cur.fetchone()['bundle_key']))
        result = packet
    elif request['action'] == 'retain':
        gate = retain_analysis(database, request['packet'], request['analysis'], author='test source review')
        result = {'inference_id':gate.inference_id, 'accepted':gate.accepted}
    else:
        result = {'review_id':review_analysis(database,request['inference_id'],action=request['action'],reviewer='test source review',rationale='Verified the complete source and hypothesis in an isolated regression fixture.')}
    print(json.dumps(result))
except ValueError as error:
    print(json.dumps({'error':str(error)}))
finally:
    database.teardown_after_execution(None)
"""


def pipeline(action, **payload):
    result = subprocess.run(
        [str(PIPELINES_DIR / ".venv/bin/python"), "-c", PIPELINE_SCRIPT],
        cwd=PIPELINES_DIR,
        env={**os.environ, **DB_ENV, "PYTHONPATH": str(PIPELINES_DIR)},
        input=json.dumps({"action": action, **payload}),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def analysis_for(packet):
    source = next(item for item in packet["sources"] if "text" in item)
    citation = f"[Evidence:source:{source['id']}]"
    return {
        "hypotheses": [
            {
                "family": "construction_timing",
                "title": "A plan may be moving toward work",
                "hypothesis": "The plan consideration warrants a check of remaining approvals. "
                + citation,
                "status": "early_signal",
                "evidence_strength": "limited",
                "stage": "Plan consideration. " + citation,
                "supporting_facts": [
                    {
                        "source_id": source["id"],
                        "quote": source["text"],
                        "fact_keys": [],
                        "statement": "The record lists plan consideration.",
                    }
                ],
                "contrary_evidence": [],
                "alternatives": [
                    {
                        "explanation": "This may be administrative plan work.",
                        "why_plausible": "The item is plan consideration. " + citation,
                        "distinguishing_check": "Read the decision and improvement plan.",
                    }
                ],
                "unknowns": ["Outcome and contractor appointments."],
                "next_checks": [
                    {
                        "question": "Which approvals and work remain?",
                        "source_to_check": "Board decision and plan conditions.",
                        "why_it_changes_the_case": "These distinguish a current service need from completed plan work.",
                    }
                ],
                "opportunities": [
                    {
                        "audience": "service_business",
                        "services": ["engineering"],
                        "title": "Research remaining engineering work",
                        "rationale": "The plan item identifies a review target. "
                        + citation,
                        "next_action": "Read the conditions before qualifying services.",
                        "target_role": "Civil engineer",
                        "readiness": "research",
                        "commercial_basis": None,
                        "blockers": ["Unassigned scope is unknown."],
                        "disqualifiers": ["All engineering work is already assigned."],
                    }
                ],
                "project_types": [],
            }
        ],
        "abstention_reason": None,
        "source_presentations": [
            {"source_id": source["id"], "language": "en", "english_text": None}
        ],
    }


def test_shared_scope_builder_matches_canonical_sources(client, add_source):  # noqa: F811
    add_source()
    project_current_sources()
    with writer() as cur:
        cur.execute(
            "SELECT bundle_key FROM public.current_municipal_matter_sources "
            "WHERE source->>'candidate_scope'=%s",
            ("property:" + TEST_PIDN,),
        )
        bundle_key = cur.fetchone()[0]
        for requested_bundle in (bundle_key, "municipal-bundle:missing"):
            for neighbors, planning_radius, environmental_radius in (
                (0, 250, 500),
                (6, 500, 500),
                (12, 1500, 2000),
                (13, 500, 500),
            ):
                cur.execute(
                    """
                    WITH scoped AS MATERIALIZED (
                        SELECT array_agg(input) AS rows
                        FROM public.current_municipal_matter_scoped_inputs input
                    ), settings AS (
                        SELECT %s::text AS bundle, %s::integer AS planning_radius,
                            %s::integer AS environmental_radius, %s::integer AS neighbors
                    )
                    SELECT public.emerging_scope_source(
                        bundle, 'york_open_data', planning_radius,
                        environmental_radius, neighbors
                    ), public.emerging_scope_source_from_inputs(
                        bundle, 'york_open_data', planning_radius,
                        environmental_radius, neighbors, scoped.rows
                    ) FROM settings CROSS JOIN scoped
                    """,
                    (
                        requested_bundle,
                        planning_radius,
                        environmental_radius,
                        neighbors,
                    ),
                )
                canonical, shared = cur.fetchone()
                assert shared == canonical


def test_review_currentness_and_source_receipts(client, add_source):  # noqa: F811
    add_source()
    project_current_sources()
    packet = pipeline("export", pidn=TEST_PIDN)
    analysis = analysis_for(packet)
    forged = deepcopy(packet)
    forged["sources"][0]["text"] = "A forged project claim."
    rejection = pipeline("retain", packet=forged, analysis=analysis)
    assert "canonical source mapping" in rejection["error"]
    retained = pipeline("retain", packet=packet, analysis=analysis)
    assert retained["accepted"]
    assert client.get("/api/intelligence").json()["cases"] == []
    pipeline("publish", inference_id=retained["inference_id"])
    response = client.get(
        "/api/intelligence", params={"service": "engineering", "limit": 1}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    case = body["cases"][0]
    key = case["case_key"]
    assert case["opportunities"] == []
    assert len(case["implications"]) == 1
    assert (
        client.get("/api/intelligence", params={"opportunities_only": True}).json()[
            "total"
        ]
        == 0
    )
    assert (
        client.get("/api/intelligence", params={"exclude_case_key": key}).json()[
            "total"
        ]
        == 0
    )
    assert (
        client.get("/api/intelligence", params={"project_type": "housing"}).json()[
            "total"
        ]
        == 0
    )
    assert (
        client.get("/api/intelligence", params={"readiness": "qualify"}).json()["total"]
        == 0
    )
    assert any(item["pidn"] == TEST_PIDN for item in case["properties"])
    assert case["citation_evidence"][0]["details"]["passages"][0]["page"] == 1
    assert "payload" not in case and "packet" not in case
    assert (
        client.get("/api/intelligence", params={"service": "electrical"}).json()[
            "total"
        ]
        == 0
    )
    assert (
        client.get("/api/intelligence", params={"case_key": key}).json()["total"] == 1
    )
    assert client.get("/api/intelligence", params={"offset": 1}).json()["cases"] == []
    changed_meaning = deepcopy(analysis)
    changed_meaning["hypotheses"][0]["hypothesis"] = (
        "This may instead be a replacement project. "
        + changed_meaning["hypotheses"][0]["hypothesis"]
    )
    challenger = pipeline("retain", packet=packet, analysis=changed_meaning)
    assert challenger["accepted"] is False
    assert (
        "quarantined"
        in pipeline("publish", inference_id=challenger["inference_id"])["error"]
    )
    assert client.get(f"/api/intelligence/{key}").status_code == 200

    # A warm cache must retract immediately on rights or GIS-context changes.
    with writer() as cur:
        cur.execute(
            "UPDATE meta.source_rights SET derived_product_allowed=FALSE WHERE source_key='public_proceedings'"
        )
    try:
        assert client.get(f"/api/intelligence/{key}").status_code == 404
    finally:
        with writer() as cur:
            cur.execute(
                "UPDATE meta.source_rights SET derived_product_allowed=TRUE WHERE source_key='public_proceedings'"
            )
    assert client.get(f"/api/intelligence/{key}").status_code == 200
    with writer() as cur:
        cur.execute(
            "SELECT zrecid, source_url FROM staging.zoning WHERE valid_to IS NULL"
        )
        zoning_urls = cur.fetchall()
        cur.execute(
            "UPDATE staging.zoning SET source_url=COALESCE(source_url, 'https://example.com/zoning') || '?revised=1' WHERE valid_to IS NULL"
        )
    try:
        assert client.get(f"/api/intelligence/{key}").status_code == 404
    finally:
        with writer() as cur:
            cur.executemany(
                "UPDATE staging.zoning SET source_url=%s WHERE zrecid=%s AND valid_to IS NULL",
                [(url, zoning_key) for zoning_key, url in zoning_urls],
            )
    assert client.get(f"/api/intelligence/{key}").status_code == 200

    # A new observation in the same property scope invalidates the old review.
    add_source("Consider the revised final plan at 1 Main Street.\n")
    project_current_sources()
    assert client.get(f"/api/intelligence/{key}").status_code == 404
    assert client.get("/api/intelligence").json()["coverage"]["awaiting_refresh"] == 1
    assert (
        "Evidence changed"
        in pipeline("publish", inference_id=retained["inference_id"])["error"]
    )
    fresh = pipeline("export", pidn=TEST_PIDN)
    updated = pipeline("retain", packet=fresh, analysis=analysis_for(fresh))
    pipeline("publish", inference_id=updated["inference_id"])
    assert client.get(f"/api/intelligence/{key}").status_code == 200
    pipeline("withdraw", inference_id=updated["inference_id"])
    assert client.get(f"/api/intelligence/{key}").status_code == 404
    assert client.get("/api/intelligence").json()["coverage"]["awaiting_refresh"] == 0


def test_private_intelligence_work_survives_legacy_client(watch_client):  # noqa: F811
    _, first = create(watch_client)
    _, second = create(watch_client)
    profile = {
        "audience": "service_business",
        "services": ["engineering"],
        "families": [],
        "municipalities": [],
        "project_types": ["infrastructure"],
        "preferred_readiness": ["qualify"],
    }
    work = [
        {
            "case_key": "emerging-" + "a" * 64,
            "status": "qualifying",
            "note": "Private research note",
            "last_seen_revision": "10",
            "updated_at": datetime.now(UTC).isoformat(),
        }
    ]
    saved = watch_client.put(
        "/api/watchspaces/current",
        headers=first,
        json={
            "version": 0,
            "items": [],
            "intelligence_profile": profile,
            "intelligence_work": work,
        },
    )
    assert saved.status_code == 200, saved.text
    assert (
        watch_client.get("/api/watchspaces/current", headers=second).json()[
            "intelligence_work"
        ]
        == []
    )
    legacy = watch_client.put(
        "/api/watchspaces/current",
        headers=first,
        json={
            "version": 1,
            "items": [],
            "intelligence_profile": {
                key: value
                for key, value in profile.items()
                if key not in {"project_types", "preferred_readiness"}
            },
        },
    )
    assert legacy.status_code == 200
    assert legacy.json()["intelligence_work"][0]["note"] == work[0]["note"]
    assert legacy.json()["intelligence_profile"] == profile
    duplicate = watch_client.put(
        "/api/watchspaces/current",
        headers=first,
        json={
            "version": 2,
            "items": [],
            "intelligence_work": work + work,
        },
    )
    assert duplicate.status_code == 422
    assert (
        watch_client.delete("/api/watchspaces/current", headers=first).status_code
        == 204
    )
    assert (
        watch_client.get("/api/watchspaces/current", headers=first).json()[
            "intelligence_work"
        ]
        == []
    )


def test_qualified_opportunity_filters_and_receipts(client, add_source):  # noqa: F811
    text = "The authority seeks engineering proposals for the water extension at 1 Main Street. Submit qualifications to the authority before the design review.\n"
    add_source(text)
    project_current_sources()
    packet = pipeline("export", pidn=TEST_PIDN)
    analysis = analysis_for(packet)
    hypothesis = analysis["hypotheses"][0]
    hypothesis["project_types"] = ["infrastructure"]
    opportunity = hypothesis["opportunities"][0]
    source = next(item for item in packet["sources"] if "text" in item)
    opportunity["title"] = "Qualify engineering proposals for the water extension"
    opportunity["readiness"] = "qualify"
    opportunity["commercial_basis"] = {
        key: {
            "source_id": source["id"],
            "quote": quote,
            "fact_keys": [],
            "statement": quote,
        }
        for key, quote in {
            "need": "engineering proposals for the water extension at 1 Main Street",
            "timing": "before the design review",
            "qualification_route": "Submit qualifications to the authority",
        }.items()
    }
    retained = pipeline("retain", packet=packet, analysis=analysis)
    assert retained["accepted"]
    pipeline("publish", inference_id=retained["inference_id"])
    params = {
        "opportunities_only": True,
        "service": "engineering",
        "project_type": "infrastructure",
        "readiness": "qualify",
        "limit": 1,
    }
    body = client.get("/api/intelligence", params=params).json()
    assert body["total"] == 1
    case = body["cases"][0]
    assert case["implications"] == []
    assert (
        "[Evidence:source:"
        in case["opportunities"][0]["commercial_basis"]["qualification_route"]
    )
    assert "quote" not in case["opportunities"][0]["commercial_basis"]
    assert (
        client.get("/api/intelligence", params={**params, "readiness": "act"}).json()[
            "total"
        ]
        == 0
    )
    assert (
        client.get(
            "/api/intelligence", params={**params, "service": "electrical"}
        ).json()["total"]
        == 0
    )
    assert (
        client.get("/api/intelligence", params={**params, "offset": 1}).json()["cases"]
        == []
    )
