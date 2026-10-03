"""Read-only probes executed in the existing application containers.

Only aggregate operational values leave the container. No record payloads,
customer identifiers, exception messages, prompts, or environment values do.
"""

from __future__ import annotations

import json
import sys

SOURCE_REASONS = frozenset(
    {
        "healthy",
        "empty_source",
        "missing_table",
        "query_failed",
        "run_not_observed",
        "last_run_failed",
        "stale",
        "source_unhealthy",
        "policy_overdue",
    }
)
REFRESH_JOBS = frozenset(
    {
        "arcgis_refresh",
        "radar_refresh",
        "scraper_refresh",
        "proceedings_refresh",
        "bulk_refresh",
        "pa_dos_refresh",
        "fema_refresh",
    }
)


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
            reason = source.get("status_reason")
            job = source.get("last_run_job") or source.get("refresh_job")
            if not job:
                job = "none"
            elif job not in REFRESH_JOBS:
                job = "unknown"
            sources[name] = {
                "healthy": source["status"] == "green",
                "stale": bool(source.get("stale", False)),
                "records": source.get("record_count"),
                "reason": reason if reason in SOURCE_REASONS else "unknown",
                "refresh_job": job,
                "last_success": last_success.timestamp() if last_success else 0,
            }
        return {
            "sources": sources,
            "integrity_healthy": health["intelligence_integrity"]["status"] == "green",
        }
    finally:
        database.close_pool()


if __name__ == "__main__":
    probes = {"sources": source_health}
    print(json.dumps(probes[sys.argv[1]]()))
