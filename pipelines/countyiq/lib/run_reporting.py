"""Persist local Dagster outcomes in the application's source-health ledgers."""

from __future__ import annotations

from datetime import UTC, datetime

from dagster import DagsterEventType, DagsterRunStatus

from countyiq.lib.asset_refresh_status import (
    ASSET_COUNT_FIELDS,
    AssetRefreshOutcome,
    collect_asset_refresh_outcomes,
    record_asset_refresh_outcome,
)
from countyiq.lib.job_run_status import record_job_run_status


def run_checks(instance, run_id: str) -> list[dict]:
    """Retain the final evaluation of each check without copying source payloads."""
    checks = {}
    cursor = None
    for _ in range(20):
        page = instance.get_records_for_run(
            run_id,
            cursor=cursor,
            of_type={
                DagsterEventType.ASSET_CHECK_EVALUATION_PLANNED,
                DagsterEventType.ASSET_CHECK_EVALUATION,
            },
            limit=500,
            ascending=True,
        )
        for record in page.records:
            entry = record.event_log_entry
            check = entry.dagster_event.event_specific_data
            asset = check.asset_key.to_user_string()
            evaluated = (
                entry.dagster_event.event_type
                == DagsterEventType.ASSET_CHECK_EVALUATION
            )
            checks[(asset, check.check_name)] = {
                "asset": asset,
                "name": check.check_name,
                "passed": check.passed if evaluated else False,
                "severity": check.severity.value if evaluated else "ERROR",
                "evaluated": evaluated,
                "finished_at": datetime.fromtimestamp(entry.timestamp, UTC),
            }
        if not page.has_more:
            return list(checks.values())
        if page.cursor == cursor:
            raise RuntimeError("Asset-check pagination did not advance")
        cursor = page.cursor
    raise RuntimeError("Asset-check report exceeded its event limit")


def record_run_outcome(instance, database, run_id: str) -> dict:
    """Fail visibly if reporting fails; the persistent local run can be replayed."""
    record = instance.get_run_record_by_id(run_id)
    if record is None:
        raise ValueError("Run is absent from this PC's Dagster history")
    run = record.dagster_run
    if not run.is_finished:
        raise ValueError("Cannot report a run that is still active")
    finished_at = (
        datetime.fromtimestamp(record.end_time, UTC)
        if record.end_time is not None
        else datetime.now(UTC)
    )
    started_at = (
        datetime.fromtimestamp(record.start_time, UTC)
        if record.start_time is not None
        else None
    )
    checks = run_checks(instance, run_id)
    failures = [check for check in checks if not check["passed"]]
    outcomes = collect_asset_refresh_outcomes(instance, run)
    failed_assets = {check["asset"] for check in failures}
    for outcome in outcomes:
        if outcome.asset_key not in failed_assets:
            record_asset_refresh_outcome(database, run=run, outcome=outcome)
    for check in failures:
        if check["asset"] in ASSET_COUNT_FIELDS:
            record_asset_refresh_outcome(
                database,
                run=run,
                outcome=AssetRefreshOutcome(
                    asset_key=check["asset"],
                    finished_at=finished_at,
                    status="failure",
                    failure_reason="unverified_result",
                ),
            )
    success = (
        run.status == DagsterRunStatus.SUCCESS
        and not failures
        and all(outcome.status == "success" for outcome in outcomes)
    )
    record_job_run_status(
        database,
        job_name=run.job_name,
        run_id=run_id,
        status="success" if success else "failure",
        started_at=started_at,
        finished_at=finished_at,
        error_message=None
        if success
        else "Local run, source receipt or asset check failed.",
    )
    instance.add_run_tags(run_id, {"countyiq/reported": "true"})
    return {
        "run_id": run_id,
        "job": run.job_name,
        "status": "success" if success else "failure",
        "source_outcomes": len(outcomes),
        "checks": [
            {key: value for key, value in check.items() if key != "finished_at"}
            for check in checks
        ],
    }
