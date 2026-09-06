"""Fail-closed source-use policy checks for public API responses."""

from __future__ import annotations

from typing import Literal

from fastapi import HTTPException


SourceUse = Literal[
    "raw_retention",
    "derived_product",
    "raw_export",
]

_USE_COLUMNS: dict[SourceUse, str] = {
    "raw_retention": "raw_retention_allowed",
    "derived_product": "derived_product_allowed",
    "raw_export": "raw_export_allowed",
}


def source_use_allowed(cur, source_key: str, use: SourceUse) -> bool:
    """Return whether a current policy permits one response-layer use."""

    column = _USE_COLUMNS[use]
    cur.execute(
        f"""
        SELECT
            rights_status,
            {column} AS use_allowed,
            review_due_on >= CURRENT_DATE AS review_current
        FROM meta.source_rights
        WHERE source_key = %(source_key)s
        """,
        {"source_key": source_key},
    )
    row = cur.fetchone()
    return bool(
        row
        and row["rights_status"] != "paused"
        and row["use_allowed"]
        and row["review_current"]
    )


def require_source_use(
    cur,
    source_key: str,
    use: SourceUse,
    *,
    conceal: bool = True,
) -> None:
    """Block an API surface when its governed source use is not permitted."""

    if source_use_allowed(cur, source_key, use):
        return
    status_code = 404 if conceal else 503
    detail = (
        "This data view is unavailable under the current source-use policy."
        if conceal
        else f"Source policy does not permit {use.replace('_', ' ')}."
    )
    raise HTTPException(status_code=status_code, detail=detail)
