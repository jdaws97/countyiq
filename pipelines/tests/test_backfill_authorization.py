"""Regression coverage for cumulative backfill spend authorization."""

from pathlib import Path

import pytest

from countyiq.lib.backfill_authorization import (
    BackfillAuthorization,
    BackfillAuthorizationError,
    create_backfill_authorization,
)
from countyiq.lib.llm_harness import HarnessConfig, HarnessResult
from countyiq.lib.pass_llm_config import PassSpendBudget


def _create(path: Path, maximum: float = 0.10) -> BackfillAuthorization:
    create_backfill_authorization(
        path,
        pass_number=2,
        model="test/model",
        max_cost_usd=maximum,
        max_price_prompt=1.0,
        max_price_completion=2.0,
    )
    return BackfillAuthorization(
        path,
        pass_number=2,
        model="test/model",
        max_cost_usd=maximum,
        max_price_prompt=1.0,
        max_price_completion=2.0,
    )


def test_authorization_persists_spend_across_runtime_instances(tmp_path):
    path = tmp_path / "pass2-authorization.json"
    first = _create(path)
    reservation = first.reserve(0.06)
    first.settle(reservation, 0.04)

    restarted = _create_runtime(path)
    with pytest.raises(
        BackfillAuthorizationError, match="cumulative backfill authorization exhausted"
    ):
        restarted.reserve(0.061)

    snapshot = restarted.snapshot()
    assert snapshot["spent_usd"] == 0.04
    assert snapshot["remaining_usd"] == 0.06


def test_unsettled_crash_reservation_remains_committed(tmp_path):
    path = tmp_path / "pass2-authorization.json"
    authorization = _create(path)
    authorization.reserve(0.08)

    restarted = _create_runtime(path)
    with pytest.raises(BackfillAuthorizationError, match="exhausted"):
        restarted.reserve(0.03)
    assert restarted.snapshot()["reserved_usd"] == 0.08


def test_authorization_scope_mismatch_fails_closed(tmp_path):
    path = tmp_path / "pass2-authorization.json"
    _create(path)

    wrong_model = BackfillAuthorization(
        path,
        pass_number=2,
        model="other/model",
        max_cost_usd=0.10,
        max_price_prompt=1.0,
        max_price_completion=2.0,
    )
    with pytest.raises(BackfillAuthorizationError, match="model does not match"):
        wrong_model.snapshot()


def test_pass_budget_settles_provider_cost_in_durable_ledger(tmp_path):
    path = tmp_path / "pass2-authorization.json"
    authorization = _create(path, maximum=0.01)
    config = HarnessConfig(
        model_path="test/model",
        max_tokens=1_000,
        max_price_prompt=1.0,
        max_price_completion=2.0,
    )
    budget = PassSpendBudget(2, 0.01, authorization=authorization)

    reservation = budget.reserve(
        config, "prompt", retries=0, pdf_bytes=None
    )
    budget.record(
        HarnessResult("{}", {}, True, metadata={"cost": 0.001}),
        reservation,
    )

    snapshot = authorization.snapshot()
    assert snapshot["spent_usd"] == 0.001
    assert snapshot["reserved_usd"] == 0.0


def _create_runtime(path: Path) -> BackfillAuthorization:
    return BackfillAuthorization(
        path,
        pass_number=2,
        model="test/model",
        max_cost_usd=0.10,
        max_price_prompt=1.0,
        max_price_completion=2.0,
    )
