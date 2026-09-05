"""Synthetic counterexamples for conversion, repairs and recall telemetry."""
from copy import deepcopy
import pytest
from countyiq.lib.proceeding_semantics import relevance_projection
from countyiq.lib.proceeding_claims import passage_document, review_claims
from countyiq.lib.proceeding_coverage import review_coverage
from tests.test_proceeding_item_review import simple


@pytest.mark.parametrize("source", [
    "Proposed conversion of a single-family home into 2 units; no new construction.",
    "A multifamily conversion from another use within the existing building.",
    "Change of use to apartments without an addition.",
])
def test_existing_shell_housing_conversion_is_discoverable(source):
    assert relevance_projection("minor_property", "property_relief", "No new development.", source) == (
        "development", "conversion", True)


@pytest.mark.parametrize("source", [
    "Plans to renovate an existing industrial building into an emergency shelter.",
    "Repurpose the existing building into a municipal office.",
])
def test_explicit_building_reuse_does_not_require_the_word_conversion(source):
    assert relevance_projection("development", "redevelopment", "Proposed reuse.", source) == (
        "development", "conversion", True)


@pytest.mark.parametrize("source", [
    "Renovate the existing shelter building; roof repairs only.",
    "No plans to renovate the industrial building into an emergency shelter.",
    "Previously renovated the industrial building into an emergency shelter.",
    "Renovate the industrial building. The neighboring building will become a shelter.",
    "Renovate the industrial building into full code compliance.",
])
def test_repairs_negated_and_historical_reuse_do_not_gain_discovery_from_rationale(source):
    assert not relevance_projection("development", "redevelopment", "Proposed building reuse.", source)[2]


@pytest.mark.parametrize("source", [
    "Parking variance for an existing lawful multifamily use; no conversion proposed.",
    "Apartments previously converted in 1998; routine repair.",
    "No proposed conversion to apartments.",
    "Conversion to multifamily is not proposed.",
    "An accessory garage for an existing apartment building.",
    "An office conversion. The neighboring building contains apartments.",  # separate sentences
])
def test_rationale_alone_cannot_promote_existing_use_or_neighbor(source):
    assert not relevance_projection("minor_property", "property_relief",
                                    "Proposed apartment conversion.", source)[2]


def repair_fixture():
    filler = "SYNTHETIC ADMINISTRATIVE RECORD. " * 37
    excerpt = "conversion of a single-family home into 2 units"
    matter = "\n22 Cedar Street: proposed " + excerpt + ".\n"
    source = filler + matter + ("Administrative padding. " * 70)
    doc = passage_document(source)
    target = next(p for p in doc.passages if excerpt in p.text)
    wrong = doc.passages[doc.passages.index(target) + 1]
    wire = simple(source, "The proposal at 22 Cedar Street converts the home to two units.")
    item = wire["extractions"][0]
    item["what_happened"]["passage_ids"] = [target.passage_id]
    item["parcel_references"] = [{"text": "22 Cedar Street", "passage_ids": [target.passage_id]}]
    item["relevance"].update(category="development", scope="conversion", source_text=excerpt)
    item["relevance"]["basis"]["passage_ids"] = [wrong.passage_id]
    return source, wire, target, wrong


def test_unique_adjacent_excerpt_repaired_with_identity_and_original_preserved():
    source, wire, target, wrong = repair_fixture()
    original = deepcopy(wire)
    reviewed = review_claims(wire, source)
    assert len(reviewed["extractions"]) == 1
    assert wire == original
    assert reviewed["citation_repairs"][0]["from_passage_ids"] == [wrong.passage_id]
    assert target.passage_id in reviewed["citation_repairs"][0]["to_passage_ids"]
    for span in reviewed["extractions"][0]["evidence_spans"]:
        assert span["quote"] == source[span["start"]:span["end"]]


@pytest.mark.parametrize("failure", ["duplicate", "identity", "narrative", "invented", "unknown_id"])
def test_citation_repair_never_guesses_an_ambiguous_or_unbound_excerpt(failure):
    source, wire, target, wrong = repair_fixture()
    item = wire["extractions"][0]
    if failure == "duplicate":
        source += "\n" + ("Distant administrative section. " * 100) + item["relevance"]["source_text"]
        wire["source_sha256"] = passage_document(source).source_sha256
    elif failure == "identity":
        item["parcel_references"] = []
    elif failure == "narrative":
        item["what_happened"]["passage_ids"] = [wrong.passage_id]
    elif failure == "invented":
        item["relevance"]["source_text"] = "a proposed conversion into one hundred apartments"
    else:
        item["relevance"]["basis"]["passage_ids"] = ["made-up"]
    reviewed = review_claims(wire, source)
    assert reviewed["extractions"] == []
    assert reviewed["citation_repairs"] == []


def test_coverage_does_not_treat_whole_paragraph_citation_as_all_matters_covered():
    source = "SYNTHETIC ADMINISTRATIVE HEADER\n" * 30 + (
        "\nSolAmerica – Orwig Road permitting update\n"
        "Baker – request to remove plan from agenda\n"
        "18 Cedar Street variance\nNext Conditional Use Case # CUH 2026-10\n")
    result = review_coverage(source, [{"project_name": "18 Cedar Street variance",
        "supporting_text": source, "evidence_spans": [{"quote": source}]}])
    assert result["needs_review"]
    assert {a["text"] for a in result["unmatched_anchors"]} == {"SolAmerica", "Baker"}
    assert result["matched_count"] == 1
    for anchor in result["unmatched_anchors"]:
        assert source[anchor["start"]:anchor["end"]] == anchor["text"]


def test_empty_output_can_still_require_coverage_review():
    source = "SYNTHETIC HEADER\n" * 60 + "\nZHB 2026-12 | 22 Cedar Street variance\n"
    result = review_claims({"source_sha256": passage_document(source).source_sha256,
                           "extractions": []}, source)
    assert result["extractions"] == []
    assert result["coverage"]["needs_review"]
    assert result["coverage"]["unmatched_count"] == 2


def test_coverage_list_is_bounded_without_hiding_truncation():
    source = "SYNTHETIC HEADER\n" * 60 + "\n".join(
        f"{n} Cedar Street variance" for n in range(1, 51))
    result = review_coverage(source, [], limit=5)
    assert result["unmatched_count"] == 50
    assert len(result["unmatched_anchors"]) == 5
    assert result["truncated"]


def test_named_discussion_request_is_not_mistaken_for_a_street_number():
    source = "SYNTHETIC HEADER\n" * 60 + (
        "\n4. Discussion Request – Cedar Lot #3 Birch Dr – Cul-De-Sac Improvements\n"
        "Board voted to remove the item from future agendas.\n")
    result = review_coverage(source, [])
    assert [a["text"] for a in result["unmatched_anchors"]] == ["Cedar Lot #3 Birch Dr"]
    assert result["unmatched_anchors"][0]["kind"] == "named_heading"
