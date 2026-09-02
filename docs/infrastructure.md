# Infrastructure

## Current Direction

CountyIQ's current infrastructure direction is:

- Cloudflare in front for DNS, CDN, TLS, and WAF
- Cloudflare R2 for raw archives and object storage
- a single Ubuntu VPS running Docker Compose
- Caddy for reverse proxy
- FastAPI, Dagster, and PostgreSQL/PostGIS as containers

Provider: **Hetzner, confirmed 2026-08-02** (CX23 now; CX33 at 3-county scale; Netcup is the fallback if Hetzner raises prices again). Hostinger was evaluated and rejected — see `docs/cost.md` for the verified comparison.

## Runtime Topology

| Layer | Current expectation |
|---|---|
| Front door | Cloudflare |
| Frontend | Cloudflare Pages preferred |
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
| `caddy` | reverse proxy and TLS termination |

## Required Environment

Production expects a root `.env` file with:

```bash
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_NAME=countyiq
DATABASE_USER=dagster_admin
DATABASE_PASSWORD=...
DATABASE_URL=postgresql://dagster_admin:...@postgres:5432/countyiq
DATABASE_PIPELINE_USER=countyiq_pipeline
DATABASE_PIPELINE_PASSWORD=...
DATABASE_API_USER=countyiq_api
DATABASE_API_PASSWORD=...

OPENROUTER_API_KEY=...
# Optional public search uses a separate, restricted provider key.
COUNTYIQ_SEARCH_API_KEY=
# Optional overrides; leave unset to use the evaluated defaults in
# pipelines/countyiq/lib/pass_llm_config.py.
COUNTYIQ_PASS0_MODEL=
COUNTYIQ_PASS1_MODEL=
COUNTYIQ_PASS2_MODEL=
COUNTYIQ_PASS3_MODEL=
COUNTYIQ_PASS4_MODEL=
COUNTYIQ_OPENROUTER_MODEL=
COUNTYIQ_SEARCH_MODEL=
COUNTYIQ_THINKING=true
COUNTYIQ_ARCHIVE_DIR=/opt/countyiq/archives
COUNTYIQ_ARCHIVE_STRICT=true
COUNTYIQ_TRUSTED_HOSTS=api.example.com
COUNTYIQ_EXPOSE_API_DOCS=false

R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_ENDPOINT_URL=https://ACCOUNT_ID.r2.cloudflarestorage.com
S3_RAW_BUCKET=countyiq-raw
COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID=...
COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY=...
COUNTYIQ_BACKUP_R2_BUCKET=countyiq-backups
COUNTYIQ_BACKUP_BUCKET_LOCK_CONFIRMED=true
COUNTYIQ_RESTORE_DRILL_MAX_AGE_DAYS=120
```

Notes:

- Passes 0-4 prefer `COUNTYIQ_PASS{N}_MODEL`, then the evaluated code
  default, then `COUNTYIQ_OPENROUTER_MODEL`.
- Search can use `COUNTYIQ_SEARCH_MODEL`, then its dedicated low-cost model
  pool. It does not inherit the offline pipeline model.
- `COUNTYIQ_THINKING` is only the global fallback; pass-specific overrides are supported.
- The API container receives neither the administrator database credential nor
  pipeline/R2/Slack credentials. `03-api-role.sh` creates and refreshes its
  read-only grants after migrations.
- Scheduled Dagster containers receive an allowlist of pipeline settings—not
  the complete `.env`—and use a non-superuser writer created by
  `02-runtime-role.sh`. Only the short-lived `migrate` service and host backup
  job use the database administrator credential.
- Dagster's R2 credential is scoped to raw archives. The separate host-only
  backup credential is scoped to the private database-backup bucket and is
  never injected into an application container.

## Access Model

- Public traffic should only reach Cloudflare and Caddy.
- Postgres and Dagster should stay private to the host and SSH tunnels.
- SSH key auth only.
- Restrict origin HTTP(S) firewall rules to Cloudflare's published networks;
  direct origin access bypasses edge WAF controls even though Caddy still
  rejects spoofed proxy headers.
- API and pipeline containers run as UID 10001 with dropped capabilities;
  Postgres is isolated on an internal network and Caddy cannot reach it.
- API, pipeline, and Caddy internet egress use separate bridge networks, so
  outbound access does not also create a shared lateral-movement network.
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
This is operationally repeatable, but it is not bit-for-bit artifact promotion:
a future registry/signing boundary becomes worthwhile if multiple hosts or
frequent releases make on-host builds inadequate. Cloudflare Pages deployment
remains separate and is not automated by this repository.
