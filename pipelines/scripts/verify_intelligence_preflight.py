"""Fail-closed, no-provider preflight for one CountyIQ LLM canary pass.

The command never calls a model and never writes the database. It does create
and remove one small archive probe. Run it from the same environment that will
launch the selected Dagster pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from countyiq.lib.backfill_authorization import (
    BackfillAuthorization,
    BackfillAuthorizationError,
)
from countyiq.lib.backfill_estimator import estimate_backfill
from countyiq.lib.llm_harness import probe_llm_archive_destination
from countyiq.lib.pass_llm_config import (
    resolve_pass_enabled,
    resolve_pass_item_limit,
    resolve_pass_model,
)
from countyiq.resources.database import make_database_resource

REPO_ROOT = Path(__file__).resolve().parents[2]
PASS2_REVIEW_FIXTURE = REPO_ROOT / "pipelines/eval/fixtures/p2_expanded_stability20.json"


def _repository_schema_heads() -> tuple[str, ...]:
    """Return the Alembic heads declared by the checked-out repository."""
    config = Config(str(REPO_ROOT / "pipelines/alembic.ini"))
    config.set_main_option(
        "script_location", str(REPO_ROOT / "pipelines/alembic")
    )
    return tuple(sorted(ScriptDirectory.from_config(config).get_heads()))


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _positive_float(name: str) -> float | None:
    try:
        value = float(os.environ.get(name, ""))
    except ValueError:
        return None
    return value if value > 0 else None


def _backfill_authorization_check(
    *,
    target_pass: int,
    backfill_mode: bool,
    max_cost_usd: float | None,
    max_price_prompt: float | None,
    max_price_completion: float | None,
) -> dict:
    path_value = os.environ.get(
        f"COUNTYIQ_PASS{target_pass}_BACKFILL_AUTHORIZATION_FILE", ""
    ).strip()
    if not path_value:
        mode = "backfill" if backfill_mode else "canary"
        return {
            "ok": False,
            "reason": (
                f"COUNTYIQ_PASS{target_pass}_BACKFILL_AUTHORIZATION_FILE "
                f"is required for a restart-safe {mode}"
            ),
        }
    try:
        authorization = BackfillAuthorization(
            Path(path_value),
            pass_number=target_pass,
            model=resolve_pass_model(target_pass) or "",
            max_cost_usd=max_cost_usd,
            max_price_prompt=max_price_prompt,
            max_price_completion=max_price_completion,
        )
        snapshot = authorization.snapshot()
    except BackfillAuthorizationError as exc:
        return {"ok": False, "path": path_value, "reason": str(exc)}
    return {
        "ok": True,
        "path": path_value,
        "authorization_id": snapshot["authorization_id"],
        "spent_usd": snapshot["spent_usd"],
        "reserved_usd": snapshot["reserved_usd"],
        "remaining_usd": snapshot["remaining_usd"],
        "reason": "runtime scope matches durable cumulative authorization",
    }


def _pass2_review_check(receipt_path: Path | None) -> dict:
    expected = json.loads(PASS2_REVIEW_FIXTURE.read_text(encoding="utf-8"))
    expected_ids = {case["id"] for case in expected["cases"]}
    fixture_sha256 = hashlib.sha256(PASS2_REVIEW_FIXTURE.read_bytes()).hexdigest()
    if receipt_path is None or not receipt_path.exists():
        return {
            "ok": False,
            "reason": "Pass 2 requires --human-review-receipt",
            "fixture_sha256": fixture_sha256,
            "expected_case_count": len(expected_ids),
        }
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    decisions = receipt.get("case_decisions") or {}
    approved_ids = {
        case_id for case_id, decision in decisions.items() if decision == "approved"
    }
    ok = bool(
        receipt.get("reviewer")
        and receipt.get("reviewed_at")
        and receipt.get("fixture_sha256") == fixture_sha256
        and approved_ids == expected_ids
    )
    return {
        "ok": ok,
        "reason": (
            "all stability cases approved"
            if ok
            else "receipt, fixture hash, reviewer, date, or case approvals are incomplete"
        ),
        "fixture_sha256": fixture_sha256,
        "expected_case_count": len(expected_ids),
        "approved_case_count": len(approved_ids & expected_ids),
    }


_GATE_RATE_MIN_OBSERVATIONS = 20


def _gate_pass_rate(database, pass_number: int, *, days: int = 30) -> dict:
    """Deterministic-gate pass rate: accepted history / (history + rejections).

    Every model output either enters the inference history (it passed the
    quote/citation/membership gates) or the rejection ledger (it did not).
    The ratio is the live measure that the runbook used to approximate with a
    one-off 20-case human receipt.
    """

    rows = database.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM meta.intelligence_inference_history
              WHERE pass_number = %(pass_number)s AND decision_origin = 'model'
                AND created_at >= NOW() - MAKE_INTERVAL(days => %(days)s)) AS produced,
            (SELECT COUNT(*) FROM meta.intelligence_validation_rejections
              WHERE pass_number = %(pass_number)s
                AND rejected_at >= NOW() - MAKE_INTERVAL(days => %(days)s)) AS rejected
        """,
        {"pass_number": pass_number, "days": days},
    ) or []
    row = rows[0] if rows else (0, 0)
    produced = int(row["produced"] if isinstance(row, dict) else row[0]) or 0
    rejected = int(row["rejected"] if isinstance(row, dict) else row[1]) or 0
    observations = produced + rejected
    threshold = _positive_float(f"COUNTYIQ_PASS{pass_number}_MIN_GATE_PASS_RATE") or 0.8
    rate = produced / observations if observations else None
    evaluated = observations >= _GATE_RATE_MIN_OBSERVATIONS
    return {
        "ok": (not evaluated) or (rate is not None and rate >= threshold),
        "evaluated": evaluated,
        "window_days": days,
        "produced": produced,
        "rejected": rejected,
        "pass_rate": None if rate is None else round(rate, 4),
        "minimum_pass_rate": threshold,
        "reason": (
            f"gate pass rate {rate:.1%} over {observations} outputs"
            if evaluated
            else f"{observations} outputs in window; needs {_GATE_RATE_MIN_OBSERVATIONS} before the rate applies"
        ),
    }


def _pass_has_accepted_history(database, pass_number: int) -> bool:
    rows = database.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM meta.intelligence_inference_history
            WHERE pass_number = %s AND disposition = 'accepted' AND decision_origin = 'model'
        )
        """,
        (pass_number,),
    ) or []
    row = rows[0] if rows else None
    if row is None:
        return False
    return bool(row["exists"] if isinstance(row, dict) else row[0])


def build_report(
    database,
    *,
    target_pass: int,
    sample_size: int,
    max_canary_items: int,
    receipt_path: Path | None,
) -> dict:
    repository_heads = _repository_schema_heads()
    expected_revision = repository_heads[0] if len(repository_heads) == 1 else None
    revision_rows = database.execute("SELECT version_num FROM alembic_version") or []
    database_revisions = sorted(row[0] for row in revision_rows)
    revision = database_revisions[0] if len(database_revisions) == 1 else None
    integrity_rows = []
    integrity_error = None
    if expected_revision is not None and revision == expected_revision:
        integrity_rows = database.execute(
            """
            SELECT integrity.*, rejection.rejection_count,
                   rejection.rejections_last_24h,
                   rejection.latest_rejection_at,
                   fixtures.test_history_count,
                   fixtures.test_rejection_count
            FROM meta.intelligence_integrity_status AS integrity
            CROSS JOIN meta.intelligence_validation_rejection_status AS rejection
            CROSS JOIN LATERAL (
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM meta.intelligence_inference_history
                        WHERE requested_model LIKE 'test/%'
                          AND prompt_version = 'test-prompt'
                    ) AS test_history_count,
                    (
                        SELECT COUNT(*)
                        FROM meta.intelligence_validation_rejections
                        WHERE subject_key LIKE 'rejection-test:%'
                          AND requested_model LIKE 'test/%'
                    ) AS test_rejection_count
            ) AS fixtures
            """
        ) or []
    else:
        if expected_revision is None:
            integrity_error = (
                "repository must have exactly one Alembic head; found "
                f"{list(repository_heads)}; integrity views were not queried"
            )
        else:
            integrity_error = (
                f"schema revision {revision or database_revisions or 'base'} does not match repository "
                f"head {expected_revision}; integrity views were not queried"
            )
    gate_rate = None
    first_run = True
    if expected_revision is not None and revision == expected_revision:
        gate_rate = _gate_pass_rate(database, target_pass)
        first_run = not _pass_has_accepted_history(database, target_pass)
    integrity = dict(integrity_rows[0]) if integrity_rows and isinstance(integrity_rows[0], dict) else None
    if integrity is None and integrity_rows:
        keys = (
            "history_count", "accepted_count", "quarantined_count",
            "human_resolution_inference_count", "contradiction_count",
            "unresolved_contradiction_count", "resolved_contradiction_count",
            "oldest_unresolved_at", "projection_count",
            "unlinked_projection_count", "projection_mismatch_count",
            "rejection_count", "rejections_last_24h", "latest_rejection_at",
            "test_history_count", "test_rejection_count",
        )
        integrity = dict(zip(keys, integrity_rows[0], strict=True))

    enabled = [number for number in range(5) if resolve_pass_enabled(number)]
    item_limit = resolve_pass_item_limit(target_pass)
    backfill_mode = _truthy(f"COUNTYIQ_PASS{target_pass}_BACKFILL_MODE")
    archive_probe = probe_llm_archive_destination()
    max_cost_usd = _positive_float(
        f"COUNTYIQ_PASS{target_pass}_MAX_COST_USD"
    )
    max_price_prompt = _positive_float("COUNTYIQ_MAX_PRICE_PROMPT")
    max_price_completion = _positive_float("COUNTYIQ_MAX_PRICE_COMPLETION")
    authorization = _backfill_authorization_check(
        target_pass=target_pass,
        backfill_mode=backfill_mode,
        max_cost_usd=max_cost_usd,
        max_price_prompt=max_price_prompt,
        max_price_completion=max_price_completion,
    )
    controls = {
        "only_target_pass_enabled": enabled == [target_pass],
        "enabled_passes": enabled,
        # A canary is bounded by items; an approved backfill is bounded only by
        # its dollar ceiling, which resolve_pass_item_limit already required.
        "item_limit_within_canary_cap": (
            (item_limit is None and backfill_mode)
            or (item_limit is not None and item_limit <= max_canary_items)
        ),
        "backfill_mode": backfill_mode,
        "item_limit": item_limit,
        "max_cost_usd": max_cost_usd,
        "max_price_prompt": max_price_prompt,
        "max_price_completion": max_price_completion,
        "cumulative_authorization": authorization,
        "archive_strict": _truthy("COUNTYIQ_ARCHIVE_STRICT"),
        "archive_probe": archive_probe,
        "openrouter_key_configured": bool(os.environ.get("OPENROUTER_API_KEY", "").strip()),
    }
    controls_ok = bool(
        controls["only_target_pass_enabled"]
        and controls["item_limit_within_canary_cap"]
        and controls["max_cost_usd"]
        and controls["max_price_prompt"]
        and controls["max_price_completion"]
        and authorization["ok"]
        and controls["archive_strict"]
        and archive_probe["ok"]
        and controls["openrouter_key_configured"]
    )
    integrity_ok = bool(
        integrity is not None
        and int(integrity["unresolved_contradiction_count"] or 0) == 0
        and int(integrity["unlinked_projection_count"] or 0) == 0
        and int(integrity["projection_mismatch_count"] or 0) == 0
        and int(integrity["rejections_last_24h"] or 0) == 0
        and int(integrity["test_history_count"] or 0) == 0
        and int(integrity["test_rejection_count"] or 0) == 0
    )
    if target_pass == 2 and first_run:
        review = _pass2_review_check(receipt_path)
    elif target_pass == 2:
        review = {
            "ok": True,
            "reason": (
                "Pass 2 already has accepted runs; the one-time label receipt is "
                "replaced by the gate pass-rate check"
            ),
        }
    else:
        review = {
            "ok": True,
            "reason": "no additional expanded-label receipt required for this pass",
        }
    from countyiq.lib.quality_release import check_quality_release
    quality_release = check_quality_release(target_pass)
    gate_rate_ok = gate_rate is None or bool(gate_rate["ok"])
    estimate_error = None
    try:
        estimate = estimate_backfill(database, sample_size=sample_size)
    except RuntimeError as exc:
        estimate = None
        estimate_error = str(exc)
    estimate_ok = estimate is not None
    return {
        "read_only": True,
        "target_pass": target_pass,
        "ready": (
            expected_revision is not None
            and revision == expected_revision
            and integrity_ok
            and controls_ok
            and review["ok"]
            and gate_rate_ok
            and estimate_ok
            and quality_release["ok"]
        ),
        "checks": {
            "schema_at_repository_head": (
                expected_revision is not None and revision == expected_revision
            ),
            "integrity_clean": integrity_ok,
            "runtime_controls": controls_ok,
            "human_review": review["ok"],
            "gate_pass_rate": gate_rate_ok,
            "estimate_available": estimate_ok,
            "quality_release": quality_release["ok"],
        },
        "quality_release": quality_release,
        "first_run_for_pass": first_run,
        "gate_pass_rate": gate_rate,
        "revision": revision,
        "repository_heads": list(repository_heads),
        "database_revisions": database_revisions,
        "integrity": integrity,
        "integrity_error": integrity_error,
        "runtime_controls": controls,
        "human_review": review,
        "estimate": estimate,
        "estimate_error": estimate_error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-pass", type=int, choices=range(4), required=True)
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--max-canary-items", type=int, default=25)
    parser.add_argument("--human-review-receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.sample_size < 1 or args.max_canary_items < 1:
        parser.error("sample size and canary item cap must be positive")

    database = make_database_resource()
    database.setup_for_execution(None)
    try:
        database.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        report = build_report(
            database,
            target_pass=args.target_pass,
            sample_size=args.sample_size,
            max_canary_items=args.max_canary_items,
            receipt_path=args.human_review_receipt,
        )
    finally:
        database.teardown_after_execution(None)

    serialized = json.dumps(report, indent=2, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
