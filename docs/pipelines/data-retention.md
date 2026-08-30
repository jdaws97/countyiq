# Data Retention and Archives

This document describes current behavior, not a promise to retain everything
forever. Retention for source evidence, database history, model transcripts,
backups, and operational logs is different.

## Raw Source Evidence

Ingestion assets that call `S3StorageResource` archive payloads to the
S3-compatible bucket configured by `R2_ENDPOINT_URL` and `S3_RAW_BUCKET`.
Keys use `<source>/<UTC date>/<filename>`. A repeated run using the same source,
date, and filename replaces that day's object; this is daily evidence, not an
immutable per-run ledger.

Not every asset has a raw upstream payload. Derived enrichment assets rebuild
from Postgres and do not write source snapshots to R2. The asset implementation
is authoritative about whether a source is archived.

Every governed archive call must pass the source's `raw_retention` policy
before writing. A public URL or successful download does not authorize a raw
copy. Conditional municipal documents also require their per-body retention
policy; unknown, paused, mismatched, or overdue policies fail before storage.
The source and municipal decision ledgers are append-only audit evidence, not
copies of the upstream payload.

`COUNTYIQ_ARCHIVE_STRICT` defaults to false for local development. Set it to
true in production so an R2 upload failure fails the asset instead of leaving
an unarchived successful materialization. R2 lifecycle and object-versioning
rules are infrastructure settings outside this repository and must be checked
in the Cloudflare account.

## PostgreSQL History

Mutable source tables generally use `valid_from`/`valid_to` SCD2 versions.
Loaders expire changed or source-removed current rows and insert a new version;
they include partial-fetch guards to avoid mass expiration. Some serving tables
and event ledgers are derived and rebuildable instead of append-only evidence.

Migrations and asset code define table behavior. Do not infer SCD2 or perpetual
retention for a table solely because it lives in `staging` or `public`.
No general historical-row purge job currently exists.

## Model Request and Response Archives

The LLM harness stores prompts, raw responses, model metadata, and keys under
`COUNTYIQ_ARCHIVE_DIR`. Production mounts `/opt/countyiq/archives`, and the
backup script copies that tree to the `countyiq-backups/intelligence-archives`
R2 prefix. These files can contain owner names, parcel context, and source text.

`COUNTYIQ_LLM_ARCHIVE_RETENTION_DAYS` defaults to 90. The harness prunes only
its recognized `<label>/<UTC date>/<hash>_<timestamp>.json` files, at most once
per process day, and leaves unrelated files untouched. The daily backup script
applies the same limit to the persistent host tree and the dedicated R2 prefix,
so copying an archive does not turn it into indefinite history. Setting the
value to `0` disables expiry and is reserved for an explicitly approved legal
hold or incident investigation; it should not be the normal production value.

The production Compose file bind-mounts `../archives` at
`/opt/countyiq/archives` for both Dagster services. Restrict that host path and
R2 prefix to pipeline operators, do not commit archives, and do not treat these
raw transcripts as a customer-facing export or permanent evidence ledger.

## Backups and Logs

`docker/backup.sh` creates daily custom-format dumps of both `countyiq` and
`dagster`, uploads them to R2, removes database dumps older than 30 days, and
enforces the configured LLM-archive retention locally and in R2. Backup restore
is currently a manual check.

Docker log retention and R2 lifecycle policy are not configured by this repo,
so no fixed seven-day or forever claim is made for them. Operators must inspect
the host's Docker logging configuration and Cloudflare lifecycle rules.
