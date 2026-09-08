"""Real canary failures must fail closed without losing neighboring cases."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
from countyiq.lib.llm_harness import HarnessConfig, HarnessResult
from countyiq.lib.municipal_evidence import bind_review, source_document
from countyiq.lib.municipal_evidence_pipeline import read_evidence
from countyiq.lib.municipal_subjects import validate_subject_cards

CASES = json.loads(
    (Path(__file__).parent / "fixtures/municipal_subject_boundaries.json").read_text()
)


def source(case):
    return source_document([{"page": None, "text": case["raw_text"]}])[0]


@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case["proceeding_id"]))
def test_observed_cumulative_cases_are_rejected(case):
    result = bind_review(case["invalid_cumulative_selection"], [], source(case))
    assert result["status"] == "partial"
    assert any("Substantive passages overlap" in error for error in result["errors"])


@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case["proceeding_id"]))
def test_separate_cases_preserve_shared_context_and_correct_sites(case):
    document = source(case)
    result = bind_review(case["corrected_selection"], [], document)
    assert result["status"] == "complete", result["errors"]
    assert len(result["cards"]) == len(case["invalid_cumulative_selection"]["items"])
    for card in result["cards"]:
        assert [ref["text"] for ref in card["references"]] == case[
            "expected_subject_references"
        ].get(card["title"], [])
        for passage in card["passages"]:
            assert passage["text"] == document.text[passage["start"] : passage["end"]]
    if case["proceeding_id"] == 8268:
        hearings = result["cards"][6:8]
        for card in hearings:
            assert "July 16, 7 p.m." in card["context_passages"][0]["text"]
            assert len(card["subject_passages"]) == 1
        assert "Eichelberger" not in hearings[0]["subject_passages"][0]["text"]
        assert "Landing" not in hearings[1]["subject_passages"][0]["text"]


@pytest.mark.parametrize("field", ["context", "references"])
def test_missing_attribution_contract_is_not_implicitly_accepted(field):
    payload = deepcopy(CASES[0]["corrected_selection"])
    del payload["items"][0][field]
    assert bind_review(payload, [], source(CASES[0]))["status"] == "invalid"


def test_neighbor_cannot_be_hidden_in_shared_context():
    payload = deepcopy(CASES[0]["corrected_selection"])
    payload["items"][3]["context"].append([27, 27])
    result = bind_review(payload, [], source(CASES[0]))
    assert result["status"] == "partial"
    assert any("Shared context" in error for error in result["errors"])


def test_reference_cannot_borrow_a_neighbor_or_shared_context():
    payload = deepcopy(CASES[0]["corrected_selection"])
    payload["items"][3]["references"] = payload["items"][2]["references"]
    result = bind_review(payload, [], source(CASES[0]))
    assert result["status"] == "partial"
    assert any("Reference is outside" in error for error in result["errors"])


@pytest.mark.parametrize(
    "role", ["speaker_address", "meeting_venue", "subject_property"]
)
def test_literal_role_is_retained_with_original_surrounding_units(role):
    document, _ = source_document(
        [{"page": 1, "text": "Stormwater hearing\n1 Main Street\nSuite 4\n"}]
    )
    payload = {
        "items": [
            {
                "index": None,
                "title": "Stormwater hearing",
                "passages": [[1, 2]],
                "context": [],
                "references": [
                    {"quote": "1 Main Street", "lines": [2, 2], "role": role}
                ],
            }
        ]
    }
    result = bind_review(payload, [], document)
    assert result["status"] == "complete", result["errors"]
    reference = result["cards"][0]["references"][0]
    assert reference["role"] == role
    assert "Suite 4" in reference["context"]["text"]


def test_joined_ocr_address_requires_the_complete_source_token():
    document, _ = source_document(
        [
            {
                "page": None,
                "text": "Council approved the parking application for312 N. 4th\nStreet.\n",
            }
        ]
    )
    payload = {
        "items": [
            {
                "index": None,
                "title": "parking application",
                "passages": [[1, 2]],
                "context": [],
                "references": [
                    {
                        "quote": "312 N. 4th Street",
                        "lines": [1, 2],
                        "role": "subject_property",
                    }
                ],
            }
        ]
    }
    rejected = bind_review(payload, [], document)
    assert rejected["status"] == "partial"
    assert "complete source tokens" in rejected["errors"][0]

    payload["items"][0]["references"][0]["quote"] = "for312 N. 4th Street"
    accepted = bind_review(payload, [], document)
    assert accepted["status"] == "complete", accepted["errors"]
    reference = accepted["cards"][0]["references"][0]
    assert reference["text"] == "for312 N. 4th\nStreet"
    assert document.text[reference["start"] : reference["end"]] == reference["text"]


@pytest.mark.parametrize("mutation", ["text", "hash", "bounds", "missing", "scalar"])
def test_storage_revalidates_reference_provenance(mutation):
    document = source(CASES[0])
    cards = bind_review(CASES[0]["corrected_selection"], [], document)["cards"]
    reference = cards[2]["references"][0]
    if mutation == "text":
        reference["text"] = "96 Butter Rd"
    elif mutation == "hash":
        reference["source_text_sha256"] = "0" * 64
    elif mutation == "bounds":
        reference["end"] = 10**30
    elif mutation == "missing":
        del reference["start"]
    else:
        cards[2]["references"][0] = "95 Butter Rd"
    with pytest.raises(ValueError):
        validate_subject_cards(cards, document)


def test_runtime_corrects_the_observed_failure_once_using_full_original_source():
    case = CASES[0]
    invoke = Mock(
        side_effect=[
            HarnessResult("{}", case["invalid_cumulative_selection"], True),
            HarnessResult("{}", case["corrected_selection"], True),
        ]
    )
    document = source(case)
    reviewed = read_evidence(document, HarnessConfig(model_path="test/reader"), invoke)
    assert reviewed["validation_attempts"] == 2
    assert len(reviewed["cards"]) == 6
    original, correction = invoke.call_args_list
    assert correction.args[1].startswith(original.args[1])
    assert "Substantive passages overlap" in correction.args[1]
    assert original.kwargs["archive_key"].endswith(":attempt:1")
    assert correction.kwargs["archive_key"].endswith(":attempt:2")
    assert original.kwargs["retries"] == correction.kwargs["retries"] == 0


def test_second_invalid_selection_is_never_published_or_retried_again():
    case = CASES[1]
    invoke = Mock(
        return_value=HarnessResult("{}", case["invalid_cumulative_selection"], True)
    )
    with pytest.raises(ValueError, match="Substantive passages overlap"):
        read_evidence(source(case), HarnessConfig(model_path="test/reader"), invoke)
    assert invoke.call_count == 2


@pytest.mark.parametrize(
    ("text", "quote", "ranges", "correction_hint"),
    [
        (
            "Subdivision at 1 Main Street\nPlan for 1 Main Street\n",
            "1 Main Street",
            [1, 2],
            "ambiguous",
        ),
        (
            "Subdivision parcel 29-000-NA-0022.A0-\n00000\n",
            "29-000-NA-0022.A0-00000",
            [1, 2],
            "not literal",
        ),
    ],
)
def test_reference_error_identifies_quote_range_and_original_source(
    text, quote, ranges, correction_hint
):
    document, _ = source_document([{"page": 1, "text": text}])
    payload = {
        "items": [
            {
                "index": None,
                "title": "Subdivision",
                "passages": [[1, 2]],
                "context": [],
                "references": [
                    {"quote": quote, "lines": ranges, "role": "subject_property"}
                ],
            }
        ]
    }
    result = bind_review(payload, [], document)
    assert result["status"] == "partial"
    error = result["errors"][0]
    assert repr(quote) in error
    assert "lines 1-2" in error
    assert "Selected source:" in error
    assert correction_hint in error
    assert "smallest range containing one occurrence" in error


def test_wrapped_parcel_id_keeps_original_bytes_in_the_bound_reference():
    text = "Subdivision parcel 29-000-NA-0022.A0-\n00000\n"
    document, _ = source_document([{"page": 1, "text": text}])
    payload = {
        "items": [
            {
                "index": None,
                "title": "Subdivision",
                "passages": [[1, 2]],
                "context": [],
                "references": [
                    {
                        "quote": "29-000-NA-0022.A0- 00000",
                        "lines": [1, 2],
                        "role": "subject_property",
                    }
                ],
            }
        ]
    }
    result = bind_review(payload, [], document)
    assert result["status"] == "complete", result["errors"]
    assert result["cards"][0]["references"][0]["text"] == "29-000-NA-0022.A0-\n00000"
