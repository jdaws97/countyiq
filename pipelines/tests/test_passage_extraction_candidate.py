from copy import deepcopy
import pytest
from jsonschema import Draft202012Validator
from eval.passage_extraction_contract import (
    CANDIDATE_SCHEMA,
    hydrate_extractions,
    passage_input,
)
from countyiq.lib.pass_schemas import PASS0_EXTRACTION_SCHEMA
from countyiq.lib.source_passages import index_source_passages
from countyiq.lib.intelligence_integrity import validate_pass0_extractions


def fixture():
    document = index_source_passages("The board approved the application.")
    fields = CANDIDATE_SCHEMA["properties"]["extractions"]["items"]["properties"]
    item = {}
    for key, schema in fields.items():
        if schema["type"] == "array":
            item[key] = []
        elif isinstance(schema["type"], list):
            item[key] = None
        elif "enum" in schema:
            item[key] = schema["enum"][0]
        else:
            item[key] = ""
    item.update(
        what_happened="The board approved the application.",
        decision="approved",
        record_status="decision",
        evidence_refs=[
            {
                "passage_ids": [document.passages[0].passage_id],
                "fields": ["what_happened", "decision"],
            }
        ],
    )
    return document, {"source_sha256": document.source_sha256, "extractions": [item]}


def test_hydration_recovers_exact_quotes_and_preserves_model_payload():
    document, payload = fixture()
    original = deepcopy(payload)
    result = hydrate_extractions(payload, document)
    Draft202012Validator(PASS0_EXTRACTION_SCHEMA).validate({"extractions": result})
    assert (
        validate_pass0_extractions(
            result, document.passages[0].text, require_contract=True
        )
        == []
    )
    assert result[0]["supporting_text"] == document.passages[0].text
    assert payload == original
    assert "supporting_text" not in payload["extractions"][0]
    assert passage_input(document)["passages"][0]["text"] == document.passages[0].text


@pytest.mark.parametrize(
    "fault",
    [
        "unknown_id",
        "wrong_source",
        "copied_quote",
        "unknown_field",
        "duplicate_id",
        "empty_refs",
    ],
)
def test_invalid_candidate_never_hydrates(fault):
    document, payload = fixture()
    item = payload["extractions"][0]
    ref = item["evidence_refs"][0]
    if fault == "unknown_id":
        ref["passage_ids"] = ["not-in-source"]
    elif fault == "wrong_source":
        payload["source_sha256"] = "0" * 64
    elif fault == "copied_quote":
        ref["quote"] = "An invented quotation"
    elif fault == "unknown_field":
        ref["fields"] = ["imagined_field"]
    elif fault == "duplicate_id":
        ref["passage_ids"] *= 2
    else:
        item["evidence_refs"] = []
    with pytest.raises(ValueError):
        hydrate_extractions(payload, document)


def test_hydration_does_not_waive_existing_decision_gate():
    document, payload = fixture()
    payload["extractions"][0]["record_status"] = "scheduled"
    result = hydrate_extractions(payload, document)
    assert any(
        "completed decision" in error
        for error in validate_pass0_extractions(
            result, document.passages[0].text, require_contract=True
        )
    )


def test_reused_passage_merges_field_assignments_without_duplicate_quote():
    document, payload = fixture()
    payload["extractions"][0]["evidence_refs"].append(
        {"passage_ids": [document.passages[0].passage_id], "fields": ["conditions"]}
    )
    result = hydrate_extractions(payload, document)
    assert len(result[0]["evidence_spans"]) == 1
    assert "conditions" in result[0]["evidence_spans"][0]["fields"]
