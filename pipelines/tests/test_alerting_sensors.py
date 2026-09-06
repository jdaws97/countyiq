"""Regression tests for the Dagster run-outcome sensor boundary."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from countyiq.sensors.alerting import _integrity_alert, _record_outcome


def test_record_outcome_reads_timestamps_from_run_record() -> None:
    run = SimpleNamespace(job_name="arcgis_refresh", run_id="run-123")
    run_record = SimpleNamespace(start_time=1_777_555_200.0, end_time=1_777_555_260.0)
    instance = Mock()
    instance.get_run_record_by_id.return_value = run_record
    context = SimpleNamespace(dagster_run=run, instance=instance)
    database = Mock()

    started_at, finished_at = _record_outcome(context, database, "success")

    instance.get_run_record_by_id.assert_called_once_with("run-123")
    assert started_at.timestamp() == run_record.start_time
    assert finished_at.timestamp() == run_record.end_time
    params = database.execute.call_args.args[1]
    assert params == {
        "job_name": "arcgis_refresh",
        "run_id": "run-123",
        "status": "success",
        "started_at": started_at,
        "finished_at": finished_at,
        "error_message": None,
    }


def test_record_outcome_is_best_effort_when_application_database_is_down() -> None:
    run = SimpleNamespace(job_name="scraper_refresh", run_id="failed-run")
    instance = Mock()
    instance.get_run_record_by_id.return_value = None
    context = SimpleNamespace(dagster_run=run, instance=instance)
    database = Mock()
    database.execute.side_effect = RuntimeError("database unavailable")

    started_at, finished_at = _record_outcome(
        context,
        database,
        "failure",
        "source fetch failed",
    )

    assert started_at is None
    assert finished_at is not None
    database.execute.assert_called_once()


def test_integrity_alert_prioritizes_projection_mismatch() -> None:
    database = Mock()
    database.execute.return_value = [
        {
            "unresolved_contradiction_count": 2,
            "oldest_unresolved_at": datetime(2026, 8, 31, 11, tzinfo=UTC),
            "unlinked_projection_count": 0,
            "projection_mismatch_count": 1,
        }
    ]

    severity, message, state = _integrity_alert(
        database, now=datetime(2026, 8, 31, 12, tzinfo=UTC)
    )

    assert severity == "critical"
    assert "projection mismatch" in message
    assert state["reason"] == "projection_mismatch"


def test_integrity_alert_warns_for_fresh_review_queue() -> None:
    database = Mock()
    database.execute.return_value = [
        {
            "unresolved_contradiction_count": 1,
            "oldest_unresolved_at": datetime(2026, 8, 31, 11, tzinfo=UTC),
            "unlinked_projection_count": 0,
            "projection_mismatch_count": 0,
        }
    ]

    severity, message, state = _integrity_alert(
        database, now=datetime(2026, 8, 31, 12, tzinfo=UTC)
    )

    assert severity == "warning"
    assert "await human review" in message
    assert state["unresolved"] == 1


def test_integrity_alert_warns_for_recent_validation_rejection() -> None:
    rejected_at = datetime(2026, 8, 31, 11, tzinfo=UTC)
    database = Mock()
    database.execute.return_value = [
        {
            "unresolved_contradiction_count": 0,
            "oldest_unresolved_at": None,
            "unlinked_projection_count": 0,
            "projection_mismatch_count": 0,
            "rejection_count": 3,
            "rejections_last_24h": 1,
            "latest_rejection_at": rejected_at,
        }
    ]

    severity, message, state = _integrity_alert(
        database, now=datetime(2026, 8, 31, 12, tzinfo=UTC)
    )

    assert severity == "warning"
    assert "deterministic gates" in message
    assert state["reason"] == "recent_validation_rejections"
    assert state["latest_rejection"] == rejected_at.isoformat()
