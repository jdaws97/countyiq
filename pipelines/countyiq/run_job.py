"""Execute a local Dagster job and publish its health receipts before exiting."""

from __future__ import annotations

import argparse
import json
import os
from uuid import uuid4

from dagster import AssetKey, DagsterInstance, RunsFilter, execute_job, reconstructable

from countyiq.lib.run_reporting import record_run_outcome
from countyiq.resources.database import make_database_resource


def selected_job():
    """A reconstructable public Dagster entry point for subprocess execution."""
    from countyiq.definitions import defs

    return defs.resolve_job_def(os.environ["COUNTYIQ_LOCAL_JOB"])


def run(arguments) -> int:
    with (
        DagsterInstance.get() as instance,
        make_database_resource().process_config_and_initialize_cm() as database,
    ):
        if arguments.report_run:
            report = record_run_outcome(instance, database, arguments.report_run)
            print(json.dumps(report), flush=True)
            return 0 if report["status"] == "success" else 1
        os.environ["COUNTYIQ_LOCAL_JOB"] = arguments.job
        definition = selected_job()
        selection = [AssetKey(name) for name in arguments.assets] or None
        available = definition.asset_layer.executable_asset_keys
        if selection and not set(selection).issubset(available):
            raise ValueError("Selected assets must belong to the requested job")
        if not available:
            raise ValueError("This job has no configured assets in the selected county")
        execution_id = uuid4().hex
        tags = {
            "countyiq/executor": "local-cli",
            "countyiq/execution_id": execution_id,
        }
        try:
            with execute_job(
                reconstructable(selected_job),
                instance=instance,
                asset_selection=selection,
                tags=tags,
                raise_on_error=False,
            ):
                pass
        finally:
            runs = instance.get_runs(filters=RunsFilter(tags=tags), limit=2)
            if len(runs) == 1:
                run_record = runs[0]
                if not run_record.is_finished:
                    instance.report_run_failed(run_record)
                report = record_run_outcome(instance, database, run_record.run_id)
                print(json.dumps(report), flush=True)
        if len(runs) != 1:
            raise RuntimeError("Execution did not leave exactly one durable run record")
        return 0 if report["status"] == "success" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--job")
    target.add_argument("--report-run")
    parser.add_argument("--assets", nargs="+", default=[])
    arguments = parser.parse_args()
    if arguments.report_run and arguments.assets:
        parser.error("--assets applies only to a job execution")
    try:
        return run(arguments)
    except Exception:  # noqa: BLE001 — sanitize resource/connection exceptions at the CLI boundary.
        # Dagster retains detailed local logs. Never copy a connection exception
        # or a credentials-bearing resource configuration into command output.
        print(
            "Pipeline execution/reporting failed; inspect the local Dagster run history.",
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
