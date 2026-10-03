# Dagster runtime

This release executes Dagster on the operator PC through
`pipelines/scripts/run_pipeline.py`. The VPS hosts the application and primary
database; its Compose graph has no Dagster service. A release receipt, not this
document, establishes whether an existing host has completed the transition.

## Execution and configuration

`countyiq/definitions.py` loads assets, checks, jobs, and resources. Jobs are
explicit selections in `countyiq/jobs/__init__.py`; county configuration omits
unsupported source capabilities. There are no registered schedules or sensors.
The command chooses a named job and, optionally, assets belonging to that job.

`countyiq.run_job` uses Dagster's reconstructable job API and waits for
completion. The default multiprocess executor limits independent asset steps
to one at a time. Bounded I/O concurrency inside an asset remains available.
The wrapper also excludes overlapping commands sharing its local state
directory, while production sessions share the VPS deployment lock.

See [Local pipeline commands](../operations/local-pipelines.md) for setup,
production and development invocations, asset subsets, and native script modes.

## Durable local state

The default state root is `~/.local/state/countyiq/pipeline`; `--state-dir`
changes it. The wrapper creates private directories and sets:

- `DAGSTER_HOME` to `<state>/dagster`, using Dagster's local SQLite storage for
  run/event history and its local compute logs;
- `COUNTYIQ_ARCHIVE_DIR` to `<state>/archives`;
- `COUNTYIQ_BACKFILL_STATE_DIR` to `<state>/intelligence`;
- `COUNTYIQ_SUBSCRIPTION_STATE_DIR` to `<state>/subscription`; and
- `TMPDIR` to `<state>/tmp`.

`pipelines/dagster.yaml` disables telemetry. The wrapper copies that file into
the local Dagster home and rejects conflicting existing contents. It does not
configure PostgreSQL Dagster storage or a queued daemon launcher.

Source archives still go to the governed R2 bucket. Local run state and model
artifacts need separate operator preservation; VPS backups contain only the
primary application database. Any old server-side Dagster state retained at
cutover is historical evidence, not an active storage backend.

## Health reporting

The job runner waits for completion and writes `meta.job_run_status` and
per-asset source outcomes synchronously through `lib/run_reporting.py`.
Failed asset checks cause a failed report even if Dagster finished the job.
Full events stay local; the API reads only the compact application ledgers.

A report failure exits nonzero. Keep the local Dagster history and retry
`run_pipeline.py --report-run <run-id>` using the same state directory and
the appropriate connection options. This republishes a finished run's health
receipts without rerunning source acquisition.

## Production connection

The SSH wrapper requires a clean checkout matching the active release. The VPS
helper holds `/var/lock/countyiq-deploy.lock`, checks the cost-stop latch,
lends allowlisted settings in memory, and enables the separate writer role
only for that session. Heartbeats maintain the lease. Cleanup restores
`NOLOGIN` and terminates writer connections before releasing the lock.

Production sessions disable inference Passes 0–4. Source and deterministic
jobs therefore retain the existing no-inference boundary. Native subscription
authoring uses the wrapper's named `--script` modes and its separate validation
and artifact workflow.
