"""Operational health endpoint."""

import logging
import os
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import TypedDict

from api.lib.database import get_cursor
from api.lib.response_types import (
    IntelligenceIntegrityStatus,
    OpsHealthResponse,
    SourceStatus,
)
from api.lib.settings import county_metadata
from fastapi import APIRouter
from psycopg2 import Error as PsycopgError
from psycopg2.errors import UndefinedTable

router = APIRouter(tags=["ops"])
logger = logging.getLogger(__name__)

# The frontend Nav fetches this endpoint on every client-side navigation and
# each uncached hit performs current-row count scans. Health staleness of a
# minute is fine, so cache the payload per worker process.
_CACHE_TTL_SECONDS = int(os.environ.get("COUNTYIQ_OPS_HEALTH_TTL", "60"))
_cache_lock = threading.Lock()
_cached_response: OpsHealthResponse | None = None
_cached_at: float = 0.0

_WEEKLY_MAX_AGE_HOURS = 8 * 24
_MONTHLY_MAX_AGE_HOURS = 35 * 24
_CONTRADICTION_MAX_AGE_HOURS = max(
    int(os.environ.get("COUNTYIQ_CONTRADICTION_MAX_AGE_HOURS", "72")), 1
)

# Each entry is (staging table, scheduled refresh job, maximum healthy age).
# Manual and paused assets do not belong in product health. In particular,
# staging.pa_open_data is a manual compatibility table with no alpha consumer.
_SOURCE_CONFIGS: dict[str, tuple[str, str, int]] = {
    "parcels": ("staging.parcels", "arcgis_refresh", _WEEKLY_MAX_AGE_HOURS),
    "municipalities": (
        "staging.municipalities",
        "arcgis_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "address_points": (
        "staging.address_points",
        "arcgis_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "structures": ("staging.structures", "arcgis_refresh", _WEEKLY_MAX_AGE_HOURS),
    "roads": ("staging.roads", "arcgis_refresh", _WEEKLY_MAX_AGE_HOURS),
    "zoning": ("staging.zoning", "arcgis_refresh", _WEEKLY_MAX_AGE_HOURS),
    "flood_zones": ("staging.flood_zones", "fema_refresh", _WEEKLY_MAX_AGE_HOURS),
    "corporate_entities": (
        "staging.corporate_entities",
        "pa_dos_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "plcb_licenses": ("staging.plcb_licenses", "bulk_refresh", _MONTHLY_MAX_AGE_HOURS),
    "penndot_roads": ("staging.penndot_roads", "arcgis_refresh", _WEEKLY_MAX_AGE_HOURS),
    "penndot_projects": (
        "staging.penndot_projects",
        "arcgis_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "tax_claims": ("staging.tax_claims", "bulk_refresh", _MONTHLY_MAX_AGE_HOURS),
    "sheriff_sales": (
        "staging.sheriff_sales",
        "scraper_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "traffic_counts": (
        "staging.traffic_counts",
        "arcgis_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "zipcodes": ("staging.zipcodes", "arcgis_refresh", _WEEKLY_MAX_AGE_HOURS),
    "zoning_overlays": (
        "staging.zoning_overlays",
        "radar_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "planning_subdivisions": (
        "staging.planning_subdivisions",
        "radar_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "growth_areas": (
        "staging.growth_areas",
        "radar_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "future_landuse": (
        "staging.future_landuse",
        "radar_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "conservation_easements": (
        "staging.conservation_easements",
        "radar_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "ag_security": (
        "staging.ag_security",
        "radar_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "economic_development_parks": (
        "staging.economic_development_parks",
        "radar_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "soils": ("staging.soils", "radar_refresh", _WEEKLY_MAX_AGE_HOURS),
    "local_traffic_counts": (
        "staging.local_traffic_counts",
        "radar_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
    "environmental_diligence": (
        "staging.environmental_diligence_sites",
        "radar_refresh",
        _WEEKLY_MAX_AGE_HOURS,
    ),
}


class _JobRunStatus(TypedDict):
    job_name: str
    status: str
    started_at: datetime | None
    finished_at: datetime
    last_success_at: datetime | None


def _get_job_run_statuses(cur) -> dict[str, _JobRunStatus]:
    """Read the application-owned projection of Dagster run outcomes."""

    try:
        cur.execute(
            """
            SELECT job_name, status, started_at, finished_at, last_success_at
            FROM meta.job_run_status
            """
        )
        return {row["job_name"]: row for row in cur.fetchall()}
    except UndefinedTable:
        cur.connection.rollback()
        logger.info("Ops health job-run ledger is not migrated yet")
        return {}
    except PsycopgError as exc:
        cur.connection.rollback()
        logger.warning("Ops health job-run query failed: %s", exc)
        return {}


def _latest_job_run(
    job_runs: dict[str, _JobRunStatus],
    *job_names: str,
) -> _JobRunStatus | None:
    candidates = (job_runs[name] for name in job_names if name in job_runs)
    return max(candidates, key=lambda run: run["finished_at"], default=None)


def _apply_run_health(
    source: SourceStatus,
    *,
    job_name: str,
    max_age_hours: int,
    run: _JobRunStatus | None,
    now: datetime,
) -> SourceStatus:
    """Combine row availability with the latest scheduled-job outcome."""

    source["refresh_job"] = job_name
    source["expected_refresh_hours"] = max_age_hours

    if source.get("error"):
        return source

    if run is None:
        source.update(
            {
                "status": "red",
                "status_reason": "run_not_observed",
                "last_run_status": "unknown",
                "stale": True,
            }
        )
        return source

    source["last_run_status"] = run["status"]
    source["last_run_job"] = run["job_name"]
    source["last_run_at"] = run["finished_at"]
    source["last_success_at"] = run["last_success_at"]

    last_success_at = run["last_success_at"]
    if last_success_at is None:
        source["stale"] = True
    else:
        freshness_due_at = last_success_at + timedelta(hours=max_age_hours)
        source["freshness_due_at"] = freshness_due_at
        source["stale"] = now > freshness_due_at

    if run["status"] == "failure":
        source["status"] = "red"
        source["status_reason"] = "last_run_failed"
    elif source["stale"]:
        source["status"] = "red"
        source["status_reason"] = "stale"
    elif source["status"] == "green":
        source["status_reason"] = "healthy"

    return source


def _get_source_status(cur, source_name: str, table: str) -> SourceStatus:
    try:
        cur.execute(f"SELECT COUNT(*) AS cnt FROM {table} WHERE valid_to IS NULL")
        row = cur.fetchone()
        count = row["cnt"]
        return {
            "status": "green" if count > 0 else "red",
            "record_count": count,
            "status_reason": "healthy" if count > 0 else "empty_source",
        }
    except UndefinedTable:
        cur.connection.rollback()
        logger.info("Ops health source missing table for %s: %s", source_name, table)
        return {
            "status": "red",
            "record_count": 0,
            "status_reason": "missing_table",
            "error": "missing_table",
        }
    except PsycopgError as exc:
        cur.connection.rollback()
        logger.warning(
            "Ops health query failed for %s (%s): %s", source_name, table, exc
        )
        return {
            "status": "red",
            "record_count": 0,
            "status_reason": "query_failed",
            "error": "query_failed",
        }


def _get_municipality_source_status(
    cur,
    county_key: str = "york",
    max_age_hours: int = _WEEKLY_MAX_AGE_HOURS,
) -> SourceStatus:
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
                      AND h.checked_at >= NOW() - %(max_age)s
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
                COUNT(*) FILTER (
                    WHERE r.acquisition_allowed
                      AND h.source_key IS NOT NULL
                      AND h.checked_at < NOW() - %(max_age)s
                ) AS stale_count,
                MAX(h.checked_at) FILTER (
                    WHERE r.acquisition_allowed
                ) AS last_checked_at,
                MIN(h.checked_at) FILTER (
                    WHERE r.acquisition_allowed
                ) AS oldest_checked_at,
                COALESCE(
                    SUM(h.document_count) FILTER (WHERE r.acquisition_allowed),
                    0
                ) AS document_count
            FROM meta.municipality_source_rights r
            LEFT JOIN meta.municipality_source_health h USING (source_key)
            WHERE r.county_key = %(county_key)s
            """,
            {
                "county_key": county_key,
                "max_age": timedelta(hours=max_age_hours),
            },
        )
        row = cur.fetchone()
        active = int(row["active_count"] or 0)
        healthy = int(row["healthy_count"] or 0)
        stale = int(row["stale_count"] or 0)
        unchecked = int(row["unchecked_count"] or 0)
        is_healthy = active > 0 and healthy == active and stale == 0 and unchecked == 0
        return {
            "status": "green" if is_healthy else "red",
            "status_reason": "healthy" if is_healthy else "source_unhealthy",
            "record_count": int(row["document_count"] or 0),
            "configured_count": int(row["configured_count"] or 0),
            "active_count": active,
            "healthy_count": healthy,
            "blocked_count": int(row["blocked_count"] or 0),
            "unchecked_count": unchecked,
            "stale_count": stale,
            "last_checked_at": row["last_checked_at"],
            "oldest_checked_at": row["oldest_checked_at"],
        }
    except UndefinedTable:
        cur.connection.rollback()
        return {
            "status": "red",
            "record_count": 0,
            "status_reason": "missing_table",
            "error": "missing_table",
        }
    except PsycopgError as exc:
        cur.connection.rollback()
        logger.warning("Municipality source health query failed: %s", exc)
        return {
            "status": "red",
            "record_count": 0,
            "status_reason": "query_failed",
            "error": "query_failed",
        }


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
            """,
            {"county_key": county_key},
        )
        row = cur.fetchone()
        configured = int(row["configured_count"] or 0)
        active = int(row["active_count"] or 0)
        overdue = int(row["overdue_count"] or 0)
        return {
            "status": "red" if overdue else "green",
            "status_reason": "policy_overdue" if overdue else "healthy",
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
        return {
            "status": "red",
            "record_count": 0,
            "status_reason": "missing_table",
            "error": "missing_table",
        }
    except PsycopgError as exc:
        cur.connection.rollback()
        logger.warning("Source policy health query failed: %s", exc)
        return {
            "status": "red",
            "record_count": 0,
            "status_reason": "query_failed",
            "error": "query_failed",
        }


def _empty_integrity_status(
    reason: str,
    *,
    max_age_hours: int = _CONTRADICTION_MAX_AGE_HOURS,
) -> IntelligenceIntegrityStatus:
    return {
        "status": "red",
        "status_reason": reason,
        "history_count": 0,
        "accepted_count": 0,
        "quarantined_count": 0,
        "human_resolution_inference_count": 0,
        "contradiction_count": 0,
        "unresolved_contradiction_count": 0,
        "resolved_contradiction_count": 0,
        "oldest_unresolved_at": None,
        "projection_count": 0,
        "unlinked_projection_count": 0,
        "projection_mismatch_count": 0,
        "validation_rejection_count": 0,
        "validation_rejections_last_24h": 0,
        "latest_validation_rejection_at": None,
        "max_unresolved_age_hours": max_age_hours,
    }


def _get_intelligence_integrity_status(
    cur,
    *,
    now: datetime,
    max_age_hours: int = _CONTRADICTION_MAX_AGE_HOURS,
) -> IntelligenceIntegrityStatus:
    """Read aggregate, non-sensitive health for the immutable LLM boundary."""

    try:
        cur.execute(
            """
            SELECT integrity.*, rejection.rejection_count,
                   rejection.rejections_last_24h,
                   rejection.latest_rejection_at
            FROM meta.intelligence_integrity_status AS integrity
            CROSS JOIN meta.intelligence_validation_rejection_status AS rejection
            """
        )
        row = cur.fetchone()
        if row is None:
            return _empty_integrity_status("query_failed", max_age_hours=max_age_hours)

        unlinked = int(row["unlinked_projection_count"] or 0)
        mismatched = int(row["projection_mismatch_count"] or 0)
        unresolved = int(row["unresolved_contradiction_count"] or 0)
        recent_rejections = int(row.get("rejections_last_24h") or 0)
        oldest = row["oldest_unresolved_at"]
        stale = bool(
            oldest is not None
            and now > oldest + timedelta(hours=max_age_hours)
        )
        if mismatched:
            status, reason = "red", "projection_mismatch"
        elif unlinked:
            status, reason = "red", "projection_unlinked"
        elif stale:
            status, reason = "red", "stale_contradictions"
        elif unresolved:
            status, reason = "yellow", "unresolved_contradictions"
        elif recent_rejections:
            status, reason = "yellow", "recent_validation_rejections"
        else:
            status, reason = "green", "healthy"

        return {
            "status": status,
            "status_reason": reason,
            "history_count": int(row["history_count"] or 0),
            "accepted_count": int(row["accepted_count"] or 0),
            "quarantined_count": int(row["quarantined_count"] or 0),
            "human_resolution_inference_count": int(
                row["human_resolution_inference_count"] or 0
            ),
            "contradiction_count": int(row["contradiction_count"] or 0),
            "unresolved_contradiction_count": unresolved,
            "resolved_contradiction_count": int(
                row["resolved_contradiction_count"] or 0
            ),
            "oldest_unresolved_at": oldest,
            "projection_count": int(row["projection_count"] or 0),
            "unlinked_projection_count": unlinked,
            "projection_mismatch_count": mismatched,
            "validation_rejection_count": int(row.get("rejection_count") or 0),
            "validation_rejections_last_24h": recent_rejections,
            "latest_validation_rejection_at": row.get("latest_rejection_at"),
            "max_unresolved_age_hours": max_age_hours,
        }
    except UndefinedTable:
        cur.connection.rollback()
        logger.info("Intelligence integrity health view is not migrated yet")
        return _empty_integrity_status("missing_table", max_age_hours=max_age_hours)
    except PsycopgError as exc:
        cur.connection.rollback()
        logger.warning("Intelligence integrity health query failed: %s", exc)
        return _empty_integrity_status("query_failed", max_age_hours=max_age_hours)


@router.get("/health")
def health() -> OpsHealthResponse:
    """System health — source record counts and database connectivity (60s cache)."""
    global _cached_response, _cached_at
    with _cache_lock:
        if (
            _cached_response is not None
            and time.monotonic() - _cached_at < _CACHE_TTL_SECONDS
        ):
            return _cached_response

    response = _compute_health()

    with _cache_lock:
        _cached_response = response
        _cached_at = time.monotonic()
    return response


def _compute_health() -> OpsHealthResponse:
    sources: dict[str, SourceStatus] = {}
    county_key = county_metadata()["county_key"]
    now = datetime.now(UTC)
    with get_cursor() as cur:
        job_runs = _get_job_run_statuses(cur)
        for name, (table, job_name, max_age_hours) in _SOURCE_CONFIGS.items():
            sources[name] = _apply_run_health(
                _get_source_status(cur, name, table),
                job_name=job_name,
                max_age_hours=max_age_hours,
                run=job_runs.get(job_name),
                now=now,
            )
        sources["source_governance"] = _get_source_policy_status(cur, county_key)
        sources["municipal_proceedings"] = _apply_run_health(
            _get_municipality_source_status(cur, county_key),
            job_name="scraper_refresh",
            max_age_hours=_WEEKLY_MAX_AGE_HOURS,
            run=_latest_job_run(
                job_runs,
                "scraper_refresh",
                "proceedings_refresh",
            ),
            now=now,
        )
        intelligence_integrity = _get_intelligence_integrity_status(cur, now=now)

    green = sum(1 for s in sources.values() if s["status"] == "green")
    total = len(sources)

    source_overall = (
        "green" if green == total else "yellow" if green > total // 2 else "red"
    )
    if intelligence_integrity["status"] == "red" or source_overall == "red":
        overall = "red"
    elif intelligence_integrity["status"] == "yellow" or source_overall == "yellow":
        overall = "yellow"
    else:
        overall = "green"

    return {
        "overall": overall,
        "sources": sources,
        "intelligence_integrity": intelligence_integrity,
        "summary": (
            f"{green}/{total} sources healthy; intelligence integrity "
            f"{intelligence_integrity['status']}"
        ),
    }
