"""Synthetic contract regressions: no model calls or real-data writes."""
from copy import deepcopy
import pytest
from countyiq.lib.proceeding_claims import hydrate_claims, passage_document, MAX_SOURCE_CHARS
from countyiq.lib.proceeding_contract import details_for, project_aliases, distinctive_project_reference
from countyiq.lib.intelligence_events import build_development_event

SOURCE = """SYNTHETIC TEST RECORD. Council approved a bond release for Willow Creek Meadows, SD-03-2026, at 123 North Main Street on July 20, 2026. This is a project milestone.
Bid opening: September 10, 2026. Completion: November 30, 2026. Condition: submit an inspection report.
"""
def payload(source=SOURCE):
    doc = passage_document(source)
    ids = [doc.passages[0].passage_id]
    def claim(text):
        return {"text": text, "passage_ids": ids.copy()}
    return {"source_sha256": doc.source_sha256, "extractions": [{
        "extraction_type": "subdivision_review", "project_name": "Willow Creek Meadows",
        "what_happened": claim("Council approved the project bond release."),
        "applicant_name": None, "current_zoning": None, "proposed_zoning": None,
        "conditions": [claim("Submit an inspection report.")],
        "why_it_matters": None, "what_happens_next": None,
        "record_status": "decision",
        "decision": {"outcome": "approved", "scope": "bond", "authority": "Council", "passage_ids": ids.copy(), "action_text": source.splitlines()[0]},
        "event_date": claim("July 20, 2026"),
        "milestones": [
            {"kind": "bid_opening", **claim("September 10, 2026")},
            {"kind": "completion", **claim("November 30, 2026")},
        ],
        "application_ids": [claim("SD-03-2026")],
        "project_reference": claim("Willow Creek Meadows"),
        "parcel_references": [claim("123 North Main Street")],
        "related_entities": [], "identity_conflicts": [],
        "relevance": {"category": "public_works", "scope": "project_milestone",
                      "basis": claim("A bond release for an existing project."), "source_text": source.splitlines()[0]},
        "confidence": "high",
    }]}

def row(item, id=1):
    return dict(id=id, proceeding_id=90, body_name="Synthetic Township Council",
                meeting_date="2026-08-01", extracted_at="2026-08-02T00:00:00Z",
                extraction_details=details_for(item), **item)

def test_hydration_recovers_exact_source_and_separate_scoped_dates():
    original = payload()
    before = deepcopy(original)
    item = hydrate_claims(original, SOURCE, meeting_date="2026-08-01")[0]
    assert original == before
    assert item["decision_scope"] == "bond"
    assert item["decision_authority"] == "Council"
    assert item["event_date"] == "2026-07-20"
    assert [(m["kind"], m["date"]) for m in item["milestones"]] == [
        ("bid_opening", "2026-09-10"), ("completion", "2026-11-30")]
    assert item["upcoming_date"] is None
    assert item["discovery_eligible"] is False
    span = item["evidence_spans"][0]
    assert span["quote"] == SOURCE[span["start"]:span["end"]]
    assert {"condition:0", "milestone:0", "milestone:1", "decision"} <= set(span["fields"])
    event = build_development_event(row(item))
    assert event["title"].startswith("Bond: Approved:")
    assert "approval" not in event["event_tags"]
    assert "scoped_decision" in event["event_tags"]
    assert event["event_date"] == "2026-07-20"
    assert event["source_evidence"][0]["details"]["milestones"] == item["milestones"]

@pytest.mark.parametrize("change", ["hash", "source", "unknown", "duplicate", "missing", "invented", "extra"])
def test_bad_citations_and_invented_literal_fail_closed(change):
    wire, source = payload(), SOURCE
    if change == "hash": wire["source_sha256"] = "0" * 64
    if change == "source": source += "Changed source."
    if change == "unknown": wire["extractions"][0]["what_happened"]["passage_ids"] = ["v1-1200-p9999"]
    if change == "duplicate": wire["extractions"][0]["what_happened"]["passage_ids"] *= 2
    if change == "missing": wire["extractions"][0]["what_happened"]["passage_ids"] = []
    if change == "invented": wire["extractions"][0]["application_ids"][0]["text"] = "SD-99-2026"
    if change == "extra": wire["extractions"][0]["event_date"]["iso"] = "2026-07-20"
    with pytest.raises(ValueError): hydrate_claims(wire, source)

@pytest.mark.parametrize("status", ["scheduled", "recommendation", "withdrawn", "removed", "update"])
def test_nondecision_cannot_carry_approval(status):
    wire = payload()
    wire["extractions"][0]["record_status"] = status
    with pytest.raises(ValueError, match="Only a completed decision"):
        hydrate_claims(wire, SOURCE)

@pytest.mark.parametrize("wording,status,outcome", [
    ("Council [approve/deny] the application.", "decision", "approved"),
    ("Council [approve/deny] the application.", "recommendation", None),
    ("Council moved to grant relief.", "decision", "approved"),
    ("Council removed this application from future agendas.", "decision", "continued"),
])
def test_known_procedural_counterexamples(wording, status, outcome):
    source = wording + "\n" + SOURCE
    wire = payload(source)
    item = wire["extractions"][0]
    item["record_status"] = status
    item["decision"]["action_text"] = wording
    if outcome is None: item["decision"] = None
    else: item["decision"]["outcome"] = outcome
    with pytest.raises(ValueError):
        hydrate_claims(wire, source)

@pytest.mark.parametrize("scope,category,eligible", [
    ("new_construction", "development", False),
    ("expansion", "development", False),
    ("new_lots", "development", False),  # Bond milestone fixture does not establish new building lots.
    ("unknown", "development", False),
    ("subdivision_only", "minor_property", False),
    ("property_relief", "minor_property", False),
    ("policy_change", "landuse_policy", False),
    ("capital_project", "public_works", False),
    ("project_milestone", "public_works", False),
])
def test_bond_source_cannot_be_promoted_by_changing_model_labels(scope, category, eligible):
    wire = payload()
    item = wire["extractions"][0]
    item["record_status"], item["decision"] = "update", None
    item["relevance"].update(scope=scope, category=category)
    assert hydrate_claims(wire, SOURCE)[0]["discovery_eligible"] is eligible

def test_explicit_no_development_overrides_category_label():
    source = SOURCE + "No new development is proposed."
    wire = payload(source)
    item = wire["extractions"][0]
    item["record_status"], item["decision"] = "update", None
    item["relevance"].update(scope="new_construction", category="development", source_text="No new development is proposed.")
    assert hydrate_claims(wire, source)[0]["discovery_eligible"] is False

@pytest.mark.parametrize("name", ["Steep Slope", "Accessory Use", "Preliminary Subdivision Plan",
                                 "123 Willow Creek Road", "Willow Creek Road", "Shared plan"])
def test_generic_or_street_descriptions_are_not_project_identity(name):
    assert not distinctive_project_reference(name)

@pytest.mark.parametrize("identifiers", [["SD-03-202695"], ["Resolution 2026-18", "Resolution 2026-19"]])
def test_suspicious_identifiers_quarantine_all_identity_aliases(identifiers):
    source = SOURCE + " ".join(identifiers)
    wire = payload(source)
    item = wire["extractions"][0]
    ids = item["what_happened"]["passage_ids"]
    item["application_ids"] = [{"text": value, "passage_ids": ids} for value in identifiers]
    hydrated = hydrate_claims(wire, source)[0]
    assert hydrated["identity_status"] == "needs_review"
    assert project_aliases(row(hydrated)) == []

def test_source_date_conflict_preserves_wording_but_no_machine_chronology():
    source = SOURCE + "The letter date is November 2025 or November 2026."
    wire = payload(source)
    wire["extractions"][0]["identity_conflicts"] = [
        {"text": "Conflicting letter years", "passage_ids": wire["extractions"][0]["what_happened"]["passage_ids"]}]
    item = hydrate_claims(wire, source)[0]
    assert item["event_date_text"] == "July 20, 2026"
    assert item["event_date"] is None
    assert all(m["date"] is None for m in item["milestones"])
    assert project_aliases(row(item)) == []

def test_two_matters_in_one_passage_have_different_event_keys():
    item = hydrate_claims(payload(), SOURCE)[0]
    other = deepcopy(item)
    other["what_happened"] = "A separate application appeared in this same source passage."
    assert build_development_event(row(item))["event_key"] != build_development_event(row(other, 2))["event_key"]

def test_empty_output_is_source_bound_and_oversized_sources_are_not_truncated():
    wire = {"source_sha256": passage_document(SOURCE).source_sha256, "extractions": []}
    assert hydrate_claims(wire, SOURCE) == []
    with pytest.raises(ValueError, match="Whole source"):
        passage_document("x" * (MAX_SOURCE_CHARS + 1))


def test_frozen_multi_passage_contract_uses_different_milestone_receipts():
    import json
    from pathlib import Path
    fixture = json.loads((Path(__file__).parents[1] / "eval/fixtures/p0_claims_contract.json").read_text())
    item = hydrate_claims(fixture["model_claims"], fixture["source_text"])[0]
    for key in ("decision_scope", "discovery_eligible", "event_date"):
        assert item[key] == fixture["expected"][key]
    assert [m["date"] for m in item["milestones"]] == fixture["expected"]["milestone_dates"]
    event = build_development_event(row(item))
    def evidence(marker):
        return next(e for e in event["source_evidence"] if marker in e["details"]["supports"])
    assert evidence("milestone:0") != evidence("milestone:1")
    assert "November 30, 2026" in evidence("milestone:1")["excerpt"]


def test_disjoint_passages_cannot_fabricate_one_literal_reference():
    source = "Willow " + "x" * 1193 + "y" * 1200 + "Creek Meadows"
    doc = passage_document(source)
    wire = payload(source)
    item = wire["extractions"][0]
    item.update(decision=None, record_status="update", event_date=None, milestones=[],
                conditions=[], application_ids=[], parcel_references=[])
    item["project_reference"] = {"text": "Willow Creek Meadows",
        "passage_ids": [doc.passages[0].passage_id, doc.passages[-1].passage_id]}
    with pytest.raises(ValueError, match="project_reference"):
        hydrate_claims(wire, source)
