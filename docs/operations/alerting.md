# Run outcomes and alerts

In the local-pipeline release, `scripts/run_pipeline.py` executes explicit
Dagster jobs on the PC. `countyiq.run_job` waits for completion and writes job
and per-asset source outcomes to the application health ledgers before
returning a JSON report. Failed asset checks fail that report. Full events and
compute logs remain under the PC's `DAGSTER_HOME`.

There are no registered Dagster success, failure, or integrity sensors and no
pipeline webhook notification process. A nonzero command result requires
inspection of the retained local run. If receipt publication alone failed,
the wrapper's `--report-run` mode republishes a finished run from the same
state directory without another acquisition. See
[Local pipeline commands](local-pipelines.md).

Grafana retains host, container, PostgreSQL, backup, source freshness,
intelligence-integrity, cost-guard, and external-readiness alerts. The new
catalog has 19 rules and seven collectors; it requires collector deployment
and Grafana provisioning before those changes are live. Host backup and
cost-guard notifications remain separate operational paths. See
[Monitoring](monitoring.md) for routing, installation, and acceptance checks.

Source freshness remains meaningful when runs are manual. A successful host
probe does not establish current source coverage, and an unrelated successful
asset cannot clear a failed source. Inspect application health alongside the
job report before closing an alert. Individual HTTP clients retain their
bounded retries; a failed job does not imply an unlimited or global retry
policy.
