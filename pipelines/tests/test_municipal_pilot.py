from copy import deepcopy
import json
import pytest
from eval.municipal_pilot import digest, evaluate_format, load_sources, validate_manifest_record, prompt_for


def source():
    return dict(id=1, body_name="York City Planning Commission", meeting_date="2026-08-10",
                proceeding_type="planning_commission", document_url="https://example.test/meeting.pdf",
                content_hash="bytes", raw_text="An unchanged source document.")


def test_manifest_refuses_changed_text_and_wrong_source_identity():
    row = source()
    record = {**row, "raw_text_sha256": digest(row["raw_text"])}
    validate_manifest_record(record, row, {1})
    for field in ("raw_text", "body_name", "meeting_date", "document_url", "content_hash"):
        changed = {**row, field: "changed"}
        with pytest.raises(ValueError, match="changed"):
            validate_manifest_record(record, changed, {1})
    with pytest.raises(ValueError, match="no longer eligible"):
        validate_manifest_record(record, row, set())


@pytest.mark.parametrize("parsed", [None, [], {}, {"extractions": None}, {"extractions": ["invalid"]}])
def test_invalid_paid_responses_remain_reportable(parsed):
    result = evaluate_format(parsed, "Some source text.")
    assert not result["runtime_gate_passed"]


def test_empty_extraction_is_format_valid_not_semantic_approval():
    result = evaluate_format({"source_sha256": digest("Some source text."), "extractions": []}, "Some source text.")
    assert result["runtime_gate_passed"]
    assert result["semantic_review_complete"] is False


def test_duplicate_or_oversized_manifest_rejected_before_db():
    for ids in [[1,1],list(range(31)),[]]:
        with pytest.raises(ValueError, match="1–30 distinct"):
            load_sources({"records":[{"id":i} for i in ids]})


def test_prompt_uses_current_document_metadata_and_whole_text():
    row=source()
    prompt=prompt_for(row)
    assert row["body_name"] in prompt
    assert row["meeting_date"] in prompt
    indexed = json.loads(prompt.split("SOURCE PASSAGES:\n", 1)[1])
    assert "".join(p["text"] for p in indexed["passages"]) == row["raw_text"]
    assert indexed["source_sha256"] == digest(row["raw_text"])
