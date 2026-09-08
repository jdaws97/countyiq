from copy import deepcopy

import pytest
from countyiq.lib.pass0_locator import review_locations
from countyiq.lib.pass0_packet_facts import (
    full_source_interpretation_prompt,
    overlap_groups,
    packet_schema,
    review_packet_facts,
)
from countyiq.lib.pass0_source import index_source

from tests.test_pass0_facts import consent_fixture


def full_source_fixture():
    text = (
        "Municipal letterhead\n101 Civic Street\nExample County\n"
        "Planning Department\nPlanning Commission\nSeptember 1, 2026\n"
        "Meeting room information\nCall to order\n"
        "Alpha subdivision plan\n"
        "The Commission recommended approval of Alpha. Motion carried.\n"
        "Council approved the separate Beta plan.\n"
    )
    _, draft = consent_fixture()
    matter = draft["matters"][0]
    matter.update(
        title="Alpha subdivision plan",
        status="recommendation",
        summary={
            "excerpts": [
                {
                    "start": "Alpha subdivision plan",
                    "end": "Motion carried.",
                    "lines": [9, 10],
                }
            ]
        },
        identifiers=[],
        participants=[],
        conditions=[],
        relevance={"scope": "subdivision_only", "lines": [[9, 9]]},
        event_date={"text": "September 1, 2026", "lines": [[6, 6]]},
    )
    matter["decisions"][0].update(
        subject={"text": "Alpha subdivision plan", "lines": [[9, 9]]},
        outcome="recommended_approval",
        scope="plan",
        authority=[[5, 5]],
        date={"text": "September 1, 2026", "lines": [[6, 6]]},
        timing_evidence=[[6, 6], [10, 10]],
        motion=[[10, 10]],
        result=[[10, 10]],
        applies_to=[[9, 10]],
    )
    locations = {"matters": [{"title": "Alpha", "lines": [[9, 10]]}]}
    payload = {"0": {"matter": matter, "skip_reason": None, "duplicate_of": None}}
    return {"raw_text": text}, locations, payload


def test_full_source_context_keeps_date_after_letterhead_citable():
    source, locations, payload = full_source_fixture()
    original = deepcopy(payload)
    prompt, document, ranges, context = full_source_interpretation_prompt(
        source, locations
    )
    review = review_packet_facts(
        payload, document, locations, evidence_ranges=ranges, context_ranges=context
    )

    assert not review["envelope_errors"]
    assert not review["rejected"]
    matter = review["matters"][0]
    assert matter["event_date_iso"] == "2026-09-01"
    assert matter["decisions"][0]["date_iso"] == "2026-09-01"
    assert matter["decisions"][0]["authority_text"] == "Planning Commission"
    assert "separate Beta plan" in prompt
    assert payload == original
    assert all(
        source["raw_text"][receipt["start"] : receipt["end"]] == receipt["quote"]
        for receipt in matter["evidence"]
    )


@pytest.mark.parametrize("scope", ["procedural", "reconsideration", "plan", "waiver"])
def test_recommendation_can_coexist_with_a_separate_procedural_approval(scope):
    source, locations, payload = full_source_fixture()
    source["raw_text"] += "The Commission voted to untable Alpha. Motion carried.\n"
    locations["matters"][0]["lines"].append([12, 12])
    matter = payload["0"]["matter"]
    procedural = deepcopy(matter["decisions"][0])
    procedural.update(
        subject={"text": "untable Alpha", "lines": [[12, 12]]},
        outcome="approved",
        scope=scope,
        motion=[[12, 12]],
        result=[[12, 12]],
        applies_to=[[9, 9], [12, 12]],
        timing_evidence=[[12, 12]],
    )
    matter["decisions"].append(procedural)
    _, document, ranges, context = full_source_interpretation_prompt(source, locations)
    review = review_packet_facts(
        payload, document, locations, evidence_ranges=ranges, context_ranges=context
    )

    if scope in {"plan", "waiver"}:
        assert review["rejected"]
        assert not review["matters"]
        return

    assert not review["envelope_errors"]
    assert not review["rejected"]
    retained = review["matters"][0]
    assert retained["status"] == "recommendation"
    assert retained["decisions"][0]["outcome"] == "recommended_approval"
    assert retained["decisions"][1]["outcome"] == "approved"
    assert retained["decisions"][1]["scope"] == scope
    assert retained["semantic_review_complete"] is False

    matter["decisions"] = [procedural]
    review = review_packet_facts(
        payload, document, locations, evidence_ranges=ranges, context_ranges=context
    )
    assert review["rejected"]


@pytest.mark.parametrize("field", ["motion", "result", "applies_to", "subject"])
def test_full_source_context_does_not_make_neighbor_actions_citable(field):
    source, locations, payload = full_source_fixture()
    _, document, ranges, context = full_source_interpretation_prompt(source, locations)
    decision = payload["0"]["matter"]["decisions"][0]
    if field == "subject":
        decision[field] = {"text": "the separate Beta plan", "lines": [[11, 11]]}
    else:
        decision[field] = [[11, 11]]

    review = review_packet_facts(
        payload, document, locations, evidence_ranges=ranges, context_ranges=context
    )

    assert review["envelope_errors"]
    assert not review["matters"]


def test_overlap_groups_share_item_context_but_not_unrelated_header_links():
    text = (
        "Council minutes\nCall to order\nAlpha application\n"
        "Shared Alpha and Beta consent result\nBeta application\n"
        "Gamma application: approved separately\n"
    )
    document = index_source(text)
    locations = {
        "matters": [
            {"title": "Alpha", "lines": [[1, 1], [3, 4]]},
            {"title": "Beta", "lines": [[1, 1], [4, 5]]},
            {"title": "Gamma", "lines": [[1, 1], [6, 6]]},
        ]
    }
    original = deepcopy(locations)

    groups = overlap_groups(locations, document)
    selected = {"matters": [locations["matters"][index] for index in groups[0]]}
    prompt, _, ranges, _ = full_source_interpretation_prompt(
        {"raw_text": text}, selected
    )
    schema = packet_schema(selected, document, evidence_ranges=ranges)

    assert groups == [[0, 1], [2]]
    assert locations == original
    assert schema["required"] == ["0", "1"]
    assert "Shared Alpha and Beta" in prompt
    assert "Gamma" in prompt
    assert all(last < 6 for _, last in ranges)


def test_overlap_groups_are_transitive_and_account_for_every_entry_once():
    document = index_source("Minutes\nCall to order\nA\nA/B\nB/C\nC\nD\n")
    locations = {
        "matters": [
            {"title": "A", "lines": [[3, 4]]},
            {"title": "B", "lines": [[4, 5]]},
            {"title": "C", "lines": [[5, 6]]},
            {"title": "D", "lines": [[7, 7]]},
        ]
    }

    assert overlap_groups(locations, document) == [[0, 1, 2], [3]]


def test_every_inventory_entry_requires_an_explicit_disposition():
    source, draft = consent_fixture()
    locations = {
        "matters": [
            {"title": "Wawa", "lines": [[2, 3], [6, 6]]},
            {"title": "Eagle Rock", "lines": [[4, 4]]},
        ]
    }
    response = {
        "0": {"matter": draft["matters"][0], "skip_reason": None, "duplicate_of": None}
    }
    review = review_packet_facts(response, index_source(source), locations)
    assert review["envelope_errors"]
    assert not review["matters"]


def test_unrelated_inventory_entry_cannot_be_hidden_as_a_duplicate():
    source, draft = consent_fixture()
    locations = {
        "matters": [
            {"title": "Wawa", "lines": [[2, 3], [6, 6]]},
            {"title": "Eagle Rock", "lines": [[4, 4]]},
        ]
    }
    response = {
        "0": {"matter": draft["matters"][0], "skip_reason": None, "duplicate_of": None},
        "1": {"matter": None, "skip_reason": "duplicate", "duplicate_of": 0},
    }
    review = review_packet_facts(response, index_source(source), locations)
    assert len(review["matters"]) == 1
    assert review["rejected"][0]["index"] == 1


def test_duplicate_of_rejected_matter_is_also_rejected():
    source, draft = consent_fixture()
    locations = {"matters": [{"title": "Wawa", "lines": [[3, 3]]}] * 2}
    broken = deepcopy(draft["matters"][0])
    broken["summary"]["excerpts"][0]["lines"] = [99, 99]
    response = {
        "0": {"matter": broken, "skip_reason": None, "duplicate_of": None},
        "1": {"matter": None, "skip_reason": "duplicate", "duplicate_of": 0},
    }
    review = review_packet_facts(response, index_source(source), locations)
    assert len(review["rejected"]) == 2
    assert not review["matters"]
    assert not review["skipped"]


def test_locator_preserves_exact_disjoint_source_ranges():
    source, _ = consent_fixture()
    document = index_source(source)
    locations = {"matters": [{"title": "Wawa", "lines": [[2, 3], [6, 6]]}]}
    result = review_locations(locations, document)
    assert not result["rejected"]
    receipts = result["matters"][0]["evidence"]
    assert len(receipts) == 2
    assert all(r["quote"] == source[r["start"] : r["end"]] for r in receipts)
    assert all("Eagle Rock" not in r["quote"] for r in receipts)


def test_packet_cannot_borrow_a_neighboring_vote_from_full_context():
    text, draft = consent_fixture()
    source = {"raw_text": text, "body_name": "Pine Borough Council"}
    locations = {"matters": [{"title": "Wawa", "lines": [[2, 3], [6, 6]]}]}
    prompt, document, ranges, context = full_source_interpretation_prompt(
        source, locations
    )
    payload = {
        "0": {"matter": draft["matters"][0], "skip_reason": None, "duplicate_of": None}
    }

    assert "Mustang Pointe" in prompt
    assert "Eagle Rock" in prompt
    assert "Pine Borough Council" in prompt
    assert not review_packet_facts(
        payload, document, locations, evidence_ranges=ranges, context_ranges=context
    )["envelope_errors"]

    for invalid in ([[5, 5]], [[2, 6]]):
        payload["0"]["matter"]["decisions"][0]["result"] = invalid
        review = review_packet_facts(
            payload, document, locations, evidence_ranges=ranges, context_ranges=context
        )
        assert review["envelope_errors"]
        assert not review["matters"]


def test_summary_endpoint_range_cannot_fill_an_unprovided_neighbor_gap():
    text, draft = consent_fixture()
    source = {"raw_text": text, "body_name": "Pine Borough Council"}
    locations = {"matters": [{"title": "Wawa", "lines": [[2, 3], [6, 6]]}]}
    _, document, ranges, _ = full_source_interpretation_prompt(source, locations)
    matter = draft["matters"][0]
    matter["summary"] = {
        "excerpts": [
            {
                "start": "Council moved to approve",
                "end": "Consent motion carried 6-0.",
                "lines": [2, 6],
            }
        ]
    }
    response = {"0": {"matter": matter, "skip_reason": None, "duplicate_of": None}}

    review = review_packet_facts(response, document, locations, evidence_ranges=ranges)

    assert review["envelope_errors"]
    assert not review["matters"]


@pytest.mark.parametrize(
    ("inventory_end", "supplied_end", "repaired"),
    [(7, 8, False), (8, 7, False), (8, 8, True)],
)
def test_name_continuation_stays_inside_both_item_inventory_and_supplied_context(
    inventory_end, supplied_end, repaired
):
    text, draft = consent_fixture()
    text += "Acme\nConstruction was awarded the contract.\n"
    matter = draft["matters"][0]
    matter["participants"] = [
        {
            "name": {"text": "Acme Construction", "lines": [[7, 7]]},
            "role": "unknown",
            "role_evidence": None,
        }
    ]
    locations = {"matters": [{"title": "Wawa", "lines": [[1, inventory_end]]}]}
    payload = {"0": {"matter": matter, "skip_reason": None, "duplicate_of": None}}
    original = deepcopy(payload)

    review = review_packet_facts(
        payload,
        index_source(text),
        locations,
        evidence_ranges=[[1, supplied_end]],
    )

    assert not review["rejected"]
    assert not review["envelope_errors"]
    retained = review["matters"][0]
    assert bool(retained["participants"]) is repaired
    assert bool(retained["field_repairs"]) is repaired
    if repaired:
        assert retained["participants"][0]["name"]["lines"] == [[7, 8]]
    assert payload == original
