"""Dagster sensors that post run outcomes to Slack.

- Success → #pipeline-runs
- Failure → #alerts-critical
"""

from dagster import (
    RunFailureSensorContext,
    RunStatusSensorContext,
    DagsterRunStatus,
    run_failure_sensor,
    run_status_sensor,
)

from countyiq.lib.slack import send_slack_message


@run_status_sensor(run_status=DagsterRunStatus.SUCCESS)
def success_reporter(context: RunStatusSensorContext) -> None:
    """Post successful run summary to #pipeline-runs."""
    run = context.dagster_run
    duration = (run.end_time - run.start_time) if run.end_time and run.start_time else 0
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    send_slack_message(
        channel="pipeline",
        text=f":white_check_mark: *{run.job_name}* completed in {minutes}m {seconds}s",
        emoji=":white_check_mark:",
    )


@run_failure_sensor
def failure_alerter(context: RunFailureSensorContext) -> None:
    """Post a failed run to #alerts-critical."""
    run = context.dagster_run
    error = (
        context.failure_event.message[:200]
        if context.failure_event
        else "Unknown error"
    )

    send_slack_message(
        channel="critical",
        text=f":x: *{run.job_name}* failed.\n```{error}```",
        emoji=":rotating_light:",
    )
