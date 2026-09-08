"""Municipality listing and profile endpoints."""

import json
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query

from api.lib.database import get_cursor
from api.lib.feed_cache import feed_pages, read_feed_revision
from api.lib.municipal_evidence import fetch_municipal_evidence
from api.lib.municipality_names import (
    muni_name_to_pattern,
    municipality_event_patterns,
)
from api.lib.response_types import MunicipalityProfileResponse, MunicipalitySummary
from api.lib.settings import open_data_source_key
from api.lib.source_policy import require_source_use, source_use_allowed

PIPELINE_WINDOW_DAYS = 365

router = APIRouter(tags=["municipalities"])


@router.get("/{name}/evidence")
def get_municipal_evidence(name: str, limit: int = Query(12, ge=1, le=100)) -> dict:
    with get_cursor() as cur:
        require_source_use(cur, "public_proceedings", "derived_product")
        return fetch_municipal_evidence(cur, municipality=name, limit=limit)


def _fetch_municipality_stats(cur, municipality_name: str) -> dict:
    cur.execute(
        """
        SELECT
            COUNT(DISTINCT pidn) AS parcel_count,
            COALESCE(SUM(COALESCE(aprtotal, 0)), 0) AS total_assessed
        FROM staging.parcels
        WHERE valid_to IS NULL
          AND UPPER(municipality) LIKE UPPER(%(municipality)s) || '%%'
        """,
        {"municipality": municipality_name},
    )
    row = cur.fetchone() or {}
    return {
        "parcel_count": row.get("parcel_count", 0) or 0,
        "total_assessed": float(row.get("total_assessed", 0) or 0),
    }


def _fetch_municipality_delinquency(cur, district_pattern: str) -> dict:
    cur.execute(
        """
        SELECT
            COUNT(DISTINCT pidn) AS delinquent_parcels,
            COALESCE(SUM(CASE WHEN total > 0 THEN total ELSE 0 END), 0) AS total_delinquent,
            MIN(tax_year) AS oldest_delinquent_year,
            COUNT(DISTINCT tax_year) AS delinquent_years
        FROM staging.tax_claims
        WHERE valid_to IS NULL
          AND UPPER(tax_district_name) LIKE UPPER(%(pattern)s)
        """,
        {"pattern": district_pattern},
    )
    row = cur.fetchone() or {}
    return {
        "delinquent_parcels": row.get("delinquent_parcels", 0) or 0,
        "total_delinquent": float(row.get("total_delinquent", 0) or 0),
        "oldest_delinquent_year": row.get("oldest_delinquent_year"),
        "delinquent_years": row.get("delinquent_years", 0) or 0,
    }


def _fetch_development_pipeline(cur, municipality_name: str) -> dict | None:
    """Summarize the same current, explained matters shown by Activity."""
    if not source_use_allowed(cur, "public_proceedings", "derived_product"):
        return None
    patterns = [
        pattern.upper() for pattern in municipality_event_patterns(municipality_name)
    ]
    revision, checked_at = read_feed_revision(cur)
    cache_key = json.dumps(["municipality_pipeline", patterns, PIPELINE_WINDOW_DAYS])
    cached = feed_pages.get(cache_key, revision, checked_at)
    if cached is not None:
        return cached
    cur.execute(
        """
        WITH municipal_events AS MATERIALIZED (
            SELECT event_key, event_type, title, event_date, project_key, project_name,
                related_pidns, event_tags, detected_at,
                COALESCE(event_date, detected_at::date) AS effective_date
            FROM public.current_activity_events
            WHERE category = 'development'
                AND municipality IS NOT NULL
                AND UPPER(municipality) LIKE ANY(%(patterns)s)
                AND COALESCE(event_date, detected_at::date)
                    >= CURRENT_DATE - GREATEST(%(window)s, 60)
                AND source_evidence->0->'details'->>'discovery_eligible'
                    IS DISTINCT FROM 'false'
        ), counts AS (
            SELECT event_type, COUNT(*) AS count
            FROM municipal_events
            WHERE effective_date >= CURRENT_DATE - %(window)s
            GROUP BY event_type
        ), upcoming AS (
            SELECT * FROM municipal_events
            WHERE event_tags && ARRAY['upcoming_decision', 'hearing']::text[]
                AND effective_date >= CURRENT_DATE - 60
            ORDER BY effective_date DESC, event_key
            LIMIT 8
        ), recent AS (
            SELECT * FROM municipal_events
            WHERE effective_date >= CURRENT_DATE - %(window)s
            ORDER BY effective_date DESC, detected_at DESC, event_key
            LIMIT 12
        ), policy AS (
            SELECT * FROM municipal_events
            WHERE event_tags && ARRAY['policy_action']::text[]
                AND effective_date >= CURRENT_DATE - %(window)s
            ORDER BY effective_date DESC, detected_at DESC, event_key
            LIMIT 8
        )
        SELECT
            COALESCE((
                SELECT jsonb_agg(to_jsonb(counts) ORDER BY count DESC, event_type)
                FROM counts
            ), '[]'::jsonb) AS by_event_type,
            COALESCE((
                SELECT jsonb_agg(
                    to_jsonb(upcoming) - ARRAY['event_tags', 'detected_at', 'effective_date']
                    ORDER BY effective_date DESC, event_key
                ) FROM upcoming
            ), '[]'::jsonb) AS upcoming,
            COALESCE((
                SELECT jsonb_agg(
                    to_jsonb(recent) - ARRAY['event_tags', 'detected_at', 'effective_date']
                    ORDER BY effective_date DESC, detected_at DESC, event_key
                ) FROM recent
            ), '[]'::jsonb) AS recent,
            COALESCE((
                SELECT jsonb_agg(
                    to_jsonb(policy) - ARRAY['event_tags', 'detected_at', 'effective_date']
                    ORDER BY effective_date DESC, detected_at DESC, event_key
                ) FROM policy
            ), '[]'::jsonb) AS policy
        """,
        {"patterns": patterns, "window": PIPELINE_WINDOW_DAYS},
    )
    result = dict(cur.fetchone())
    result["window_days"] = PIPELINE_WINDOW_DAYS
    result["total_matters"] = sum(int(row["count"]) for row in result["by_event_type"])
    feed_pages.put(cache_key, revision, checked_at + timedelta(seconds=60), result)
    return result


def _fetch_radar_top(cur, municipality_name: str, *, limit: int = 8) -> list[dict]:
    """Top opportunity parcels for the municipality, or [] when radar sources are gated."""
    for source_key in ("penndot_open_data", "fema_nfhl"):
        if not source_use_allowed(cur, source_key, "derived_product"):
            return []
    cur.execute(
        """
        SELECT dm.pidn, p.propadr, p.acres, dm.opportunity_score, dm.score,
               dm.top_signal, dm.opportunity_delta, dm.is_new
        FROM public.current_development_momentum dm
        JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
        WHERE dm.eligible = TRUE
          AND dm.has_active_plan = FALSE
          AND dm.opportunity_score > 0
          AND UPPER(p.municipality) LIKE UPPER(%(municipality)s) || '%%'
        ORDER BY dm.opportunity_score DESC, dm.signal_count DESC, dm.pidn
        LIMIT %(limit)s
        """,
        {"municipality": municipality_name, "limit": limit},
    )
    rows = []
    for row in cur.fetchall():
        item = dict(row)
        item["acres"] = float(item["acres"]) if item.get("acres") is not None else None
        item["is_new"] = bool(item.get("is_new"))
        rows.append(item)
    return rows


def _fetch_municipality_licenses(
    cur, municipality_name: str, *, limit: int = 50
) -> list[dict]:
    cur.execute(
        """
        SELECT
            NULL::text AS licensee,
            premises_name,
            premises_address,
            license_type,
            status,
            municipality,
            last_issue_date,
            expiration_date
        FROM staging.plcb_licenses
        WHERE valid_to IS NULL
          AND UPPER(status) = 'ACTIVE'
          AND UPPER(municipality) LIKE UPPER(%(municipality)s) || '%%'
        ORDER BY premises_name NULLS LAST, premises_address
        LIMIT %(limit)s
        """,
        {"municipality": municipality_name, "limit": limit},
    )
    return [dict(row) for row in cur.fetchall()]


@router.get("", response_model=None)
def list_municipalities() -> list[MunicipalitySummary]:
    """List all municipalities with delinquency stats."""
    with get_cursor() as cur:
        require_source_use(
            cur, open_data_source_key(), "derived_product", conceal=False
        )
        require_source_use(cur, "tax_claims", "derived_product", conceal=False)
        cur.execute("""
            SELECT name, muni_type
            FROM staging.municipalities
            WHERE valid_to IS NULL
            ORDER BY name
        """)
        munis = cur.fetchall()

        cur.execute("""
            SELECT
                tax_district_name,
                COUNT(DISTINCT pidn) AS delinquent_parcels,
                COALESCE(SUM(CASE WHEN total > 0 THEN total ELSE 0 END), 0) AS total_delinquent
            FROM staging.tax_claims
            WHERE valid_to IS NULL
            GROUP BY tax_district_name
        """)
        district_stats = {row["tax_district_name"]: row for row in cur.fetchall()}

    results = []
    for muni in munis:
        pattern = muni_name_to_pattern(muni["name"])
        base = pattern.rstrip("%").upper()
        delinquent_parcels = 0
        total_delinquent = 0.0
        for dist_name, stats in district_stats.items():
            if dist_name.upper().startswith(base):
                delinquent_parcels += stats["delinquent_parcels"]
                total_delinquent += float(stats["total_delinquent"])

        results.append(
            {
                "name": muni["name"],
                "muni_type": muni["muni_type"],
                "delinquent_parcels": delinquent_parcels,
                "total_delinquent": round(total_delinquent, 2),
            }
        )

    return results


@router.get("/{name}")
def get_municipality(name: str) -> MunicipalityProfileResponse:
    """Get a single municipality profile."""
    with get_cursor(snapshot=True) as cur:
        require_source_use(
            cur, open_data_source_key(), "derived_product", conceal=False
        )
        require_source_use(cur, "tax_claims", "derived_product", conceal=False)
        require_source_use(cur, "plcb_licenses", "derived_product", conceal=False)
        cur.execute(
            """
            SELECT name, muni_type, county
            FROM staging.municipalities
            WHERE valid_to IS NULL AND UPPER(name) = UPPER(%s)
            """,
            (name,),
        )
        muni = cur.fetchone()
        if not muni:
            raise HTTPException(
                status_code=404, detail=f"Municipality not found: {name}"
            )

        pattern = muni_name_to_pattern(muni["name"])
        stats = _fetch_municipality_stats(cur, muni["name"])
        delinquency = _fetch_municipality_delinquency(cur, pattern)
        licenses = _fetch_municipality_licenses(cur, muni["name"], limit=50)
        development_pipeline = _fetch_development_pipeline(cur, muni["name"])
        radar_top = _fetch_radar_top(cur, muni["name"])

    return {
        **dict(muni),
        "stats": stats,
        "delinquency": delinquency,
        "licenses": licenses,
        "development_pipeline": development_pipeline,
        "radar_top": radar_top,
    }
