"""Operational health endpoint."""

import logging
import os
import threading
import time

from fastapi import APIRouter
from psycopg2 import Error as PsycopgError
from psycopg2.errors import UndefinedTable

from api.lib.database import get_cursor
from api.lib.response_types import OpsHealthResponse, SourceStatus
from api.lib.settings import county_metadata

router = APIRouter(tags=["ops"])
logger = logging.getLogger(__name__)

# The frontend Nav fetches this endpoint on every client-side navigation and
# each uncached hit costs 15 COUNT(*) scans. Health staleness of a minute is
# fine, so cache the payload per worker process.
_CACHE_TTL_SECONDS = int(os.environ.get("COUNTYIQ_OPS_HEALTH_TTL", "60"))
_cache_lock = threading.Lock()
_cached_response: OpsHealthResponse | None = None
_cached_at: float = 0.0


def _get_source_status(cur, source_name: str, table: str) -> SourceStatus:
    try:
        cur.execute(f"SELECT COUNT(*) AS cnt FROM {table} WHERE valid_to IS NULL")
        row = cur.fetchone()
        count = row["cnt"]
        return {
            "status": "green" if count > 0 else "red",
            "record_count": count,
        }
    except UndefinedTable:
        cur.connection.rollback()
        logger.info("Ops health source missing table for %s: %s", source_name, table)
        return {"status": "red", "record_count": 0, "error": "missing_table"}
    except PsycopgError as exc:
        cur.connection.rollback()
        logger.warning("Ops health query failed for %s (%s): %s", source_name, table, exc)
        return {"status": "red", "record_count": 0, "error": "query_failed"}


def _get_municipality_source_status(cur, county_key: str = "york") -> SourceStatus:
    """Summarize per-body policy and live listing health."""

    try:
        cur.execute(
            """
            SELECT
                COUNT(*) AS configured_count,
                COUNT(*) FILTER (WHERE r.acquisition_allowed) AS active_count,
                COUNT(*) FILTER (
                    WHERE r.acquisition_allowed
                      AND h.listing_status IN ('ok', 'not_modified')
                ) AS healthy_count,
                COUNT(*) FILTER (
                    WHERE r.rights_status = 'paused'
                       OR h.listing_status IN (
                            'access_error', 'no_documents', 'partial_error',
                            'render_error', 'robots_skipped',
                            'needs_playwright', 'policy_skipped',
                            'policy_no_documents'
                       )
                ) AS blocked_count,
                COUNT(*) FILTER (
                    WHERE r.acquisition_allowed AND h.source_key IS NULL
                ) AS unchecked_count,
                COALESCE(
                    SUM(h.document_count) FILTER (WHERE r.acquisition_allowed),
                    0
                ) AS document_count
            FROM meta.municipality_source_rights r
            LEFT JOIN meta.municipality_source_health h USING (source_key)
            WHERE r.county_key = %(county_key)s
            """
            , {"county_key": county_key}
        )
        row = cur.fetchone()
        active = int(row["active_count"] or 0)
        healthy = int(row["healthy_count"] or 0)
        return {
            "status": "green" if active > 0 and healthy == active else "red",
            "record_count": int(row["document_count"] or 0),
            "configured_count": int(row["configured_count"] or 0),
            "active_count": active,
            "healthy_count": healthy,
            "blocked_count": int(row["blocked_count"] or 0),
            "unchecked_count": int(row["unchecked_count"] or 0),
        }
    except UndefinedTable:
        cur.connection.rollback()
        return {"status": "red", "record_count": 0, "error": "missing_table"}
    except PsycopgError as exc:
        cur.connection.rollback()
        logger.warning("Municipality source health query failed: %s", exc)
        return {"status": "red", "record_count": 0, "error": "query_failed"}


def _get_source_policy_status(cur, county_key: str = "york") -> SourceStatus:
    """Summarize review deadlines for every governed top-level source."""

    try:
        cur.execute(
            """
            SELECT
                COUNT(*) AS configured_count,
                COUNT(*) FILTER (WHERE acquisition_allowed) AS active_count,
                COUNT(*) FILTER (WHERE rights_status = 'conditional') AS conditional_count,
                COUNT(*) FILTER (WHERE rights_status = 'paused') AS paused_count,
                COUNT(*) FILTER (WHERE review_due_on < CURRENT_DATE) AS overdue_count,
                COUNT(*) FILTER (
                    WHERE review_due_on BETWEEN CURRENT_DATE AND CURRENT_DATE + 30
                ) AS due_soon_count,
                MIN(review_due_on) FILTER (
                    WHERE review_due_on >= CURRENT_DATE
                ) AS next_review_on
            FROM meta.source_rights
            WHERE county_key IS NULL OR county_key = %(county_key)s
            """
            , {"county_key": county_key}
        )
        row = cur.fetchone()
        configured = int(row["configured_count"] or 0)
        active = int(row["active_count"] or 0)
        overdue = int(row["overdue_count"] or 0)
        return {
            "status": "red" if overdue else "green",
            "record_count": active,
            "configured_count": configured,
            "active_count": active,
            "healthy_count": max(active - overdue, 0),
            "blocked_count": int(row["paused_count"] or 0) + overdue,
            "unchecked_count": 0,
            "conditional_count": int(row["conditional_count"] or 0),
            "paused_count": int(row["paused_count"] or 0),
            "overdue_count": overdue,
            "due_soon_count": int(row["due_soon_count"] or 0),
            "next_review_on": row["next_review_on"],
        }
    except UndefinedTable:
        cur.connection.rollback()
        return {"status": "red", "record_count": 0, "error": "missing_table"}
    except PsycopgError as exc:
        cur.connection.rollback()
        logger.warning("Source policy health query failed: %s", exc)
        return {"status": "red", "record_count": 0, "error": "query_failed"}


@router.get("/health")
def health() -> OpsHealthResponse:
    """System health — source record counts and database connectivity (60s cache)."""
    global _cached_response, _cached_at
    with _cache_lock:
        if _cached_response is not None and time.monotonic() - _cached_at < _CACHE_TTL_SECONDS:
            return _cached_response

    response = _compute_health()

    with _cache_lock:
        _cached_response = response
        _cached_at = time.monotonic()
    return response


def _compute_health() -> OpsHealthResponse:
    sources: dict[str, SourceStatus] = {}
    county_key = county_metadata()["county_key"]
    with get_cursor() as cur:
        tables = {
            "parcels": "staging.parcels",
            "municipalities": "staging.municipalities",
            "address_points": "staging.address_points",
            "structures": "staging.structures",
            "roads": "staging.roads",
            "zoning": "staging.zoning",
            "flood_zones": "staging.flood_zones",
            "plcb_licenses": "staging.plcb_licenses",
            "pa_open_data": "staging.pa_open_data",
            "penndot_roads": "staging.penndot_roads",
            "penndot_projects": "staging.penndot_projects",
            "tax_claims": "staging.tax_claims",
            "sheriff_sales": "staging.sheriff_sales",
            "traffic_counts": "staging.traffic_counts",
            "zipcodes": "staging.zipcodes",
            "zoning_overlays": "staging.zoning_overlays",
            "economic_development_parks": "staging.economic_development_parks",
            "soils": "staging.soils",
            "local_traffic_counts": "staging.local_traffic_counts",
            "environmental_diligence": "staging.environmental_diligence_sites",
        }
        for name, table in tables.items():
            sources[name] = _get_source_status(cur, name, table)
        sources["source_governance"] = _get_source_policy_status(cur, county_key)
        sources["municipal_proceedings"] = _get_municipality_source_status(cur, county_key)

    green = sum(1 for s in sources.values() if s["status"] == "green")
    total = len(sources)

    return {
        "overall": "green" if green == total else "yellow" if green > total // 2 else "red",
        "sources": sources,
        "summary": f"{green}/{total} sources active",
    }
