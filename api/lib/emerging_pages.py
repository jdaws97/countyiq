"""Filter indexed candidates, then verify only this page's evidence scopes."""

import base64
import binascii
import json
import re
from datetime import datetime
from hashlib import sha256

from api.lib.emerging_intelligence import MARKER, present_cases

CASE_KEY = re.compile(r"emerging-[0-9a-f]{64}\Z")
COVERAGE_NOTE = (
    "These cases reflect selected public records. Open a case to review its evidence "
    "and remaining uncertainties. Unassessed places may still contain opportunities; "
    "an empty result does not establish inactivity."
)
MISSING_SOURCE_FAMILIES = [
    "Project-specific utility capacity and service commitments",
    "Complete permit and construction-start histories",
    "Current procurement, financing and contractor commitments",
]


def filter_fingerprint(filters: dict) -> str:
    return sha256(json.dumps(filters, sort_keys=True).encode()).hexdigest()


def encode_cursor(row: dict, fingerprint: str) -> str:
    payload = {
        "version": 1,
        "created_at": row["created_at"].isoformat(),
        "case_key": row["case_key"],
        "filters": fingerprint,
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def decode_cursor(value: str | None, fingerprint: str) -> tuple | None:
    if value is None:
        return None
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
        payload = json.loads(decoded)
        if not isinstance(payload, dict) or set(payload) != {
            "version",
            "created_at",
            "case_key",
            "filters",
        }:
            raise ValueError("Invalid page cursor")
        stamp = datetime.fromisoformat(payload["created_at"])
        if (
            type(payload["version"]) is not int
            or payload["version"] != 1
            or payload["filters"] != fingerprint
            or stamp.utcoffset() is None
            or not CASE_KEY.fullmatch(payload["case_key"])
        ):
            raise ValueError("Invalid page cursor")
        return stamp, payload["case_key"]
    except (ValueError, TypeError, KeyError, binascii.Error, UnicodeError) as error:
        raise ValueError("Invalid page cursor; return to the first page.") from error


def candidate_query(filters: dict, after: tuple | None, limit: int) -> tuple:
    clauses = ["candidate.published"]
    values = []
    for key, column in (
        ("family", "family"),
        ("case_key", "case_key"),
    ):
        if filters[key]:
            clauses.append(f"candidate.{column} = ANY(%s)")
            values.append(filters[key])
    for key, column in (
        ("municipality", "municipalities"),
        ("project_type", "project_types"),
    ):
        if filters[key]:
            clauses.append(f"candidate.{column} && %s::text[]")
            values.append(filters[key])
    if filters["exclude_case_key"]:
        clauses.append("NOT candidate.case_key = ANY(%s)")
        values.append(filters["exclude_case_key"])
    if filters["pidn"]:
        clauses.append("candidate.pidns @> ARRAY[%s]::text[]")
        values.append(filters["pidn"])
    if filters["q"]:
        literal = (
            filters["q"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        clauses.append("candidate.search_text LIKE %s")
        values.append("%" + literal + "%")
    if filters["opportunities_only"]:
        clauses.append("candidate.has_opportunities")
    # Indexed unions narrow candidates; the correlated check below still requires
    # all selected criteria to match the same commercial possibility.
    if filters["audience"]:
        clauses.append("candidate.audiences @> ARRAY[%s]::text[]")
        values.append(filters["audience"])
    for key, column in (("service", "services"), ("readiness", "readiness")):
        if filters[key]:
            clauses.append(f"candidate.{column} && %s::text[]")
            values.append(filters[key])
    possibility_filters = []
    if filters["audience"]:
        possibility_filters.append("possibility->>'audience' = %s")
        values.append(filters["audience"])
    if filters["service"]:
        possibility_filters.append("possibility->'services' ?| %s::text[]")
        values.append(filters["service"])
    if filters["readiness"]:
        possibility_filters.append("possibility->>'readiness' = ANY(%s)")
        values.append(filters["readiness"])
    if possibility_filters:
        possibilities = "candidate.summary->'opportunities'"
        if not filters["opportunities_only"]:
            possibilities = (
                "(candidate.summary->'opportunities') || "
                "(candidate.summary->'implications')"
            )
        clauses.append(
            f"EXISTS (SELECT 1 FROM jsonb_array_elements({possibilities}) possibility "
            f"WHERE {' AND '.join(possibility_filters)})"
        )
    if after:
        stamp, key = after
        clauses.append(
            "(candidate.created_at < %s OR "
            "(candidate.created_at = %s AND candidate.case_key > %s))"
        )
        values.extend((stamp, stamp, key))
    values.append(limit + 1)
    query = f"""
        SELECT candidate.case_key, candidate.inference_id, candidate.created_at,
            candidate.summary
        FROM public.emerging_case_index candidate
        WHERE {" AND ".join(clauses)}
        ORDER BY candidate.created_at DESC, candidate.case_key
        LIMIT %s
    """
    return query, values


def current_inference_ids(cur, inference_ids: list[int]) -> set[int]:
    """Canonical equality remains authoritative; the candidate index grants nothing."""
    if not inference_ids:
        return set()
    if len(inference_ids) > 100:
        raise ValueError("A request may check at most one hundred evidence scopes")
    cur.execute(
        """
        WITH selected AS MATERIALIZED (
            SELECT inference_id, payload->'packet'->'source' AS source
            FROM meta.intelligence_inference_history
            WHERE inference_id = ANY(%s::bigint[])
                AND output_kind = 'emerging_analysis' AND disposition = 'accepted'
        ), scoped AS MATERIALIZED (
            SELECT array_agg(input) AS rows
            FROM public.current_municipal_matter_scoped_inputs input
            WHERE EXISTS (SELECT 1 FROM selected)
        )
        SELECT selected.inference_id
        FROM selected CROSS JOIN scoped
        WHERE selected.source = public.emerging_scope_source_from_inputs(
            selected.source->>'seed_bundle',
            selected.source->'settings'->>'open_data_key',
            (selected.source->'settings'->>'planning_radius_m')::integer,
            (selected.source->'settings'->>'environmental_radius_m')::integer,
            (selected.source->'settings'->>'neighbor_limit')::integer,
            scoped.rows
        )
        """,
        (inference_ids,),
    )
    return {row["inference_id"] for row in cur.fetchall()}


def _plain_text(value):
    if isinstance(value, str):
        return MARKER.sub("", value).strip()
    if isinstance(value, list):
        return [_plain_text(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain_text(item) for key, item in value.items()}
    return value


def present_summary(row: dict) -> dict:
    summary = _plain_text(row["summary"])
    summary.update(case_key=row["case_key"], revision=str(row["inference_id"]))
    for name in ("opportunities", "implications"):
        for possibility in summary[name]:
            identity = possibility["audience"] + "|" + possibility["title"].casefold()
            possibility["opportunity_key"] = (
                row["case_key"] + ":" + sha256(identity.encode()).hexdigest()[:16]
            )
    return summary


def load_page(cur, filters: dict, limit: int, cursor: str | None) -> dict:
    if not 1 <= limit <= 100:
        raise ValueError("Page size must be between one and one hundred")
    fingerprint = filter_fingerprint(filters)
    after = decode_cursor(cursor, fingerprint)
    query, values = candidate_query(filters, after, limit)
    cur.execute(query, values)
    candidates = list(cur.fetchall())
    has_more = len(candidates) > limit
    selected = candidates[:limit]
    inference_ids = sorted({row["inference_id"] for row in selected})
    current = current_inference_ids(cur, inference_ids)
    cases = [present_summary(row) for row in selected if row["inference_id"] in current]
    return {
        "cases": cases,
        "has_more": has_more,
        "next_cursor": encode_cursor(selected[-1], fingerprint) if has_more else None,
        "coverage": {
            "checked_scopes": len(inference_ids),
            "awaiting_refresh_in_page": len(inference_ids) - len(current),
            "note": COVERAGE_NOTE,
            "missing_source_families": MISSING_SOURCE_FAMILIES,
        },
    }


def load_case(cur, case_key: str) -> dict | None:
    cur.execute(
        """
        SELECT case_key, inference_id, family
        FROM public.emerging_case_index
        WHERE case_key = %s AND published
        """,
        (case_key,),
    )
    candidate = cur.fetchone()
    if not candidate:
        return None
    inference_id = candidate["inference_id"]
    if inference_id not in current_inference_ids(cur, [inference_id]):
        return None
    cur.execute(
        """
        SELECT subject_key, created_at, payload
        FROM meta.intelligence_inference_history WHERE inference_id = %s
        """,
        (inference_id,),
    )
    history = cur.fetchone()
    payload = history["payload"]
    hypothesis = next(
        item
        for item in payload["analysis"]["hypotheses"]
        if item["family"] == candidate["family"]
    )
    row = {
        "case_key": case_key,
        "inference_id": inference_id,
        "created_at": history["created_at"],
        "packet": payload["packet"],
        "analysis": payload["analysis"],
        "hypothesis": hypothesis,
    }
    return present_cases(cur, [row])[0]
