# Local pipeline commands

The release runs CountyIQ pipelines on the operator PC. The VPS retains
PostgreSQL, the API, Caddy, and cloudflared; migrations use a separate one-shot
image. This page describes the new executable model. Confirm the deployed
commit in `/var/lib/countyiq/releases/current.env` before using it against an
existing host.

## Prepare the PC

Use a clean checkout of the exact deployed commit and the locked environment:

```bash
uv sync --project pipelines --locked --extra dev
cd pipelines
```

The production wrapper requires a verified SSH host key, an explicit identity
file, and operator access to run the protected session helper through
`sudo -n`. Keep the PC online for the whole command. No daemon, webserver,
schedule, or background sensor is needed.

By default `scripts/run_pipeline.py` creates a private state directory at
`~/.local/state/countyiq/pipeline`:

| Path                             | Contents                                                                     |
| -------------------------------- | ---------------------------------------------------------------------------- |
| `dagster/`                       | `DAGSTER_HOME`: SQLite run/event history, materializations, and compute logs |
| `archives/`                      | Model request/response archives                                              |
| `intelligence/`, `subscription/` | Persistent backfill state                                                    |
| `tmp/`                           | Temporary pipeline files                                                     |
| `run.lock`                       | Excludes overlapping commands using this state directory                     |

Use `--state-dir /absolute/path` to choose another location. Keep it outside
Git and back it up separately; daily VPS database backups do not contain PC
state. The runner copies this release's `pipelines/dagster.yaml` into the
Dagster home and refuses a conflicting existing configuration.

## Refresh production sources

Run a named job, or select assets that belong to that job:

```bash
.venv/bin/python scripts/run_pipeline.py \
  --ssh-target ubuntu@YOUR_HOST --identity-file /absolute/path/to/ssh-key \
  --job arcgis_refresh \
  --assets penndot_roads_arcgis penndot_projects_arcgis traffic_counts_arcgis

.venv/bin/python scripts/run_pipeline.py \
  --ssh-target ubuntu@YOUR_HOST --identity-file /absolute/path/to/ssh-key \
  --job radar_refresh --assets pa_dep_environmental_diligence

.venv/bin/python scripts/run_pipeline.py \
  --ssh-target ubuntu@YOUR_HOST --identity-file /absolute/path/to/ssh-key \
  --job bulk_refresh --assets tax_claims
```

Other source jobs include `scraper_refresh`, `proceedings_refresh`,
`pa_dos_refresh`, and `fema_refresh`. The job registry in
`countyiq/jobs/__init__.py` defines selections; county configuration controls
which optional source assets are present. Omitting `--assets` runs the whole
named job. After the required sources succeed, rebuild deterministic outputs:

```bash
.venv/bin/python scripts/run_pipeline.py \
  --ssh-target ubuntu@YOUR_HOST --identity-file /absolute/path/to/ssh-key \
  --job deterministic_enrichment_refresh
```

Source acquisition happens directly on the PC. Authorization, raw-retention
and derived-use checks run before source requests. R2 archives remain strict;
parser, count, geometry, and SCD2 protections remain in the owning assets.
The protected production session forces Passes 0–4 off, including when an
inherited local environment would otherwise enable them.

## Protected writer session

The runner rejects a dirty checkout or a commit that differs from the active
VPS release. `docker/pipeline_session.py` holds
`/var/lock/countyiq-deploy.lock` for the command, excluding deployment,
restore, cleanup, and other protected pipeline sessions. It checks the cost
stop before starting and during heartbeats.

The helper enables the separate writer role for this session and lends only
the required database/source settings in memory. The PC connects through a
temporary PC loopback SSH tunnel to the database container's private address.
The address is checked again under the deployment lock before execution.
It does not download the production environment
file. On exit, interruption, lost heartbeat, or a cost stop, the wrapper stops
local child processes and the helper restores writer `NOLOGIN`, terminates
writer connections, and releases the host lock. Do not bypass this wrapper
with saved production database credentials.

## Run history and health receipts

`countyiq.run_job` executes the job against the persistent local Dagster
instance, then synchronously records the job outcome and source outcomes in
the application health ledgers. Failed asset checks produce a failed report.
The command emits a JSON report with its run ID and returns nonzero for a
failed execution or report; inspect the local event and compute logs for detail.

If execution finished but receipt publication failed, keep the same state
directory and retry reporting the durable run instead of fetching again:

```bash
.venv/bin/python scripts/run_pipeline.py \
  --ssh-target ubuntu@YOUR_HOST --identity-file /absolute/path/to/ssh-key \
  --report-run <local-dagster-run-id>
```

This requires a finished run in that PC's Dagster history. Compare the report
with `/api/ops/health`, `meta.job_run_status`, and source freshness before
declaring a recovery complete. A job that did not execute an asset cannot
supply that asset's successful refresh receipt.

## Native scripts and local development

The same session wrapper accepts only these named script modes:

| `--script`               | Script                             |
| ------------------------ | ---------------------------------- |
| `subscription-backfill`  | `subscription_backfill.py`         |
| `rebind-subscription`    | `rebind_subscription_reads.py`     |
| `intelligence-preflight` | `verify_intelligence_preflight.py` |
| `estimate-backfill`      | `estimate_llm_backfill.py`         |
| `emerging-intelligence`  | `emerging_intelligence.py`         |

Place native script arguments after `--`. For example:

```bash
.venv/bin/python scripts/run_pipeline.py \
  --ssh-target ubuntu@YOUR_HOST --identity-file /absolute/path/to/ssh-key \
  --script subscription-backfill -- \
  read --directory /absolute/path/to/subscription-artifacts --limit 16
```

Native scripts preserve their own bounded authoring and validation behavior.
They do not create a Dagster job receipt; run the appropriate deterministic
job afterward to rebuild serving projections. See
[subscription backfill](subscription-backfill.md) for selectors, retained
artifacts, and partial-result handling.

For a development database, set explicit local `DATABASE_*` variables and use
`--local` in place of the SSH options:

```bash
DATABASE_PORT=5433 .venv/bin/python scripts/run_pipeline.py \
  --local --job deterministic_enrichment_refresh
```

`--local` uses the caller's environment and does not acquire a VPS writer
session. Keep production and test databases distinct; integration tests belong
on a disposable database.
