"""Unit tests for unified intelligence event normalization and copy."""

from datetime import date, datetime, timezone

from countyiq.lib.intelligence_events import (
    build_delinquency_event,
    build_development_event,
    build_parcel_event,
    make_project_key,
    municipality_from_body_name,
    normalize_development_tags,
    primary_development_event_type,
)
from countyiq.assets.enrichment.intelligence_events import _DEVELOPMENT_EVENTS_SQL

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def test_development_event_address_match_is_scoped_to_municipality():
    # The shared SQL function is behavior-tested against synthetic parcels.
    sql = _DEVELOPMENT_EVENTS_SQL
    assert "public.proceeding_parcel_matches(" in sql
    assert "pp.body_name) matched" in sql


def test_development_tags_combine_model_and_source_facts():
    tags = normalize_development_tags(
        extraction_type="variance_request",
        decision="continued",
        conditions=["Submit a traffic study"],
        proposed_tags=["revision"],
        what_happens_next="Return next month.",
        upcoming_date="September meeting",
    )
    assert set(tags) == {
        "application",
        "hearing",
        "revision",
        "continuance",
        "condition",
        "upcoming_decision",
    }
    assert primary_development_event_type(tags) == "continuance"


def test_ordinance_actions_carry_a_policy_tag_and_no_application():
    tags = normalize_development_tags(
        extraction_type="ordinance_action",
        decision="approved",
        conditions=[],
        proposed_tags=["hearing"],
        what_happens_next=None,
        upcoming_date=None,
    )
    assert "policy_action" in tags
    assert "application" not in tags
    assert primary_development_event_type(tags) == "approval"


def test_recorded_decision_overrides_contradictory_model_tag():
    tags = normalize_development_tags(
        extraction_type="variance_request",
        decision="denied",
        conditions=[],
        proposed_tags=["approval"],
        what_happens_next=None,
        upcoming_date=None,
    )
    assert "denial" in tags
    assert "approval" not in tags
    assert primary_development_event_type(tags) == "denial"


def test_project_key_is_stable_and_sensitive_to_project_identity():
    kwargs = {
        "applicant_name": "Alpha Holdings LLC",
        "project_name": "Main Street Redevelopment",
        "parcel_reference": "1 MAIN ST",
        "body_name": "Test Township ZHB",
    }
    assert make_project_key(**kwargs) == make_project_key(**kwargs)
    assert make_project_key(**kwargs) != make_project_key(**{**kwargs, "parcel_reference": "2 MAIN ST"})
    assert make_project_key(**kwargs) == make_project_key(
        **{**kwargs, "body_name": "Test Township Planning Commission"}
    )


def test_municipality_is_derived_from_public_body_name():
    assert municipality_from_body_name("Spring Garden Township Planning Commission") == "Spring Garden Township"
    assert municipality_from_body_name("York City Council") == "York City"
    assert municipality_from_body_name("Monaghan Twp Board of Supervisors") == "Monaghan Twp"
    assert municipality_from_body_name("York Twp Board of Commissioners") == "York Twp"


def test_parcel_event_copy_separates_fact_from_interpretation():
    event = build_parcel_event(
        {
            "id": 7,
            "pidn": "0000000000001",
            "event_type": "transfer",
            "confidence": "confirmed",
            "event_date": date(2026, 8, 1),
            "detected_at": NOW,
            "evidence": {
                "changed": {
                    "owner_full": {"old": "Old Owner", "new": "Alpha Holdings LLC"},
                    "deed_bk": {"old": "1", "new": "2"},
                }
            },
            "owner_full": "Alpha Holdings LLC",
            "propadr": "1 Main St",
            "municipality": "Test TWP",
            "source_url": "https://example.com/parcel",
        }
    )
    assert event["event_type"] == "transfer"
    assert "Old Owner" in event["what_happened"]
    assert event["interpretation_kind"] == "deterministic"
    assert event["related_pidns"] == ["0000000000001"]
    assert event["source_evidence"][0]["details"]["changed"]


def test_delinquency_event_describes_direction_and_limit():
    event = build_delinquency_event(
        {
            "pidn": "0000000000001",
            "detected_at": NOW,
            "event_date": date(2026, 8, 20),
            "old_total": 1000,
            "new_total": 1500,
            "change_kind": "increased",
            "affected_claims": 2,
            "tax_years": [2024, 2025],
            "owner_full": "Alpha Holdings LLC",
            "propadr": "1 Main St",
            "municipality": "Test TWP",
            "source_url": "https://example.com/tax-claims.pdf",
        }
    )
    assert event["event_type"] == "delinquency_change"
    assert "$1,000.00" in event["what_happened"]
    assert event["why_it_matters"] == ""
    assert event["confidence"] is None


def test_delinquency_transition_kind_prevents_same_timestamp_key_collision():
    base = {
        "pidn": "0000000000001",
        "detected_at": NOW,
        "event_date": date(2026, 8, 20),
        "affected_claims": 1,
    }
    added = build_delinquency_event(
        {**base, "old_total": 0, "new_total": 100, "change_kind": "new"}
    )
    resolved = build_delinquency_event(
        {
            **base,
            "old_total": 100,
            "new_total": 0,
            "change_kind": "resolved",
        }
    )

    assert added["event_key"] != resolved["event_key"]
    assert added["source_record_id"] != resolved["source_record_id"]


def test_development_event_uses_cached_llm_interpretation_and_evidence():
    event = build_development_event(
        {
            "id": 11,
            "proceeding_id": 4,
            "extraction_type": "subdivision_review",
            "applicant_name": "Alpha Holdings LLC",
            "parcel_reference": "1 Main St",
            "current_zoning": "R-1",
            "proposed_zoning": None,
            "decision": "approved",
            "conditions": ["Traffic study"],
            "supporting_text": "The commission approved the plan subject to a traffic study.",
            "extraction_confidence": 0.91,
            "model_used": "test-model",
            "extracted_at": NOW,
            "event_tags": ["application", "approval"],
            "project_name": "Main Street subdivision",
            "related_entities": ["Alpha Engineering"],
            "what_happened": "The commission approved the subdivision plan with one condition.",
            "why_it_matters": "The approval advances the plan into its next review stage.",
            "what_happens_next": "The applicant must submit the traffic study.",
            "upcoming_date": None,
            "interpretation_generated_at": NOW,
            "body_name": "Test Township Planning Commission",
            "meeting_date": date(2026, 8, 20),
            "source_url": "https://example.com/meeting",
            "document_url": "https://example.com/minutes.pdf",
            "proceeding_valid_from": NOW,
            "related_pidns": ["0000000000001"],
            "matched_owners": ["Alpha Holdings LLC"],
        }
    )
    assert event["event_type"] == "approval"
    assert set(event["event_tags"]) >= {"application", "hearing", "approval", "condition"}
    assert event["interpretation_kind"] == "llm"
    assert event["interpretation_model"] == "test-model"
    assert event["project_key"].startswith("project:")
    assert event["municipality"] == "Test Township"
    assert event["source_evidence"][0]["excerpt"].startswith("The commission")
    assert set(event["related_entities"]) == {"Alpha Holdings LLC", "Alpha Engineering"}


def test_development_event_falls_back_without_llm_interpretation():
    event = build_development_event(
        {
            "id": 12,
            "proceeding_id": 5,
            "extraction_type": "variance_request",
            "applicant_name": "Beta LLC",
            "parcel_reference": None,
            "decision": "denied",
            "conditions": [],
            "supporting_text": "The request was denied.",
            "extraction_confidence": 0.8,
            "model_used": "legacy-model",
            "extracted_at": NOW,
            "event_tags": None,
            "project_name": None,
            "related_entities": None,
            "what_happened": None,
            "why_it_matters": None,
            "what_happens_next": None,
            "upcoming_date": None,
            "interpretation_generated_at": None,
            "body_name": "Test Township ZHB",
            "meeting_date": date(2026, 8, 20),
            "source_url": "https://example.com/meeting",
            "document_url": None,
            "proceeding_valid_from": NOW,
            "related_pidns": [],
            "matched_owners": [],
            "current_zoning": None,
            "proposed_zoning": None,
        }
    )
    assert event["event_type"] == "denial"
    assert event["interpretation_kind"] == "deterministic"
    assert event["what_happens_next"] == ""


def test_development_event_does_not_create_project_from_board_alone():
    event = build_development_event(
        {
            "id": 13,
            "proceeding_id": 6,
            "extraction_type": "other",
            "applicant_name": None,
            "parcel_reference": None,
            "decision": None,
            "conditions": [],
            "supporting_text": "The board discussed the zoning ordinance.",
            "extraction_confidence": 0.6,
            "model_used": "legacy-model",
            "extracted_at": NOW,
            "event_tags": ["hearing"],
            "project_name": None,
            "related_entities": [],
            "what_happened": None,
            "why_it_matters": None,
            "what_happens_next": None,
            "upcoming_date": None,
            "interpretation_generated_at": None,
            "body_name": "Test Township Planning Commission",
            "meeting_date": date(2026, 8, 20),
            "source_url": "https://example.com/meeting",
            "document_url": None,
            "proceeding_valid_from": NOW,
            "related_pidns": [],
            "matched_owners": [],
            "current_zoning": None,
            "proposed_zoning": None,
        }
    )
    assert event["project_key"] is None
    assert event["project_name"] is None
