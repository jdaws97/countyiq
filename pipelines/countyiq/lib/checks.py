"""Shared asset_check builders for staging tables."""

from collections.abc import Callable
from typing import Any

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    MetadataValue,
    asset_check,
)

from countyiq.resources.database import DatabaseResource


def make_row_count_check(
    asset_def: Any,
    *,
    table: str,
    name: str | None = None,
    min_count: int = 1,
    threshold_fn: Callable[[], int] | None = None,
    severity: AssetCheckSeverity = AssetCheckSeverity.ERROR,
    metadata_key: str = "current_record_count",
    schema: str = "staging",
    count_expr: str = "*",
    description: str | None = None,
    include_threshold_metadata: bool = False,
) -> Any:
    """Build a row-count ``@asset_check`` for a staging table.

    The check runs ``SELECT COUNT(count_expr) FROM schema.table WHERE
    valid_to IS NULL`` and passes iff the count is at least ``min_count``
    (or ``threshold_fn()`` when provided — evaluated lazily so callers can
    reference ``get_county_config()`` without importing at module load).

    Args:
        asset_def: The asset definition to attach this check to.
        table: Staging table name (without schema).
        name: Override for the check name. Defaults to
            ``"{table}_record_count_nonzero"``.
        min_count: Static minimum row count (inclusive). Default 1 means
            "at least one row" (equivalent to the common ``count > 0``).
        threshold_fn: Zero-arg callable returning the minimum count at
            check-time. Overrides ``min_count``. Use when the threshold
            comes from ``get_county_config()``.
        severity: Check severity, ``ERROR`` by default.
        metadata_key: Key used for the count in the result metadata.
        schema: Postgres schema, ``"staging"`` by default.
        count_expr: Expression inside ``COUNT(...)``. Default ``"*"``.
            Use e.g. ``"DISTINCT pidn"`` for uniqueness checks.
        description: Override the check's docstring/description.
        include_threshold_metadata: Also emit ``"threshold"`` in the
            metadata (useful when the threshold is a dynamic county config
            value and surfacing it aids debugging).
    """
    check_name = name or f"{table}_record_count_nonzero"
    doc = description or f"Verify staging.{table} has at least one current record."
    sql = f"SELECT COUNT({count_expr}) FROM {schema}.{table} WHERE valid_to IS NULL"

    @asset_check(asset=asset_def, name=check_name, description=doc)
    def _check(database: DatabaseResource) -> AssetCheckResult:
        result = database.execute(sql)
        count = result[0][0] if result else 0
        threshold = threshold_fn() if threshold_fn else min_count
        metadata = {metadata_key: MetadataValue.int(count)}
        if include_threshold_metadata:
            metadata["threshold"] = MetadataValue.int(threshold)
        return AssetCheckResult(
            passed=count >= threshold,
            severity=severity,
            metadata=metadata,
        )

    return _check
