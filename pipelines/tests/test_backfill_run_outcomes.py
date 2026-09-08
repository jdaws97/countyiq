"""Backfills must distinguish exhausted work, interrupted work and systemic failure."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from countyiq.assets.enrichment import record_explanations as explanations
from countyiq.lib import municipal_evidence_pipeline as evidence
from countyiq.lib.llm_harness import HarnessConfig
from countyiq.lib.pass_llm_config import PassSpendLimitExceeded


@pytest.fixture(params=["evidence", "municipal", "property"])
def backfill(request, monkeypatch):
    """Exercise real orchestration and budgets with database/provider edges stubbed."""
    kind = request.param
    pass_number = 0 if kind == "evidence" else 3
    monkeypatch.setenv(f"COUNTYIQ_PASS{pass_number}_BACKFILL_MODE", "false")
    monkeypatch.setenv(f"COUNTYIQ_PASS{pass_number}_MAX_ITEMS", "25")
    monkeypatch.setenv("COUNTYIQ_PASS3_MODE", "records")
    monkeypatch.setenv("COUNTYIQ_ERROR_BUDGET", "0.3")
    config = HarnessConfig(model_path="test/backfill", max_tokens=256)
    runtime = evidence if kind == "evidence" else explanations
    monkeypatch.setattr(
        runtime, "resolve_pass_harness", Mock(return_value=(config, Mock()))
    )
    previous = []
    rows = [
        {
            "id": identifier,
            "subject_key": f"proceeding:{identifier}",
            "content_hash": "source-hash",
            "raw_text": "Retained municipal source text. " * 20,
            "body_name": "Example Township Board",
            "meeting_date": "2026-09-01",
            "proceeding_type": "board_minutes",
            "document_url": "https://example.test/meeting.pdf",
        }
        for identifier in range(1, 7)
    ]

    class Database:
        @contextmanager
        def dict_cursor(self):
            cursor = Mock()
            cursor.fetchall.side_effect = (
                [rows, previous] if kind == "evidence" else [previous]
            )
            yield cursor

    context = SimpleNamespace(log=Mock(), op_config={})
    prepared = Mock(return_value=(None, []))
    generated = Mock(return_value={} if kind == "evidence" else ({}, 1))
    persisted = Mock(return_value=SimpleNamespace(accepted=True))
    if kind == "evidence":
        monkeypatch.setattr(evidence, "prepare_source", prepared)
        monkeypatch.setattr(evidence, "read_evidence", generated)
        monkeypatch.setattr(evidence, "persist_evidence", persisted)
        monkeypatch.setattr(
            "countyiq.assets.enrichment.proceeding_extraction._update_pass_status",
            Mock(),
        )
        identity_config = evidence.replace(
            config, temperature=0, top_k=0, top_p=1, require_parameters=True
        )

        def identity(row):
            return evidence.content_hash(
                {
                    "record": evidence.record_snapshot(row),
                    "reader": evidence.reader_identity(identity_config),
                }
            )

        def run():
            return evidence.run_municipal_evidence(
                context, Database(), "pending query", {}
            )

    else:
        monkeypatch.setattr(
            explanations,
            "_source_bundles",
            lambda *args, **kwargs: (len(rows), iter(rows)),
        )
        monkeypatch.setattr(explanations, "generate_explanation", generated)
        monkeypatch.setattr(explanations, "persist_explanation", persisted)
        identity_config = explanations.configure_explanation_harness(config, kind)

        def identity(row):
            return explanations.explanation_identity(row, identity_config)

        def run():
            return explanations.run_explanations(context, Database(), kind)

    return SimpleNamespace(
        run=run,
        rows=rows,
        previous=previous,
        identity=identity,
        generated=generated,
        persisted=persisted,
        prepared=prepared,
        kind=kind,
        pass_number=pass_number,
    )


def test_systemic_validation_failure_fails_the_backfill(backfill):
    backfill.generated.side_effect = ValueError("Invalid source response")
    with pytest.raises(RuntimeError, match="error budget exceeded.*6/6"):
        backfill.run()
    backfill.persisted.assert_not_called()


@pytest.mark.parametrize("backfill", ["evidence"], indirect=True)
def test_systemic_source_preparation_failure_fails_pass0(backfill):
    backfill.prepared.side_effect = ValueError("Unreadable source")
    with pytest.raises(RuntimeError, match="error budget exceeded.*6/6"):
        backfill.run()
    backfill.generated.assert_not_called()


@pytest.mark.parametrize("accepted_before_stop", [0, 2])
def test_spend_stop_reports_pending_work(backfill, accepted_before_stop):
    success = backfill.generated.return_value
    backfill.generated.side_effect = [
        *([success] * accepted_before_stop),
        PassSpendLimitExceeded("Budget exhausted"),
    ]
    metadata = backfill.run().metadata
    assert metadata["status"] == "partial"
    assert metadata["stop_reason"] == "spend_limit"
    assert metadata["remaining"] == 6 - accepted_before_stop
    assert backfill.persisted.call_count == accepted_before_stop
    assert backfill.generated.call_count == accepted_before_stop + 1


@pytest.mark.parametrize("limit, remaining", [(2, 4), (6, 0)])
def test_item_cap_only_reports_complete_when_scope_is_exhausted(
    backfill, monkeypatch, limit, remaining
):
    monkeypatch.setenv(f"COUNTYIQ_PASS{backfill.pass_number}_MAX_ITEMS", str(limit))
    metadata = backfill.run().metadata
    assert metadata["remaining"] == remaining
    assert metadata["eligible_in_scope"] == 6
    assert metadata["status"] == ("partial" if remaining else "complete")
    assert metadata["stop_reason"] == ("item_limit" if remaining else "scope_exhausted")
    assert backfill.generated.call_count == limit


def test_unchanged_records_do_not_consume_cap_or_remain_pending(backfill, monkeypatch):
    monkeypatch.setenv(f"COUNTYIQ_PASS{backfill.pass_number}_MAX_ITEMS", "2")
    backfill.previous.extend(
        {"subject_key": row["subject_key"], "input_hash": backfill.identity(row)}
        for row in backfill.rows[2:]
    )
    metadata = backfill.run().metadata
    assert metadata["status"] == "complete"
    assert metadata["remaining"] == 0
    assert metadata["unchanged"] == 4
    assert backfill.generated.call_count == 2


@pytest.mark.parametrize("changed", [False, True])
def test_subscription_outputs_avoid_paid_rework_only_while_source_is_current(
    backfill, changed
):
    for row in backfill.rows:
        prior = {
            "subject_key": row["subject_key"],
            "input_hash": "different-subscription-config",
            "provider": "codex_subscription",
        }
        if backfill.kind == "evidence":
            snapshot = evidence.record_snapshot(row)
            if changed:
                snapshot["content_hash"] = "old-source"
            prior.update(
                prompt_version=evidence.REVIEW_VERSION,
                payload={
                    "record_snapshot": snapshot,
                    "reader_policy": evidence.READER_POLICY_VERSION,
                    "value_policy": evidence.VALUE_POLICY_VERSION,
                },
            )
        else:
            prior.update(
                prompt_version=explanations.PROMPT_VERSION,
                source_hash="old-source" if changed else explanations.content_hash(row),
            )
        backfill.previous.append(prior)
    metadata = backfill.run().metadata
    assert metadata["status"] == "complete"
    assert metadata["unchanged"] == (0 if changed else 6)
    assert backfill.generated.call_count == (6 if changed else 0)


@pytest.mark.parametrize("outcome", ["error", "quarantine"])
def test_unaccepted_work_remains_pending_after_scope_is_traversed(backfill, outcome):
    if outcome == "error":
        backfill.generated.side_effect = [
            ValueError("One invalid source"),
            *([backfill.generated.return_value] * 5),
        ]
    else:
        backfill.persisted.side_effect = [
            SimpleNamespace(accepted=False),
            *([SimpleNamespace(accepted=True)] * 5),
        ]
    metadata = backfill.run().metadata
    assert metadata["status"] == "partial"
    assert metadata["stop_reason"] == "scope_exhausted"
    assert metadata["remaining"] == 1


def test_empty_scope_is_complete_without_dispatch(backfill):
    backfill.rows.clear()
    metadata = backfill.run().metadata
    assert metadata["status"] == "complete"
    assert metadata["remaining"] == 0
    backfill.generated.assert_not_called()


@pytest.mark.parametrize("backfill", ["property"], indirect=True)
def test_unavailable_property_source_is_not_reported_as_explained(backfill):
    backfill.rows[0] = None
    metadata = backfill.run().metadata
    assert metadata["status"] == "partial"
    assert metadata["unavailable"] == 1
    assert metadata["remaining"] == 1
    assert backfill.generated.call_count == 5


def test_property_scope_count_does_not_eagerly_prepare_spatial_context():
    cursor = Mock()
    cursor.fetchall.return_value = [{"pidn": "one"}, {"pidn": "two"}]
    cursor.fetchone.side_effect = [{"source": None}, {"source": {"pidn": "two"}}]

    class Database:
        @contextmanager
        def dict_cursor(self):
            yield cursor

    count, sources = explanations._source_bundles(Database(), "property")
    assert count == 2
    cursor.fetchone.assert_not_called()
    assert next(sources) is None
    assert cursor.fetchone.call_count == 1
    assert next(sources) == {"pidn": "two"}
    with pytest.raises(StopIteration):
        next(sources)
