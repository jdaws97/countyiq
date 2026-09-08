# Infrastructure

This page describes repository configuration. See
[Account workspaces](operations/account-workspaces.md#guarded-hostname-rollout)
for hostname rollout status and steps, and [Infrastructure cost](cost.md) for
provider and sizing decisions.

## Runtime Topology

| Layer | Repository configuration |
|---|---|
| Front door | Cloudflare TLS/WAF, Access for app testers, and Tunnel |
| Frontend | Separate marketing and app HTML entries served by Caddy on the VPS |
| API | FastAPI behind Caddy on the VPS |
| Pipelines | Dagster on the VPS |
| Database | PostgreSQL 16 + PostGIS on the VPS |
| Raw archive store | Cloudflare R2 |
| LLM backend | OpenRouter |

## Container Services

The production Compose stack in `docker/docker-compose.yml` is the current deployment reference:

| Service | Purpose |
|---|---|
| `postgres` | application database + PostGIS |
| `api` | FastAPI/Uvicorn |
| `dagster-webserver` | Dagster UI and GraphQL API |
| `dagster-daemon` | Schedule/sensor evaluation and run execution |
| `caddy` | frontend files and API proxy on private port 8080 |
| `cloudflared` | outbound Tunnel connector; public TLS terminates at Cloudflare |

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
- Scheduled Dagster containers receive an allowlist of pipeline settings—not
  the complete environment file—and use a non-superuser writer created by
  `02-runtime-role.sh`. Only the short-lived `migrate` service and host backup
  job use the database administrator credential.
- Dagster's R2 credential is scoped to raw archives. The separate host-only
  backup credential is scoped to the private database-backup bucket and is
  never injected into an application container.

## Access Model

- Public traffic reaches Cloudflare; its outbound Tunnel connector reaches
  Caddy over the internal edge network. No origin HTTP(S) port is published.
- Cloudflare Access covers the whole app host. The API also verifies customer
  identity; production preflight rejects disabled authentication. Marketing
  cannot proxy API requests.
- Postgres and Dagster stay private; use SSH tunnels for operator access.
- SSH key auth only.
- API and pipeline containers run as UID 10001 with dropped capabilities;
  Postgres is isolated on an internal network and Caddy cannot reach it.
- API, pipeline, and Tunnel internet egress use separate bridge networks.
  Caddy joins only the internal proxy and edge networks.
- External runtime images and Dockerfile bases are pinned by digest; Dependabot
  proposes reviewed digest updates rather than silently changing a deployment.
- Container JSON logs rotate at 10 MiB with five files per service. Commit-tagged
  images are retained for reviewed rollback, so operators still monitor
  `docker system df` and prune only after release receipts and rollback needs
  have been reviewed.

## Backups And Archives

- PostgreSQL backups: unique custom-format `pg_dump` sets in private R2 storage
- raw pipeline archives: Cloudflare R2
- LLM output archives: `COUNTYIQ_ARCHIVE_DIR`

The archives are operational artifacts, not core repo content. They should not be committed to git.
Each database dump is validated locally, uploaded with a SHA-256 sidecar,
download-checked against R2, and made eligible for restore only when a manifest
is uploaded and read back last. Uploads are immutable and the host script has
no remote delete operation. R2 bucket-lock and lifecycle rules own protection
and expiry. A successful dump check is still not a restore test, so ordinary
deployments require a recent receipt from `docker/restore-drill.sh`.

## Delivery

Operator monitoring and private Dagster browser access are configured in
`infra/monitoring/` and `infra/cloudflare/`. See
[Monitoring](operations/monitoring.md) for installation, account connection,
zero-cost limits, and the live acceptance checks.

GitHub Actions verifies the locked pipeline and API environments, architecture
contracts, pipeline definition import, unit and contract tests, frontend type,
lint and production build, Compose configuration, and the deployment preflight.
It does not publish images or deploy either runtime.

VPS release initiation remains manual, but execution is scripted and
fail-closed. The operator checks out an exact reviewed SHA and runs
`docker/deploy.sh`; the script builds SHA-tagged images locally, stops writers,
requires a remotely verified pre-deploy backup, applies Alembic, refreshes
runtime grants, checks readiness, persists the active image tag, and writes an
immutable release receipt.
Both frontend entries ship in the same web image. Cloudflare DNS, Tunnel, and
Access changes are managed separately in `infra/cloudflare/`; building the web
image does not apply them.
