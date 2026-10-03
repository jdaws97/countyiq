# Infrastructure

This page describes repository configuration. See
[Account workspaces](operations/account-workspaces.md#guarded-hostname-rollout)
for hostname rollout status and steps, and [Infrastructure cost](cost.md) for
provider and sizing decisions.

## Runtime Topology

| Layer             | Repository configuration                                                      |
| ----------------- | ----------------------------------------------------------------------------- |
| Front door        | Cloudflare TLS/WAF, Access for app testers, and Tunnel                        |
| Frontend          | Separate marketing and app HTML entries served by Caddy on the VPS            |
| API               | FastAPI behind Caddy on the VPS                                               |
| Pipelines         | Explicit local Dagster CLI jobs on the operator PC                            |
| Database          | PostgreSQL 16 + PostGIS on the VPS                                            |
| Raw archive store | Cloudflare R2                                                                 |
| LLM backend       | Explicitly enabled OpenRouter or supported native subscription work on the PC |

## Container Services

The release configuration in `docker/docker-compose.yml` has four persistent
services and a one-shot migration tool. The release receipt is authoritative
about whether this configuration is deployed.

| Service       | Purpose                                                            |
| ------------- | ------------------------------------------------------------------ |
| `postgres`    | application database + PostGIS                                     |
| `api`         | FastAPI/Uvicorn                                                    |
| `caddy`       | frontend files and API proxy on private port 8080                  |
| `cloudflared` | outbound Tunnel connector; public TLS terminates at Cloudflare     |
| `migrate`     | one-shot Alembic image, run only during reviewed schema operations |

The PC stores SQLite run history and logs beneath
`~/.local/state/countyiq/pipeline/dagster`. There are no deployed Dagster
schedules, sensors, daemon, or webserver. Jobs and asset subsets are invoked
through [the local runner](operations/local-pipelines.md), which writes health
receipts synchronously before returning.

## Required Environment

Production reads the root-owned /etc/countyiq/production.env (or
COUNTYIQ_ENV_FILE), published by docker/publish-production-env.sh.

- [Production secrets](../infra/secrets/README.md) owns environment creation,
  editing, and publication.
- [Production preflight](../docker/lib/operations.sh) defines required settings;
  [Compose](../docker/docker-compose.yml) defines each service's environment.
- [Account configuration](operations/account-workspaces.md#runtime-configuration)
  owns app-host identity settings and their rollout order.
- [LLM configuration](../pipelines/countyiq/lib/pass_llm_config.py) owns model
  defaults and overrides.

Credential boundaries:

- The API container receives neither the administrator database credential nor
  pipeline/R2/Slack credentials. `03-api-role.sh` creates and refreshes its
  source-data read grants and scoped account/workspace write grants after
  migrations.
- A protected SSH session lends an allowlist of pipeline settings and the
  non-superuser writer credential to the PC in memory. It requires a clean
  checkout matching the deployed commit, holds the host deployment lock, and
  enables writer `LOGIN` only for the session. Cleanup restores `NOLOGIN` and
  terminates writer connections. Production source sessions disable every
  inference pass. Only the short-lived `migrate` service and host administrative
  operations use the database administrator credential.
- The pipeline's R2 credential is scoped to raw archives. The separate host-only
  backup credential is scoped to the private database-backup bucket and is
  never injected into an application container.

## Access Model

- Public traffic reaches Cloudflare; its outbound Tunnel connector reaches
  Caddy over the internal edge network. No origin HTTP(S) port is published.
- Cloudflare Access covers the whole app host. The API also verifies customer
  identity; production preflight rejects disabled authentication. Marketing
  cannot proxy API requests.
- Postgres stays on the internal Docker network without a published host port.
  The runner forwards a temporary PC loopback port to its private container
  address and verifies that address again under the deployment lock.
- SSH key auth only.
- API and migration containers run as UID 10001 with dropped capabilities;
  Postgres is isolated on an internal network and Caddy cannot reach it.
- API and Tunnel internet egress use separate bridge networks.
  Caddy joins only the internal proxy and edge networks.
- External runtime images and Dockerfile bases are pinned by digest; Dependabot
  proposes reviewed digest updates rather than silently changing a deployment.
- Container JSON logs rotate at 10 MiB with five files per service. Commit-tagged
  images for the current and previous release are retained for rollback. An
  hourly monitoring-host retention service removes older CountyIQ images after
  a one-hour grace period and trims unused build cache toward 4 GB. It verifies
  receipt identities, protects all container-referenced images, and shares the
  deployment lock. See [retention operations](operations/monitoring.md#docker-retention)
  for additional release pins and failure behavior.

## Backups And Archives

- PostgreSQL backups: daily custom-format `pg_dump` sets of the primary
  `countyiq` database in private R2 storage
- raw pipeline archives: Cloudflare R2
- LLM output archives: local `~/.local/state/countyiq/pipeline/archives` by default

The VPS backup does not include the PC's SQLite run history, logs, or authoring
artifacts. Operators must preserve those local directories separately. An older
Dagster database or volume retained during cutover is historical state, not a
dependency of the new runtime.

The archives are operational artifacts, not core repo content. They should not be committed to git.
Each database dump is validated locally, uploaded with a SHA-256 sidecar,
download-checked against R2, and made eligible for restore only when a manifest
is uploaded and read back last. Uploads are immutable and the host script has
no remote delete operation. R2 bucket-lock and lifecycle rules own protection
and expiry. A successful dump check is still not a restore test, so ordinary
deployments require a recent receipt from `docker/restore-drill.sh`.

## Delivery

Operator monitoring is configured in `infra/monitoring/`. See
[Monitoring](operations/monitoring.md) for installation, account connection,
zero-cost limits, and the live acceptance checks.

GitHub Actions verifies the locked pipeline and API environments, architecture
contracts, pipeline definition import, unit and contract tests, frontend type,
lint and production build, Compose configuration, and the deployment preflight.
It does not publish images or deploy either runtime.

VPS release initiation remains manual, but execution is scripted and
fail-closed. The operator checks out an exact reviewed SHA and runs
`docker/deploy.sh`; the script builds SHA-tagged images on the VPS, acquires the
same host lock as local pipeline sessions, stops application writers,
requires a remotely verified pre-deploy backup, applies Alembic, refreshes
runtime grants, checks readiness, persists the active image tag, and writes an
immutable release receipt.
Both frontend entries ship in the same web image. Cloudflare DNS, Tunnel, and
Access changes are managed separately in `infra/cloudflare/`; building the web
image does not apply them.
