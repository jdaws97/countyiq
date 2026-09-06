"""Tests for lib.checks.make_row_count_check."""

from unittest.mock import MagicMock

import pytest
from dagster import AssetCheckSeverity, asset

from countyiq.lib.checks import make_row_count_check


@asset
def dummy_asset() -> str:
    return "ok"


def _result_for(check, count: int):
    """Invoke the builder's check against a mock database returning `count`."""
    db = MagicMock()
    db.execute.return_value = [(count,)]
    return check(database=db), db


def test_default_passes_when_count_at_or_above_one():
    check = make_row_count_check(dummy_asset, table="widgets")
    result, db = _result_for(check, 1)
    assert result.passed is True
    assert result.severity == AssetCheckSeverity.ERROR
    assert result.metadata["current_record_count"].value == 1
    db.execute.assert_called_once_with(
        "SELECT COUNT(*) FROM staging.widgets WHERE valid_to IS NULL"
    )


def test_default_fails_when_count_zero():
    check = make_row_count_check(dummy_asset, table="widgets")
    result, _ = _result_for(check, 0)
    assert result.passed is False


def test_min_count_override():
    check = make_row_count_check(dummy_asset, table="widgets", min_count=11)
    passing, _ = _result_for(check, 11)
    failing, _ = _result_for(check, 10)
    assert passing.passed is True
    assert failing.passed is False


def test_threshold_fn_overrides_min_count():
    calls = {"n": 0}

    def threshold() -> int:
        calls["n"] += 1
        return 500

    check = make_row_count_check(
        dummy_asset, table="widgets", min_count=1, threshold_fn=threshold
    )
    passing, _ = _result_for(check, 500)
    failing, _ = _result_for(check, 499)
    assert passing.passed is True
    assert failing.passed is False
    assert calls["n"] == 2


def test_custom_count_expr_builds_distinct_sql():
    check = make_row_count_check(
        dummy_asset, table="widgets", count_expr="DISTINCT pidn"
    )
    _, db = _result_for(check, 5)
    db.execute.assert_called_once_with(
        "SELECT COUNT(DISTINCT pidn) FROM staging.widgets WHERE valid_to IS NULL"
    )


def test_metadata_key_rename():
    check = make_row_count_check(dummy_asset, table="widgets", metadata_key="my_count")
    result, _ = _result_for(check, 3)
    assert "my_count" in result.metadata
    assert "current_record_count" not in result.metadata


def test_include_threshold_metadata():
    check = make_row_count_check(
        dummy_asset,
        table="widgets",
        threshold_fn=lambda: 42,
        include_threshold_metadata=True,
    )
    result, _ = _result_for(check, 100)
    assert result.metadata["threshold"].value == 42


def test_severity_override():
    check = make_row_count_check(
        dummy_asset, table="widgets", severity=AssetCheckSeverity.WARN
    )
    result, _ = _result_for(check, 0)
    assert result.severity == AssetCheckSeverity.WARN


def test_name_and_description_override():
    check = make_row_count_check(
        dummy_asset,
        table="widgets",
        name="custom_check_name",
        description="Custom docstring.",
    )
    # Dagster stores specs on the check definition
    [spec] = check.check_specs
    assert spec.name == "custom_check_name"
    assert "Custom docstring." in (spec.description or "")


@pytest.mark.parametrize("schema", ["staging", "meta", "public"])
def test_schema_override(schema):
    check = make_row_count_check(dummy_asset, table="widgets", schema=schema)
    _, db = _result_for(check, 1)
    assert f"FROM {schema}.widgets" in db.execute.call_args[0][0]
