"""No-spend preflight receipt checks."""

import hashlib
import json

from countyiq.lib.backfill_authorization import create_backfill_authorization
from scripts.verify_intelligence_preflight import (
    PASS2_REVIEW_FIXTURE,
    _backfill_authorization_check,
    _pass2_review_check,
    _repository_schema_heads,
    build_report,
)


def test_backfill_preflight_requires_matching_durable_authorization(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "pass2-authorization.json"
    create_backfill_authorization(
        path,
        pass_number=2,
        model="openai/gpt-5.6-luna",
        max_cost_usd=12.5,
        max_price_prompt=0.2,
        max_price_completion=1.2,
    )
    monkeypatch.setenv(
        "COUNTYIQ_PASS2_BACKFILL_AUTHORIZATION_FILE", str(path)
    )

    accepted = _backfill_authorization_check(
        target_pass=2,
        backfill_mode=True,
        max_cost_usd=12.5,
        max_price_prompt=0.2,
        max_price_completion=1.2,
    )
    mismatched = _backfill_authorization_check(
        target_pass=2,
        backfill_mode=True,
        max_cost_usd=13.0,
        max_price_prompt=0.2,
        max_price_completion=1.2,
    )

    assert accepted["ok"] is True
    assert accepted["remaining_usd"] == 12.5
    assert mismatched["ok"] is False
    assert "max_cost_usd does not match" in mismatched["reason"]


def test_canary_preflight_requires_durable_authorization(monkeypatch) -> None:
    monkeypatch.delenv(
        "COUNTYIQ_PASS0_BACKFILL_AUTHORIZATION_FILE", raising=False
    )

    result = _backfill_authorization_check(
        target_pass=0,
        backfill_mode=False,
        max_cost_usd=0.10,
        max_price_prompt=0.2,
        max_price_completion=1.2,
    )

    assert result["ok"] is False
    assert "restart-safe canary" in result["reason"]


def test_pass2_review_receipt_requires_every_stability_case(tmp_path) -> None:
    fixture = json.loads(PASS2_REVIEW_FIXTURE.read_text(encoding="utf-8"))
    case_ids = [case["id"] for case in fixture["cases"]]
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps({
            "reviewer": "test-reviewer",
            "reviewed_at": "2026-08-31T12:00:00Z",
            "fixture_sha256": hashlib.sha256(
                PASS2_REVIEW_FIXTURE.read_bytes()
            ).hexdigest(),
            "case_decisions": {case_id: "approved" for case_id in case_ids},
        }),
        encoding="utf-8",
    )

    assert _pass2_review_check(receipt)["ok"] is True

    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["case_decisions"][case_ids[0]] = "pending"
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    assert _pass2_review_check(receipt)["ok"] is False


def test_preflight_reports_old_schema_without_querying_missing_views(monkeypatch):
    class OldSchemaDatabase:
        def execute(self, sql, params=None):
            if "SELECT version_num FROM alembic_version" in sql:
                return [("039",)]
            if "intelligence_integrity_status" in sql:
                raise AssertionError("old-schema integrity views must not be queried")
            raise AssertionError(f"unexpected SQL: {sql}")

    monkeypatch.setattr(
        "scripts.verify_intelligence_preflight.estimate_backfill",
        lambda database, sample_size: {"read_only": True},
    )
    monkeypatch.setattr(
        "scripts.verify_intelligence_preflight.probe_llm_archive_destination",
        lambda: {"ok": True, "path": "/tmp/archive", "reason": "write probe passed"},
    )

    report = build_report(
        OldSchemaDatabase(),
        target_pass=0,
        sample_size=50,
        max_canary_items=25,
        receipt_path=None,
    )

    assert report["ready"] is False
    assert report["revision"] == "039"
    assert report["integrity"] is None
    assert "does not match repository head" in report["integrity_error"]


def test_preflight_rejects_integration_test_audit_fixtures(monkeypatch):
    expected_revision, = _repository_schema_heads()

    class FixtureDatabase:
        def execute(self, sql, params=None):
            if "SELECT version_num FROM alembic_version" in sql:
                return [(expected_revision,)]
            if "intelligence_integrity_status" in sql:
                return [{
                    "history_count": 1,
                    "accepted_count": 1,
                    "quarantined_count": 0,
                    "human_resolution_inference_count": 0,
                    "contradiction_count": 0,
                    "unresolved_contradiction_count": 0,
                    "resolved_contradiction_count": 0,
                    "oldest_unresolved_at": None,
                    "projection_count": 0,
                    "unlinked_projection_count": 0,
                    "projection_mismatch_count": 0,
                    "rejection_count": 0,
                    "rejections_last_24h": 0,
                    "latest_rejection_at": None,
                    "test_history_count": 1,
                    "test_rejection_count": 0,
                }]
            if "intelligence_validation_rejections" in sql and "produced" in sql:
                return [{"produced": 1, "rejected": 0}]
            if "SELECT EXISTS" in sql and "intelligence_inference_history" in sql:
                return [{"exists": True}]
            raise AssertionError(f"unexpected SQL: {sql}")

    monkeypatch.setattr(
        "scripts.verify_intelligence_preflight.estimate_backfill",
        lambda database, sample_size: {"read_only": True},
    )
    monkeypatch.setattr(
        "scripts.verify_intelligence_preflight.probe_llm_archive_destination",
        lambda: {"ok": True, "path": "/tmp/archive", "reason": "write probe passed"},
    )

    report = build_report(
        FixtureDatabase(),
        target_pass=0,
        sample_size=50,
        max_canary_items=25,
        receipt_path=None,
    )

    assert report["checks"]["integrity_clean"] is False
    assert report["integrity"]["test_history_count"] == 1


def test_gate_pass_rate_applies_only_after_twenty_outputs(monkeypatch):
    from scripts.verify_intelligence_preflight import _gate_pass_rate

    class Database:
        def __init__(self, produced, rejected):
            self.row = {"produced": produced, "rejected": rejected}

        def execute(self, sql, params=None):
            return [self.row]

    monkeypatch.delenv("COUNTYIQ_PASS2_MIN_GATE_PASS_RATE", raising=False)
    small = _gate_pass_rate(Database(10, 5), 2)
    assert small["ok"] is True and small["evaluated"] is False

    failing = _gate_pass_rate(Database(14, 6), 2)
    assert failing["evaluated"] is True and failing["pass_rate"] == 0.7 and failing["ok"] is False

    monkeypatch.setenv("COUNTYIQ_PASS2_MIN_GATE_PASS_RATE", "0.6")
    assert _gate_pass_rate(Database(14, 6), 2)["ok"] is True
