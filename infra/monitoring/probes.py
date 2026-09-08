"""Read-only probes executed in the existing application containers.

Only aggregate operational values leave the container. No record payloads,
customer identifiers, exception messages, prompts, or environment values do.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta


def source_health() -> dict:
    from api.lib import database

    original_kwargs = database._connection_kwargs

    def read_only_kwargs():
        kwargs = original_kwargs()
        kwargs["options"] = (
            "-c jit=off -c default_transaction_read_only=on -c statement_timeout=8000"
        )
        return kwargs

    # This is an isolated probe process, not the serving API process.
    database._connection_kwargs = read_only_kwargs
    from api.routes.ops import _compute_health

    try:
        health = _compute_health()
        sources = {}
        for name, source in health["sources"].items():
            last_success = source.get("last_success_at")
            sources[name] = {
                "healthy": source["status"] == "green",
                "stale": bool(source.get("stale", False)),
                "records": source.get("count"),
                "last_success": last_success.timestamp() if last_success else 0,
            }
        return {
            "sources": sources,
            "integrity_healthy": health["intelligence_integrity"]["status"] == "green",
        }
    finally:
        database.close_pool()


def dagster_health() -> dict:
    from dagster import DagsterInstance, DagsterRunStatus, RunsFilter

    now = datetime.now(UTC)
    with DagsterInstance.get() as instance:
        heartbeats = instance.get_daemon_heartbeats()
        daemons = {}
        for name in instance.get_required_daemon_types():
            heartbeat = heartbeats.get(name)
            daemons[name] = {
                "timestamp": heartbeat.timestamp if heartbeat else 0,
                "errors": len(heartbeat.errors or []) if heartbeat else 0,
            }
        runs = {}
        for status in (
            DagsterRunStatus.QUEUED,
            DagsterRunStatus.STARTING,
            DagsterRunStatus.STARTED,
        ):
            filters = RunsFilter(statuses=[status])
            oldest = instance.get_run_records(filters, limit=1, ascending=True)
            age = 0
            if oldest:
                created = oldest[0].create_timestamp
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                age = max(0, (now - created).total_seconds())
            runs[status.value] = {
                "count": instance.get_runs_count(filters),
                "oldest_seconds": age,
            }
        failures = instance.get_runs_count(
            RunsFilter(
                statuses=[DagsterRunStatus.FAILURE],
                updated_after=now - timedelta(hours=24),
            )
        )
    return {"daemons": daemons, "runs": runs, "failures_24h": failures}


if __name__ == "__main__":
    probes = {"sources": source_health, "dagster": dagster_health}
    print(json.dumps(probes[sys.argv[1]]()))
