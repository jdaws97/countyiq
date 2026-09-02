from __future__ import annotations

from datetime import UTC, datetime

from countyiq.lib.job_run_status import record_job_run_status


class _Database:
    def __init__(self) -> None:
        self.sql = ""
        self.params: dict = {}

    def execute(self, sql: str, params=None):
        self.sql = sql
        self.params = params or {}


def test_job_run_status_upsert_preserves_success_and_latest_completion():
    database = _Database()
    finished_at = datetime(2026, 8, 30, 11, tzinfo=UTC)

    record_job_run_status(
        database,
        job_name="arcgis_refresh",
        run_id="run-123",
        status="failure",
        started_at=datetime(2026, 8, 30, 10, tzinfo=UTC),
        finished_at=finished_at,
        error_message="network timeout",
    )

    assert "ON CONFLICT (job_name) DO UPDATE" in database.sql
    assert "last_success_at" in database.sql
    assert database.params == {
        "job_name": "arcgis_refresh",
        "run_id": "run-123",
        "status": "failure",
        "started_at": datetime(2026, 8, 30, 10, tzinfo=UTC),
        "finished_at": finished_at,
        "error_message": "network timeout",
    }
