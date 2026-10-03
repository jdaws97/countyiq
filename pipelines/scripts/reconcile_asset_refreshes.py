"""Replay retained Dagster receipts into source health, without rerunning assets.

The default is a read-only preview. --apply writes only the derived application
health ledger; it never changes staging records or source acquisition settings.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime, timedelta

from dagster import DagsterInstance, DagsterRunStatus, RunsFilter

from countyiq.lib.asset_refresh_status import (
    collect_asset_refresh_outcomes,
    record_asset_refresh_outcome,
)
from countyiq.resources.database import make_database_resource


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=45)
    parser.add_argument("--max-runs", type=int, default=500)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    if not 1 <= arguments.days <= 90 or not 1 <= arguments.max_runs <= 2000:
        parser.error("days must be 1–90 and max-runs must be 1–2000")

    since = datetime.now(UTC) - timedelta(days=arguments.days)
    with DagsterInstance.get() as instance:
        runs = instance.get_runs(
            filters=RunsFilter(
                statuses=[DagsterRunStatus.SUCCESS, DagsterRunStatus.FAILURE],
                updated_after=since,
            ),
            limit=arguments.max_runs + 1,
        )
        if len(runs) > arguments.max_runs:
            raise RuntimeError("Run limit exceeded; narrow the history window")
        receipts = [
            (run, outcome)
            for run in runs
            for outcome in collect_asset_refresh_outcomes(instance, run)
        ]

    counts = Counter((item.asset_key, item.status) for _, item in receipts)
    print(f"Read {len(runs)} completed runs and {len(receipts)} source receipts")
    for (asset_key, status), count in sorted(counts.items()):
        print(f"{asset_key}: {count} {status} receipt(s)")
    if not arguments.apply:
        print("Preview only; no application records changed")
        return

    database = make_database_resource()
    database.setup_for_execution(None)
    try:
        for run, outcome in sorted(receipts, key=lambda item: item[1].finished_at):
            record_asset_refresh_outcome(database, run=run, outcome=outcome)
    finally:
        database.teardown_after_execution(None)
    print(f"Applied {len(receipts)} source receipts; replay is idempotent")


if __name__ == "__main__":
    main()
