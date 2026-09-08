"""Fail-closed source authorization backed by ``meta.source_rights``.

Source reachability is not authorization. External ingestion assets call
``authorize_source`` before making a request; the helper validates the
reviewed policy and writes an immutable decision receipt for the Dagster run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Literal

from countyiq.lib.county_config import municipality_source_key
from countyiq.lib.robots import source_origin
from countyiq.resources.database import DatabaseResource


@dataclass(frozen=True)
class SourceAuthorization:
    source_key: str
    rights_status: str
    acquisition_method: str
    raw_retention_allowed: bool
    derived_product_allowed: bool
    raw_export_allowed: bool


@dataclass(frozen=True)
class MunicipalitySourceAuthorization:
    source_key: str
    body_name: str
    listing_url: str
    acquisition_method: str
    raw_retention_allowed: bool
    derived_product_allowed: bool
    raw_export_allowed: bool
    allowed_origins: frozenset[str]
    robots_unavailable_risk_accepted: bool
    browser_transport_reviewed: bool = False
    document_url_prefixes: tuple[str, ...] = ()


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


def _policy_receipt(snapshot: dict) -> tuple[str, str]:
    """Return canonical JSON plus a stable fingerprint for an audit decision."""

    payload = json.dumps(snapshot, default=str, sort_keys=True, separators=(",", ":"))
    return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_policy_snapshot(source_key: str, row: tuple) -> dict:
    return {
        "source_key": source_key,
        "rights_status": row[0],
        "acquisition_allowed": row[1],
        "raw_retention_allowed": row[2],
        "derived_product_allowed": row[3],
        "raw_export_allowed": row[4],
        "allowed_methods": list(row[5] or []),
        "reviewed_on": row[6],
        "review_due_on": row[7],
        "evidence": row[8] or {},
        "updated_at": row[9],
        "publisher": row[10],
        "source_url": row[11],
        "terms_url": row[12],
        "notes": row[13],
        "policy_version": row[14],
    }


def authorize_source(
    database: DatabaseResource,
    *,
    source_key: str,
    acquisition_method: str,
    asset_key: str,
    dagster_run_id: str | None = None,
) -> SourceAuthorization:
    """Authorize one acquisition attempt or raise before network access.

    Unknown, paused, disallowed-method, and overdue-review policies fail
    closed. Every decision for a known policy is appended to the audit table.
    """

    rows = database.execute(
        """
        SELECT
            rights_status,
            acquisition_allowed,
            raw_retention_allowed,
            derived_product_allowed,
            raw_export_allowed,
            allowed_methods,
            reviewed_on,
            review_due_on,
            evidence,
            updated_at,
            publisher,
            source_url,
            terms_url,
            notes,
            policy_version
        FROM meta.source_rights
        WHERE source_key = %s
        """,
        (source_key,),
    )
    if not rows:
        raise RuntimeError(
            f"Source {source_key!r} has no meta.source_rights policy; "
            "refusing external acquisition"
        )

    row = rows[0]
    (
        rights_status,
        acquisition_allowed,
        raw_retention_allowed,
        derived_product_allowed,
        raw_export_allowed,
        allowed_methods,
        _reviewed_on,
        review_due_on,
        _evidence,
        _updated_at,
        _publisher,
        _source_url,
        _terms_url,
        _notes,
        policy_version,
    ) = row
    snapshot = _source_policy_snapshot(source_key, row)
    snapshot_json, policy_fingerprint = _policy_receipt(snapshot)

    reason = "authorized"
    allowed = True
    if rights_status == "paused":
        allowed = False
        reason = "source policy is paused"
    elif not acquisition_allowed:
        allowed = False
        reason = "acquisition is disabled by source policy"
    elif acquisition_method not in set(allowed_methods or []):
        allowed = False
        reason = f"method {acquisition_method!r} is not allowlisted"
    elif review_due_on < date.today():
        allowed = False
        reason = f"source review expired on {review_due_on.isoformat()}"

    database.execute(
        """
        INSERT INTO meta.source_rights_audit (
            source_key, asset_key, dagster_run_id, acquisition_method,
            allowed, reason, policy_version, policy_fingerprint, policy_snapshot
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            source_key,
            asset_key,
            dagster_run_id,
            acquisition_method,
            allowed,
            reason,
            policy_version,
            policy_fingerprint,
            snapshot_json,
        ),
    )

    if not allowed:
        raise RuntimeError(f"Source {source_key!r} blocked: {reason}")

    return SourceAuthorization(
        source_key=source_key,
        rights_status=rights_status,
        acquisition_method=acquisition_method,
        raw_retention_allowed=raw_retention_allowed,
        derived_product_allowed=derived_product_allowed,
        raw_export_allowed=raw_export_allowed,
    )


def require_source_use(
    authorization: SourceAuthorization | MunicipalitySourceAuthorization,
    use: SourceUse,
) -> None:
    """Fail closed before retaining or publishing source-derived material.

    Acquisition authorization is intentionally separate from downstream-use
    authorization: a source can be collectable while raw retention or export
    remains prohibited.
    """

    field = f"{use}_allowed"
    if not getattr(authorization, field):
        raise RuntimeError(
            f"Source {authorization.source_key!r} blocks {use.replace('_', ' ')}"
        )


def authorize_source_use(
    database: DatabaseResource,
    *,
    source_key: str,
    use: SourceUse,
    asset_key: str,
    dagster_run_id: str | None = None,
) -> None:
    """Authorize a current downstream use without manufacturing an acquisition.

    Score rebuilds can be launched independently of their source assets and may
    otherwise reuse rows after a source is paused or its review expires. This
    check consults the current policy at the point of derivation. The existing
    append-only audit ledger records ``use:<type>`` in its legacy
    ``acquisition_method`` column so downstream decisions remain attributable.
    """

    rows = database.execute(
        """
        SELECT
            rights_status, acquisition_allowed,
            raw_retention_allowed, derived_product_allowed, raw_export_allowed,
            allowed_methods, reviewed_on, review_due_on, evidence,
            updated_at, publisher, source_url, terms_url, notes, policy_version
        FROM meta.source_rights
        WHERE source_key = %s
        """,
        (source_key,),
    )
    if not rows:
        raise RuntimeError(
            f"Source {source_key!r} has no meta.source_rights policy; "
            f"refusing {use.replace('_', ' ')}"
        )

    row = rows[0]
    rights_status = row[0]
    use_allowed = row[{"raw_retention": 2, "derived_product": 3, "raw_export": 4}[use]]
    review_due_on = row[7]
    snapshot = _source_policy_snapshot(source_key, row)
    snapshot_json, policy_fingerprint = _policy_receipt(snapshot)
    allowed = True
    reason = "authorized"
    if rights_status == "paused":
        allowed = False
        reason = "source policy is paused"
    elif not use_allowed:
        allowed = False
        reason = f"source policy blocks {use.replace('_', ' ')}"
    elif review_due_on < date.today():
        allowed = False
        reason = f"source review expired on {review_due_on.isoformat()}"

    database.execute(
        """
        INSERT INTO meta.source_rights_audit (
            source_key, asset_key, dagster_run_id, acquisition_method,
            allowed, reason, policy_version, policy_fingerprint, policy_snapshot
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            source_key,
            asset_key,
            dagster_run_id,
            f"use:{use}",
            allowed,
            reason,
            row[14],
            policy_fingerprint,
            snapshot_json,
        ),
    )
    if not allowed:
        raise RuntimeError(f"Source {source_key!r} blocked: {reason}")


def authorize_source_uses(
    database: DatabaseResource,
    *,
    source_keys: tuple[str, ...],
    use: SourceUse,
    asset_key: str,
    dagster_run_id: str | None = None,
) -> None:
    """Authorize the same downstream use for an exact set of dependencies."""

    for source_key in source_keys:
        authorize_source_use(
            database,
            source_key=source_key,
            use=use,
            asset_key=asset_key,
            dagster_run_id=dagster_run_id,
        )


def source_use_is_authorized(
    database: DatabaseResource,
    *,
    source_key: str,
    use: SourceUse,
    asset_key: str,
    dagster_run_id: str | None = None,
) -> bool:
    """Audit an optional capability and return False instead of blocking peers.

    This is for deliberately segmented products only: for example an expired
    tax-claim policy may disable opportunity/distress signals without taking
    deterministic site screening offline.
    """

    try:
        authorize_source_use(
            database,
            source_key=source_key,
            use=use,
            asset_key=asset_key,
            dagster_run_id=dagster_run_id,
        )
    except RuntimeError:
        return False
    return True


def authorize_municipality_sources(
    database: DatabaseResource,
    *,
    entries: tuple[tuple[str, str, str], ...],
    acquisition_method: str,
    asset_key: str,
    dagster_run_id: str | None = None,
) -> dict[str, MunicipalitySourceAuthorization]:
    """Authorize every configured municipal body before any network access.

    The reviewed database policy must match the configured body, URL, and
    proceeding type.  New or edited configuration therefore fails closed
    until a corresponding policy review is recorded by migration.
    """

    source_keys = [municipality_source_key(body_name) for body_name, _, _ in entries]
    rows = database.execute(
        """
        SELECT
            source_key, body_name, listing_url, proceeding_type,
            rights_status, acquisition_allowed, raw_retention_allowed,
            derived_product_allowed, raw_export_allowed,
            allowed_methods, allowed_origins,
            terms_review_status,
            review_due_on, reviewed_on, evidence, updated_at, notes,
            policy_version, terms_url
        FROM meta.municipality_source_rights
        WHERE source_key = ANY(%s)
        """,
        (source_keys,),
    )
    policies = {row[0]: row for row in rows or []}
    missing = sorted(set(source_keys) - policies.keys())
    if missing:
        raise RuntimeError(
            "Municipality sources have no reviewed policy: " + ", ".join(missing)
        )

    authorizations: dict[str, MunicipalitySourceAuthorization] = {}
    for body_name, listing_url, proceeding_type in entries:
        source_key = municipality_source_key(body_name)
        row = policies[source_key]
        (
            _,
            policy_body,
            policy_url,
            policy_type,
            rights_status,
            acquisition_allowed,
            raw_retention_allowed,
            derived_product_allowed,
            raw_export_allowed,
            allowed_methods,
            allowed_origins,
            terms_review_status,
            review_due_on,
            reviewed_on,
            evidence,
            updated_at,
            notes,
            policy_version,
            terms_url,
        ) = row

        policy_snapshot = {
            "source_key": source_key,
            "body_name": policy_body,
            "listing_url": policy_url,
            "proceeding_type": policy_type,
            "rights_status": rights_status,
            "acquisition_allowed": acquisition_allowed,
            "raw_retention_allowed": raw_retention_allowed,
            "derived_product_allowed": derived_product_allowed,
            "raw_export_allowed": raw_export_allowed,
            "allowed_methods": list(allowed_methods or []),
            "allowed_origins": list(allowed_origins or []),
            "terms_review_status": terms_review_status,
            "terms_url": terms_url,
            "reviewed_on": reviewed_on,
            "review_due_on": review_due_on,
            "evidence": evidence or {},
            "notes": notes,
            "updated_at": updated_at,
            "policy_version": policy_version,
        }
        snapshot_json, policy_fingerprint = _policy_receipt(policy_snapshot)

        allowed = True
        reason = "authorized"
        if (policy_body, policy_url, policy_type) != (
            body_name,
            listing_url,
            proceeding_type,
        ):
            allowed = False
            reason = "configured source does not match reviewed policy"
        elif rights_status == "paused":
            allowed = False
            reason = "municipality source policy is paused"
        elif not acquisition_allowed:
            allowed = False
            reason = "acquisition is disabled by municipality source policy"
        elif terms_review_status in {"restricted", "no_web_presence"}:
            allowed = False
            reason = f"terms review status is {terms_review_status}"
        elif source_origin(listing_url) not in set(allowed_origins or []):
            allowed = False
            reason = "reviewed listing origin is not allowlisted"
        elif acquisition_method not in set(allowed_methods or []):
            allowed = False
            reason = f"method {acquisition_method!r} is not allowlisted"
        elif review_due_on < date.today():
            allowed = False
            reason = (
                f"municipality source review expired on {review_due_on.isoformat()}"
            )

        database.execute(
            """
            INSERT INTO meta.municipality_source_audit (
                source_key, asset_key, dagster_run_id, acquisition_method,
                allowed, reason, policy_version, policy_fingerprint,
                policy_snapshot
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                source_key,
                asset_key,
                dagster_run_id,
                acquisition_method,
                allowed,
                reason,
                policy_version,
                policy_fingerprint,
                snapshot_json,
            ),
        )
        if not allowed:
            raise RuntimeError(f"Municipality source {source_key!r} blocked: {reason}")

        authorization = MunicipalitySourceAuthorization(
            source_key=source_key,
            body_name=body_name,
            listing_url=listing_url,
            acquisition_method=acquisition_method,
            raw_retention_allowed=raw_retention_allowed,
            derived_product_allowed=derived_product_allowed,
            raw_export_allowed=raw_export_allowed,
            allowed_origins=frozenset(allowed_origins or []),
            robots_unavailable_risk_accepted=bool(
                (evidence or {}).get("robots_unavailable_risk_accepted", False)
            ),
            browser_transport_reviewed=bool(
                (evidence or {}).get("browser_transport_reviewed", False)
            ),
            document_url_prefixes=(str(evidence["document_path_prefix"]),)
            if (evidence or {}).get("document_path_prefix")
            else (),
        )
        require_source_use(authorization, "derived_product")
        authorizations[source_key] = authorization

    return authorizations


def record_municipality_source_health(
    database: DatabaseResource,
    *,
    source_key: str,
    listing_status: str,
    robots_allowed: bool | None,
    robots_reason: str | None,
    http_status: int | None,
    document_count: int,
    last_error: str | None = None,
) -> None:
    """Persist the latest observable health for one municipal body source."""

    database.execute(
        """
        INSERT INTO meta.municipality_source_health (
            source_key, listing_status, robots_allowed, robots_reason,
            http_status, document_count, checked_at, last_success_at,
            last_error
        ) VALUES (
            %s, %s, %s, %s, %s, %s, NOW(),
            CASE WHEN %s IN ('ok', 'not_modified') THEN NOW() ELSE NULL END,
            %s
        )
        ON CONFLICT (source_key) DO UPDATE SET
            listing_status = EXCLUDED.listing_status,
            robots_allowed = EXCLUDED.robots_allowed,
            robots_reason = EXCLUDED.robots_reason,
            http_status = EXCLUDED.http_status,
            document_count = CASE
                WHEN EXCLUDED.listing_status = 'not_modified'
                    THEN meta.municipality_source_health.document_count
                ELSE EXCLUDED.document_count
            END,
            checked_at = NOW(),
            last_success_at = CASE
                WHEN EXCLUDED.listing_status IN ('ok', 'not_modified')
                    THEN NOW()
                ELSE meta.municipality_source_health.last_success_at
            END,
            last_error = EXCLUDED.last_error
        """,
        (
            source_key,
            listing_status,
            robots_allowed,
            robots_reason,
            http_status,
            document_count,
            listing_status,
            last_error,
        ),
    )
