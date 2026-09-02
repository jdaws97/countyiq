from __future__ import annotations

from datetime import UTC, date, datetime

from api.routes.ops import (
    _SOURCE_CONFIGS,
    _apply_run_health,
    _get_intelligence_integrity_status,
    _get_municipality_source_status,
    _get_source_policy_status,
    _get_source_status,
    _latest_job_run,
)


class _Cursor:
    def __init__(self, row: dict):
        self.row = row
        self.query = ""

    def execute(self, query: str, _params=None) -> None:
        self.query = query

    def fetchone(self) -> dict:
        return self.row


def test_product_health_covers_scheduled_sources_not_manual_compatibility():
    assert "pa_open_data" not in _SOURCE_CONFIGS
    assert {
        "corporate_entities",
        "planning_subdivisions",
        "growth_areas",
        "future_landuse",
        "conservation_easements",
        "ag_security",
    }.issubset(_SOURCE_CONFIGS)


def test_source_policy_health_exposes_review_deadlines():
    cursor = _Cursor(
        {
            "configured_count": 11,
            "active_count": 9,
            "conditional_count": 4,
            "paused_count": 2,
            "overdue_count": 0,
            "due_soon_count": 2,
            "next_review_on": date(2026, 11, 27),
        }
    )

    status = _get_source_policy_status(cursor)

    assert status == {
        "status": "green",
        "status_reason": "healthy",
        "record_count": 9,
        "configured_count": 11,
        "active_count": 9,
        "healthy_count": 9,
        "blocked_count": 2,
        "unchecked_count": 0,
        "conditional_count": 4,
        "paused_count": 2,
        "overdue_count": 0,
        "due_soon_count": 2,
        "next_review_on": date(2026, 11, 27),
    }
    assert "CURRENT_DATE + 30" in cursor.query


def test_municipality_health_excludes_paused_document_counts():
    cursor = _Cursor(
        {
            "configured_count": 122,
            "active_count": 110,
            "healthy_count": 96,
            "blocked_count": 26,
            "unchecked_count": 0,
            "stale_count": 0,
            "last_checked_at": datetime(2026, 8, 30, 7, tzinfo=UTC),
            "oldest_checked_at": datetime(2026, 8, 24, 7, tzinfo=UTC),
            "document_count": 7152,
        }
    )

    status = _get_municipality_source_status(cursor)

    assert status == {
        "status": "red",
        "status_reason": "source_unhealthy",
        "record_count": 7152,
        "configured_count": 122,
        "active_count": 110,
        "healthy_count": 96,
        "blocked_count": 26,
        "unchecked_count": 0,
        "stale_count": 0,
        "last_checked_at": datetime(2026, 8, 30, 7, tzinfo=UTC),
        "oldest_checked_at": datetime(2026, 8, 24, 7, tzinfo=UTC),
    }
    assert "SUM(h.document_count) FILTER (WHERE r.acquisition_allowed)" in cursor.query
    assert "policy_skipped" in cursor.query
    assert "policy_no_documents" in cursor.query
    assert "h.checked_at >= NOW() - %(max_age)s" in cursor.query


def test_source_health_requires_a_recent_successful_job_run():
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    last_success = datetime(2026, 8, 25, 6, tzinfo=UTC)
    source = _get_source_status(_Cursor({"cnt": 176_060}), "parcels", "staging.parcels")

    status = _apply_run_health(
        source,
        job_name="arcgis_refresh",
        max_age_hours=8 * 24,
        run={
            "job_name": "arcgis_refresh",
            "status": "success",
            "started_at": datetime(2026, 8, 25, 5, tzinfo=UTC),
            "finished_at": last_success,
            "last_success_at": last_success,
        },
        now=now,
    )

    assert status["status"] == "green"
    assert status["status_reason"] == "healthy"
    assert status["stale"] is False
    assert status["freshness_due_at"] == datetime(2026, 9, 2, 6, tzinfo=UTC)


def test_source_health_fails_closed_for_stale_or_failed_runs():
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    stale_success = datetime(2026, 8, 20, 6, tzinfo=UTC)
    stale = _apply_run_health(
        _get_source_status(_Cursor({"cnt": 100}), "zoning", "staging.zoning"),
        job_name="arcgis_refresh",
        max_age_hours=8 * 24,
        run={
            "job_name": "arcgis_refresh",
            "status": "success",
            "started_at": stale_success,
            "finished_at": stale_success,
            "last_success_at": stale_success,
        },
        now=now,
    )
    failed = _apply_run_health(
        _get_source_status(_Cursor({"cnt": 100}), "zoning", "staging.zoning"),
        job_name="arcgis_refresh",
        max_age_hours=8 * 24,
        run={
            "job_name": "arcgis_refresh",
            "status": "failure",
            "started_at": datetime(2026, 8, 30, 10, tzinfo=UTC),
            "finished_at": datetime(2026, 8, 30, 11, tzinfo=UTC),
            "last_success_at": datetime(2026, 8, 29, 6, tzinfo=UTC),
        },
        now=now,
    )

    assert (stale["status"], stale["status_reason"], stale["stale"]) == (
        "red",
        "stale",
        True,
    )
    assert (failed["status"], failed["status_reason"], failed["stale"]) == (
        "red",
        "last_run_failed",
        False,
    )


def test_source_health_fails_closed_before_any_run_is_observed():
    status = _apply_run_health(
        _get_source_status(_Cursor({"cnt": 100}), "zoning", "staging.zoning"),
        job_name="arcgis_refresh",
        max_age_hours=8 * 24,
        run=None,
        now=datetime(2026, 8, 30, 12, tzinfo=UTC),
    )

    assert status["status"] == "red"
    assert status["status_reason"] == "run_not_observed"
    assert status["last_run_status"] == "unknown"


def test_targeted_recovery_can_supersede_an_older_grouped_run():
    older = datetime(2026, 8, 30, 10, tzinfo=UTC)
    newer = datetime(2026, 8, 30, 11, tzinfo=UTC)
    runs = {
        "scraper_refresh": {
            "job_name": "scraper_refresh",
            "status": "failure",
            "started_at": older,
            "finished_at": older,
            "last_success_at": None,
        },
        "proceedings_refresh": {
            "job_name": "proceedings_refresh",
            "status": "success",
            "started_at": newer,
            "finished_at": newer,
            "last_success_at": newer,
        },
    }

    latest = _latest_job_run(runs, "scraper_refresh", "proceedings_refresh")

    assert latest is not None
    assert latest["job_name"] == "proceedings_refresh"


def test_recent_run_does_not_erase_source_specific_failure_reason():
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    status = _apply_run_health(
        {
            "status": "red",
            "status_reason": "source_unhealthy",
            "record_count": 0,
        },
        job_name="scraper_refresh",
        max_age_hours=8 * 24,
        run={
            "job_name": "scraper_refresh",
            "status": "success",
            "started_at": now,
            "finished_at": now,
            "last_success_at": now,
        },
        now=now,
    )

    assert status["status_reason"] == "source_unhealthy"


def test_integrity_health_warns_for_new_unresolved_contradiction():
    now = datetime(2026, 8, 31, 12, tzinfo=UTC)
    cursor = _Cursor(
        {
            "history_count": 4,
            "accepted_count": 3,
            "quarantined_count": 1,
            "human_resolution_inference_count": 0,
            "contradiction_count": 1,
            "unresolved_contradiction_count": 1,
            "resolved_contradiction_count": 0,
            "oldest_unresolved_at": datetime(2026, 8, 31, 11, tzinfo=UTC),
            "projection_count": 3,
            "unlinked_projection_count": 0,
            "projection_mismatch_count": 0,
        }
    )

    status = _get_intelligence_integrity_status(
        cursor, now=now, max_age_hours=72
    )

    assert status["status"] == "yellow"
    assert status["status_reason"] == "unresolved_contradictions"
    assert status["unresolved_contradiction_count"] == 1


def test_integrity_health_fails_for_projection_mismatch_before_queue_age():
    now = datetime(2026, 8, 31, 12, tzinfo=UTC)
    cursor = _Cursor(
        {
            "history_count": 2,
            "accepted_count": 1,
            "quarantined_count": 1,
            "human_resolution_inference_count": 0,
            "contradiction_count": 1,
            "unresolved_contradiction_count": 1,
            "resolved_contradiction_count": 0,
            "oldest_unresolved_at": now,
            "projection_count": 1,
            "unlinked_projection_count": 0,
            "projection_mismatch_count": 1,
        }
    )

    status = _get_intelligence_integrity_status(cursor, now=now)

    assert status["status"] == "red"
    assert status["status_reason"] == "projection_mismatch"


def test_integrity_health_warns_for_recent_validation_rejection():
    rejected_at = datetime(2026, 8, 31, 11, tzinfo=UTC)
    cursor = _Cursor(
        {
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
            "rejection_count": 2,
            "rejections_last_24h": 1,
            "latest_rejection_at": rejected_at,
        }
    )

    status = _get_intelligence_integrity_status(
        cursor, now=datetime(2026, 8, 31, 12, tzinfo=UTC)
    )

    assert status["status"] == "yellow"
    assert status["status_reason"] == "recent_validation_rejections"
    assert status["validation_rejection_count"] == 2
    assert status["latest_validation_rejection_at"] == rejected_at
