"""Regression coverage for municipal evidence orchestration gates."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import countyiq.lib.municipal_evidence_pipeline as pipeline
import pytest
from countyiq.lib.llm_harness import HarnessConfig, HarnessResult
from countyiq.lib.municipal_evidence_pipeline import (
    persist_evidence,
    prepare_source,
    read_evidence,
    reader_identity,
)
from countyiq.lib.pass0_source import index_source
from countyiq.lib.source_rights import MunicipalitySourceAuthorization


def harness_config() -> HarnessConfig:
    return HarnessConfig(model_path="test/municipal-reader", max_tokens=256)


def source_row(**overrides) -> dict:
    row = {
        "id": 17,
        "content_hash": "source-hash",
        "raw_text": "Municipal record text with enough retained content for local reuse. "
        * 4,
        "body_name": "Example Township Board",
        "meeting_date": "2026-09-01",
        "proceeding_type": "board_minutes",
        "document_url": "https://example.test/meeting.pdf",
    }
    row.update(overrides)
    return row


def test_fixed_scope_rerun_does_not_advance_into_unprocessed_backlog(monkeypatch):
    selected = source_row(id=17)
    unprocessed = source_row(id=18)

    class Cursor:
        queries = 0

        def execute(self, _query):
            self.queries += 1

        def fetchall(self):
            if self.queries == 1:
                return [selected, unprocessed]
            return [{"subject_key": "proceeding:17", "input_hash": fingerprint}]

    class Database:
        @contextmanager
        def dict_cursor(self):
            yield Cursor()

    # Runtime applies these deterministic sampling values before hashing.
    config = pipeline.replace(
        harness_config(), temperature=0, top_k=0, top_p=1, require_parameters=True
    )
    fingerprint = pipeline.content_hash(
        {
            "record": pipeline.record_snapshot(selected),
            "reader": reader_identity(config),
        }
    )
    invoke = Mock(
        side_effect=AssertionError("An unchanged scope must make no model call")
    )
    prepare = Mock(
        side_effect=AssertionError("The unselected backlog must not be read")
    )
    monkeypatch.setattr(
        pipeline, "resolve_pass_harness", lambda *args, **kwargs: (config, invoke)
    )
    monkeypatch.setattr(pipeline, "prepare_source", prepare)
    result = pipeline.run_municipal_evidence(
        SimpleNamespace(log=Mock()),
        Database(),
        "eligible source query",
        {},
        proceeding_ids=[17],
    )
    assert result.metadata["eligible_in_scope"] == 1
    assert result.metadata["unchanged"] == 1
    assert result.metadata["processed"] == 0
    invoke.assert_not_called()
    prepare.assert_not_called()


def test_fixed_scope_refuses_now_ineligible_document():
    with pytest.raises(ValueError, match="not eligible: \\[19\\]"):
        pipeline.select_proceedings([source_row(id=17)], [17, 19])


def authorization() -> MunicipalitySourceAuthorization:
    return MunicipalitySourceAuthorization(
        source_key="example_township_board",
        body_name="Example Township Board",
        listing_url="https://example.test/meetings",
        acquisition_method="public_download",
        raw_retention_allowed=True,
        derived_product_allowed=True,
        raw_export_allowed=False,
        allowed_origins=frozenset({"https://example.test"}),
        robots_unavailable_risk_accepted=False,
    )


def bound_review(document) -> dict:
    span = {
        "start": 0,
        "end": len(document.text),
        "text": document.text,
        "source_text_sha256": document.sha256,
    }
    return {
        "status": "complete",
        "cards": [
            {
                "id": "card-1",
                "title": "Example project",
                "subject": span,
                "passages": [span],
                "selection_contract": "subject-passages-v1",
                "subject_passages": [span],
                "context_passages": [],
                "references": [],
            }
        ],
        "warnings": [],
        "requested_model": "test/municipal-reader",
    }


def test_provider_failure_is_not_retried_and_invalid_ranges_fail_closed():
    document = index_source("Named project\nSource text\n")
    calls = []

    def failed_invoke(*_args, **kwargs):
        calls.append(kwargs)
        return HarnessResult("", None, False, error="provider unavailable")

    with pytest.raises(ValueError, match="provider unavailable"):
        read_evidence(document, harness_config(), failed_invoke)
    assert calls == [
        {"retries": 0, "archive_key": f"municipal-source:{document.sha256}:attempt:1"}
    ]

    def partial_invoke(*_args, **_kwargs):
        return HarnessResult(
            "{}",
            {
                "items": [
                    {
                        "index": None,
                        "title": "Named project",
                        "passages": [[1, 999]],
                        "context": [],
                        "references": [],
                    }
                ]
            },
            True,
        )

    with pytest.raises(ValueError):
        read_evidence(document, harness_config(), partial_invoke)


def test_read_evidence_supplies_complete_source_even_for_empty_result():
    document = index_source("Named project\nSource text\nLast source line\n")
    calls = []

    def empty_invoke(config, prompt, **kwargs):
        calls.append((config, prompt, kwargs))
        return HarnessResult("{}", {"items": []}, True)

    assert read_evidence(document, harness_config(), empty_invoke) == {
        "status": "complete",
        "cards": [],
        "errors": [],
        "warnings": [],
        "requested_model": "test/municipal-reader",
        "value_decision": "read_non_accounting_source",
        "validation_attempts": 1,
    }
    assert len(calls) == 1
    assert "Named project" in calls[0][1]
    assert "Last source line" in calls[0][1]
    assert calls[0][2] == {
        "retries": 0,
        "archive_key": f"municipal-source:{document.sha256}:attempt:1",
    }


@pytest.mark.parametrize(
    ("model", "effort", "strict_schema"),
    [
        ("z-ai/glm-5.3-flash", "high", True),
        ("deepseek/deepseek-v4-flash-0731", "low", False),
    ],
)
def test_reader_keeps_requested_model_and_validated_family_contract(
    model, effort, strict_schema
):
    document = index_source("Named capital project report.\n" * 1_000)
    calls = []

    def invoke(config, prompt, **kwargs):
        calls.append((config, prompt, kwargs))
        return HarnessResult('{"items": []}', {"items": []}, True)

    config = HarnessConfig(
        model_path=model,
        max_tokens=8_192,
        max_price_prompt=3.0,
        max_price_completion=15.0,
    )
    result = read_evidence(document, config, invoke)
    assert result["requested_model"] == model
    assert len(calls) == 1
    request, prompt, kwargs = calls[0]
    assert request.model_path == model
    assert request.max_tokens == 8_192
    assert request.reasoning_effort == effort
    assert bool(request.json_schema) is strict_schema
    assert request.max_price_prompt == 0.16
    assert request.max_price_completion == (0.55 if strict_schema else 0.32)
    assert ("Required output JSON schema:" in prompt) is not strict_schema
    assert kwargs == {
        "retries": 0,
        "archive_key": f"municipal-source:{document.sha256}:attempt:1",
    }


@pytest.mark.parametrize("mutation", ["text", "hash"])
def test_persist_evidence_rejects_mutated_spans_before_database_gate(
    monkeypatch, mutation
):
    document = index_source("Example project\n")
    reviewed = bound_review(document)
    span = reviewed["cards"][0]["passages"][0]
    if mutation == "text":
        span["text"] = "different source text"
    else:
        span["source_text_sha256"] = "wrong-hash"
    gate_calls = []
    monkeypatch.setattr(
        pipeline,
        "record_inference_decision",
        lambda *_args, **_kwargs: gate_calls.append(True),
    )

    with pytest.raises(ValueError, match="Evidence changed after source binding"):
        persist_evidence(
            object(), source_row(), document, [], reviewed, harness_config()
        )
    assert gate_calls == []


def test_persist_evidence_records_immutable_source_snapshot_and_reader(monkeypatch):
    document = index_source("Example project\n")
    captured = {}
    sentinel = object()
    monkeypatch.setattr(
        pipeline,
        "record_inference_decision",
        lambda database, **kwargs: (
            captured.update(database=database, **kwargs) or sentinel
        ),
    )
    config = harness_config()
    row = source_row()

    result = persist_evidence(
        object(),
        row,
        document,
        [{"page": 1, "start": 0, "end": 16}],
        bound_review(document),
        config,
    )

    assert result is sentinel
    assert captured["payload"]["record_snapshot"] == {
        "content_hash": row["content_hash"],
        "raw_text_sha256": pipeline.hashlib.sha256(
            row["raw_text"].encode()
        ).hexdigest(),
        "body_name": row["body_name"],
        "meeting_date": row["meeting_date"],
        "proceeding_type": row["proceeding_type"],
        "document_url": row["document_url"],
    }
    assert captured["payload"]["reader_identity"] == reader_identity(config)
    assert captured["payload"]["coverage"] == "value_filtered_source_read"


def test_prepare_source_uses_retained_text_without_download(monkeypatch):
    row = source_row()
    monkeypatch.setattr(
        pipeline,
        "get_with_robots",
        lambda *_args, **_kwargs: pytest.fail("retained text must not download"),
    )
    monkeypatch.setattr(
        pipeline,
        "municipality_source_key",
        lambda _body_name: "example_township_board",
    )

    document, pages = prepare_source(
        row,
        {"example_township_board": authorization()},
        robots=object(),
    )

    assert document.text.startswith(row["raw_text"])
    assert pages == [{"page": None, "start": 0, "end": len(row["raw_text"])}]


def test_prepare_source_refuses_unavailable_authorization_before_download(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "get_with_robots",
        lambda *_args, **_kwargs: pytest.fail(
            "missing authorization must not download"
        ),
    )

    with pytest.raises(ValueError, match="no current authorization"):
        prepare_source(source_row(raw_text=""), {}, robots=object())


@pytest.mark.parametrize(
    "changed_field",
    ["raw_text", "content_hash", "document_url", "meeting_date", "body_name"],
)
def test_resolution_rechecks_live_source_before_applying_an_evidence_choice(
    changed_field,
):
    from countyiq.lib.intelligence_integrity import content_hash
    from countyiq.lib.intelligence_resolution import _current_source_hash
    from countyiq.lib.municipal_evidence_pipeline import record_snapshot

    row = source_row()
    snapshot = record_snapshot(row)
    payload = {"record_snapshot": snapshot, "source_text_sha256": "ocr-text-hash"}
    contradiction = {
        "output_kind": "municipal_evidence",
        "subject_key": "proceeding:17",
    }

    class Cursor:
        def execute(self, _sql, _params):
            pass

        def fetchone(self):
            return row

    assert _current_source_hash(
        Cursor(), contradiction, {}, {"payload": payload}
    ) == content_hash({"record": snapshot, "text": "ocr-text-hash"})
    row[changed_field] = "changed"
    assert _current_source_hash(Cursor(), contradiction, {}, {"payload": payload}) == ""
