"""Dagster sensors that post run outcomes to Slack.

- Success → #pipeline-runs
- Failure → #alerts-critical

Both outcomes are also written to ``meta.job_run_status`` so the read-only API
can report freshness and failures without access to Dagster's database.
"""

import json
import logging
import os
from datetime import UTC, datetime, timedelta

from dagster import (
    DagsterRunStatus,
    DefaultSensorStatus,
    RunFailureSensorContext,
    RunStatusSensorContext,
    SensorEvaluationContext,
    SkipReason,
    run_failure_sensor,
    run_status_sensor,
    sensor,
)

from countyiq.lib.job_run_status import RunOutcome, record_job_run_status
from countyiq.lib.slack import send_slack_message
from countyiq.resources.database import DatabaseResource

logger = logging.getLogger(__name__)


def _integrity_alert(database, *, now: datetime) -> tuple[str, str, dict]:
    """Return severity, message, and stable cursor state for integrity health."""

    rows = (
        database.execute(
            """
        SELECT unresolved_contradiction_count, oldest_unresolved_at,
               unlinked_projection_count, projection_mismatch_count,
               rejection_count, rejections_last_24h, latest_rejection_at
        FROM meta.intelligence_integrity_status
        CROSS JOIN meta.intelligence_validation_rejection_status
        """
        )
        or []
    )
    if not rows:
        state = {"severity": "critical", "reason": "status_unavailable"}
        return "critical", "Intelligence integrity status is unavailable.", state
    row = rows[0]
    if isinstance(row, dict):
        unresolved = int(row.get("unresolved_contradiction_count") or 0)
        oldest = row.get("oldest_unresolved_at")
        unlinked = int(row.get("unlinked_projection_count") or 0)
        mismatched = int(row.get("projection_mismatch_count") or 0)
        rejection_count = int(row.get("rejection_count") or 0)
        recent_rejections = int(row.get("rejections_last_24h") or 0)
        latest_rejection = row.get("latest_rejection_at")
    else:
        (
            unresolved,
            oldest,
            unlinked,
            mismatched,
            rejection_count,
            recent_rejections,
            latest_rejection,
        ) = row
        unresolved = int(unresolved or 0)
        unlinked = int(unlinked or 0)
        mismatched = int(mismatched or 0)
        rejection_count = int(rejection_count or 0)
        recent_rejections = int(recent_rejections or 0)

    max_age_hours = max(
        int(os.environ.get("COUNTYIQ_CONTRADICTION_MAX_AGE_HOURS", "72")), 1
    )
    stale = bool(oldest and now > oldest + timedelta(hours=max_age_hours))
    if mismatched:
        severity, reason = "critical", "projection_mismatch"
        message = f"Intelligence integrity has {mismatched} projection mismatch(es)."
    elif unlinked:
        severity, reason = "critical", "projection_unlinked"
        message = f"Intelligence integrity has {unlinked} unlinked projection row(s)."
    elif stale:
        severity, reason = "critical", "stale_contradictions"
        message = (
            f"{unresolved} intelligence contradiction(s) remain unresolved beyond "
            f"{max_age_hours} hours."
        )
    elif unresolved:
        severity, reason = "warning", "unresolved_contradictions"
        message = f"{unresolved} intelligence contradiction(s) await human review."
    elif recent_rejections:
        severity, reason = "warning", "recent_validation_rejections"
        message = (
            f"{recent_rejections} invalid intelligence output(s) were rejected "
            "by deterministic gates in the last 24 hours."
        )
    else:
        severity, reason = "healthy", "healthy"
        message = "Intelligence integrity is healthy."
    state = {
        "severity": severity,
        "reason": reason,
        "unresolved": unresolved,
        "oldest": oldest.isoformat() if oldest else None,
        "unlinked": unlinked,
        "mismatched": mismatched,
        "rejections": rejection_count,
        "recent_rejections": recent_rejections,
        "latest_rejection": (
            latest_rejection.isoformat() if latest_rejection else None
        ),
    }
    return severity, message, state


def _timestamp(value: float | None) -> datetime | None:
    return datetime.fromtimestamp(value, tz=UTC) if value is not None else None


def _record_outcome(
    context: RunStatusSensorContext | RunFailureSensorContext,
    database: DatabaseResource,
    status: RunOutcome,
    error_message: str | None = None,
) -> tuple[datetime | None, datetime]:
    run = context.dagster_run
    try:
        run_record = context.instance.get_run_record_by_id(run.run_id)
    except Exception:
        logger.exception("Could not read Dagster run timing for %s", run.run_id)
        run_record = None
    started_at = _timestamp(run_record.start_time) if run_record else None
    finished_at = (
        _timestamp(run_record.end_time) if run_record and run_record.end_time else None
    ) or datetime.now(UTC)
    try:
        record_job_run_status(
            database,
            job_name=run.job_name,
            run_id=run.run_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            error_message=error_message,
        )
    except Exception:
        # The application database may be the reason a run failed. Preserve the
        # pre-existing Slack alert path and let health remain conservatively red.
        logger.exception("Could not persist run outcome for %s", run.run_id)
    return started_at, finished_at


@run_status_sensor(
    run_status=DagsterRunStatus.SUCCESS,
    default_status=DefaultSensorStatus.RUNNING,
)
def success_reporter(
    context: RunStatusSensorContext,
    database: DatabaseResource,
) -> None:
    """Post successful run summary to #pipeline-runs."""
    run = context.dagster_run
    started_at, finished_at = _record_outcome(context, database, "success")
    duration = (finished_at - started_at).total_seconds() if started_at else 0
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    send_slack_message(
        channel="pipeline",
        text=f":white_check_mark: *{run.job_name}* completed in {minutes}m {seconds}s",
        emoji=":white_check_mark:",
    )


@run_failure_sensor(default_status=DefaultSensorStatus.RUNNING)
def failure_alerter(
    context: RunFailureSensorContext,
    database: DatabaseResource,
) -> None:
    """Post a failed run to #alerts-critical."""
    run = context.dagster_run
    error = (
        context.failure_event.message[:200]
        if context.failure_event
        else "Unknown error"
    )
    _record_outcome(context, database, "failure", error)

    send_slack_message(
        channel="critical",
        text=f":x: *{run.job_name}* failed.\n```{error}```",
        emoji=":rotating_light:",
    )


@sensor(
    minimum_interval_seconds=300,
    default_status=DefaultSensorStatus.RUNNING,
)
def intelligence_integrity_guard(
    context: SensorEvaluationContext,
    database: DatabaseResource,
) -> SkipReason:
    """Alert only when the aggregate integrity state changes."""

    try:
        severity, message, state = _integrity_alert(database, now=datetime.now(UTC))
    except Exception:
        logger.exception("Could not read intelligence integrity status")
        severity = "critical"
        message = "Intelligence integrity status query failed."
        state = {"severity": severity, "reason": "query_failed"}

    cursor = json.dumps(state, sort_keys=True)
    if context.cursor == cursor:
        return SkipReason("Intelligence integrity state is unchanged")
    previous = json.loads(context.cursor) if context.cursor else None
    context.update_cursor(cursor)

    if severity == "critical":
        send_slack_message(
            channel="critical",
            text=f":rotating_light: *Intelligence integrity:* {message}",
            emoji=":rotating_light:",
        )
    elif severity == "warning":
        send_slack_message(
            channel="warning",
            text=f":warning: *Intelligence integrity:* {message}",
            emoji=":warning:",
        )
    elif previous and previous.get("severity") != "healthy":
        send_slack_message(
            channel="pipeline",
            text=":white_check_mark: *Intelligence integrity recovered.*",
            emoji=":white_check_mark:",
        )
    return SkipReason(message)
