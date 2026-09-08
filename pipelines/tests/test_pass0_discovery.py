from copy import deepcopy

import pytest
from countyiq.lib.pass0_source import index_source
from eval.pass0_discovery import DEFERRED_FIELDS, review_discovery

from tests.test_pass0_facts import consent_fixture


def test_discovery_preserves_actions_without_claiming_deferred_fields_are_empty():
    source, payload = consent_fixture()
    for field in DEFERRED_FIELDS:
        del payload["matters"][0][field]
    original = deepcopy(payload)

    review = review_discovery(payload, index_source(source))

    assert not review["envelope_errors"]
    assert not review["rejected"]
    matter = review["matters"][0]
    assert matter["decisions"][0]["outcome"] == "approved"
    assert matter["summary"]["text"]
    assert matter["deferred_fields"] == ["conditions", "milestones"]
    assert "conditions" not in matter
    assert "milestones" not in matter
    assert matter["semantic_review_complete"] is False
    assert payload == original


def test_discovery_rejects_unsourced_actions_and_does_not_accept_full_enrichment():
    source, payload = consent_fixture()
    document = index_source(source)
    assert review_discovery(payload, document)["envelope_errors"]
    for field in DEFERRED_FIELDS:
        del payload["matters"][0][field]
    payload["matters"][0]["decisions"][0]["result"] = [[999, 999]]

    review = review_discovery(payload, document)

    assert review["rejected"]
    assert not review["matters"]
    assert not review["source_candidates"]


def test_bad_excerpt_keeps_source_for_revisit_without_promoting_failed_actions():
    source, payload = consent_fixture()
    for field in DEFERRED_FIELDS:
        del payload["matters"][0][field]
    item = payload["matters"][0]
    item["summary"]["excerpts"][0]["end"] = "invented quotation"
    item["decisions"][0]["result"] = [[999, 999]]
    original = deepcopy(payload)
    document = index_source(source)

    review = review_discovery(payload, document)

    assert review["rejected"]
    assert not review["matters"]
    candidate = review["source_candidates"][0]
    assert candidate["semantic_review_complete"] is False
    assert candidate["review_flags"] == ["source_selection_review_needed"]
    assert "decisions" not in candidate
    assert "status" not in candidate
    assert candidate["original_excerpt_selection"] == item["summary"]["excerpts"]
    for passage in candidate["source_passages"]:
        assert passage["quote"] == source[passage["start"] : passage["end"]]
        assert passage["source_sha256"] == document.sha256
        assert "invented quotation" not in passage["quote"]
    assert payload == original


@pytest.mark.parametrize("lines", [[0, 3], [3, 2], [2, 999]])
def test_invalid_source_bounds_cannot_become_a_revisit_candidate(lines):
    source, payload = consent_fixture()
    for field in DEFERRED_FIELDS:
        del payload["matters"][0][field]
    payload["matters"][0]["summary"]["excerpts"][0]["lines"] = lines

    review = review_discovery(payload, index_source(source))

    assert not review["matters"]
    assert not review.get("source_candidates", [])
