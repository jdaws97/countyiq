"""Persist Dagster job outcomes in the application database.

Dagster's own run history lives in a separate database that the read-only API
cannot access.  This module keeps only the latest outcome per job, plus the
latest successful completion, so the product health endpoint can fail closed
for stale or failed source refreshes without duplicating Dagster's event log.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from countyiq.resources.database import DatabaseResource

RunOutcome = Literal["success", "failure"]


def record_job_run_status(
    database: DatabaseResource,
    *,
    job_name: str,
    run_id: str,
    status: RunOutcome,
    started_at: datetime | None,
    finished_at: datetime,
    error_message: str | None = None,
) -> None:
    """Upsert the latest completion and preserve the newest successful run."""

    database.execute(
        """
        INSERT INTO meta.job_run_status (
            job_name, run_id, status, started_at, finished_at,
            last_success_at, error_message
        ) VALUES (
            %(job_name)s, %(run_id)s, %(status)s, %(started_at)s, %(finished_at)s,
            CASE WHEN %(status)s = 'success' THEN %(finished_at)s END,
            %(error_message)s
        )
        ON CONFLICT (job_name) DO UPDATE SET
            run_id = CASE
                WHEN EXCLUDED.finished_at >= meta.job_run_status.finished_at
                    THEN EXCLUDED.run_id
                ELSE meta.job_run_status.run_id
            END,
            status = CASE
                WHEN EXCLUDED.finished_at >= meta.job_run_status.finished_at
                    THEN EXCLUDED.status
                ELSE meta.job_run_status.status
            END,
            started_at = CASE
                WHEN EXCLUDED.finished_at >= meta.job_run_status.finished_at
                    THEN EXCLUDED.started_at
                ELSE meta.job_run_status.started_at
            END,
            finished_at = GREATEST(
                meta.job_run_status.finished_at,
                EXCLUDED.finished_at
            ),
            last_success_at = CASE
                WHEN EXCLUDED.status = 'success' THEN GREATEST(
                    meta.job_run_status.last_success_at,
                    EXCLUDED.finished_at
                )
                ELSE meta.job_run_status.last_success_at
            END,
            error_message = CASE
                WHEN EXCLUDED.finished_at >= meta.job_run_status.finished_at
                    THEN EXCLUDED.error_message
                ELSE meta.job_run_status.error_message
            END,
            updated_at = NOW()
        """,
        {
            "job_name": job_name,
            "run_id": run_id,
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "error_message": error_message,
        },
    )
