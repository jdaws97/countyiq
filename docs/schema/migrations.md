# Schema Migrations

Alembic is the sole authority for application table, index, view, function,
and constraint changes. The ordered chain lives in
`pipelines/alembic/versions/`; `alembic_version` records the deployed revision.

Revision 066 adds shared read-only functions for parcel-center zoning selection
and soil coverage. Reports and deterministic signals use the same newest-adoption
zoning rule and combine matching soil fragments by geometric union, retaining
all source IDs. It changes no source records. After deploying the corresponding
code, rebuild `development_signals` and `development_momentum` from existing
staging data to replace cached facts; these two assets make no LLM calls.

## Rules

- Never edit a migration that may already have run. Add a new revision.
- Write explicit `upgrade()` and `downgrade()` behavior and review the emitted
  SQL for locks, destructive changes, and data conversion risk.
- Do not run migrations from API startup or Dagster module import. Deployment
  applies them explicitly before code that depends on the new schema is used.
- Test the complete chain against the dedicated PostGIS test database. Never
  point destructive tests at development or production data.
- An LLM may help draft or review a migration, but generated DDL is not an
  acceptance oracle. The author owns the schema design and database test.

## Local Chain Check

The dedicated Compose file is `pipelines/docker-compose.yml` and exposes
`postgres-test` on port 5433:

```bash
cd pipelines
docker compose up -d postgres-test

DATABASE_URL=postgresql://dagster_admin:localtest@localhost:5433/countyiq \
  .venv/bin/alembic upgrade head

.venv/bin/alembic current
.venv/bin/alembic history
```

The container runs the ordered scripts under `pipelines/init-db/` on a new test
volume before Alembic. Use `docker compose down -v` only for an intentional
reset of that specific test volume.

Contract tests create their own `countyiq_test` database and apply the full
migration chain. The exact command is maintained in
`docs/operations/testing.md`.

Use Alembic heads to inspect the current repository head and Alembic current
to inspect the connected database; the historical notes below are not a deployed
revision assertion. Revision 031 adds executable source-rights
policy and audit tables, four site-readiness staging families, and the serving
score column; it also expires the two paused York project-service layers and
clears rebuildable score rows. Revision 032 adds per-municipal-body rights,
append-only decision receipts, collection-health state, use-specific
authorization, and a paused County Scout policy. Its 122 municipal policies
cover all 72 municipalities. Revision 033 adds exact origin allowlists and
pauses Rep'd-, Google Drive-, and explicit-robots-backed municipal paths.
Revision 034 records reviewed same-organization redirect/document origins and
pauses three GoDaddy-CDN-only paths. The resulting registry has 110 conditional
and 12 paused municipal policies. Revision 035 is a forward reconciliation for
databases that applied revision 032 before the County Scout seed was added; it
restores the explicit paused policy so upgraded and fresh databases converge.
Revision 036 adds immutable policy snapshots/fingerprints, county policy scope,
the governed PA DEP source, and `staging.environmental_diligence_sites` for
portable deterministic parcel screening. Revision 037 adds the bounded
`meta.job_run_status` projection used by application health; Dagster retains
the full run history in its separate database. Revision 038 adds append-only
LLM inference history, contradiction and resolution ledgers, and
`active_inference_id` provenance links on the five model-backed serving or
staging projections.

Revision 039 closes PostgreSQL's statement-level `TRUNCATE` path on all three
append-only intelligence audit tables.

Revision 040 adds atomic human contradiction resolution, resolution provenance,
and the aggregate integrity-health view. Existing model-backed rows with no
`active_inference_id` are copied into immutable history as
`legacy_unverified` and retracted from serving; source tables and accepted
history are untouched. This data retraction is intentionally fail-closed and
is not automatically reversed by `downgrade()`.

Revision 041 adds the append-only
`meta.intelligence_validation_rejections` ledger and its 24-hour aggregate
status view. Deterministic evidence, identity-membership, and citation gate
failures are now durable operator evidence rather than log-only events.

Revision 042 records explicit product-owner risk acceptance for the three
official municipal listings that deliver documents through GoDaddy. It enables
Franklintown Borough, Newberry Township, and Washington Township collection,
allowlists only the exact `https://img1.wsimg.com` document origin, retains raw
archives privately, and at that revision kept person-level display and raw
export disabled. Revision 054 later removes the person-display switch.

Revision 043 records a source-row-scoped exception for the nonresponsive robots
endpoints on those same three official listing origins. It does not allow an
explicit disallow and does not extend to the GoDaddy PDF CDN, whose live robots
policy remains mandatory.

Revision 044 adds the trigram expression index used by mapped-address search.
Revision 045 removes the unused County Scout runtime and its empty registry
tables and policy row. The migration aborts if Scout data or policy audit
receipts exist so retirement cannot silently delete evidence.

Revision 046 records PA DOS refresh timestamps. Revision 047 adds the
rule-first contradiction auto-resolution and sampled-review audit ledgers.
Revision 048 adds radar history, normalized address matching, and Pass 2
configuration fingerprints. Revision 049 distinguishes refused automatic
resolutions in the review queue. Revision 050 closes the TRUNCATE path on the
new audit ledgers and provides a forward-safe downgrade bridge for revision
049's outcome normalization.
Revisions 051 and 052 refresh municipal proceedings listing URLs (including
the York Township Board of Commissioners source). Revision 053 adds
`public.normalize_parcel_reference`, the single rule every proceeding-to-parcel
linker uses: York PIDNs are alphanumeric, so the earlier digit-only comparison
could never link a minute that cited such a parcel by PIDN. Revision 054 drops
`person_level_display_allowed` from both source-rights tables: owner names are
public record and are served under `derived_product_allowed`.

## Production

Production runs migrations only through the release orchestrator, inside the
commit-tagged Dagster image that contains the lockfile and Alembic
configuration:

```bash
cd /opt/countyiq/docker
sudo env COUNTYIQ_DEPLOY_REF=<reviewed-40-character-commit-sha> \
  COUNTYIQ_ENV_FILE=/opt/countyiq/.env ./deploy.sh
```

The orchestrator stops API and Dagster, verifies their database sessions are
gone, creates and remotely verifies the pre-deploy backup, and only then runs
the chain. Once migration execution starts, any failure leaves application
services stopped for reviewed recovery—even if `alembic_version` did not
advance. Rollback is not assumed safe merely because `downgrade()` exists;
data loss, partial application, and PostgreSQL locks are reviewed per revision.

## Creating a Revision

```bash
cd pipelines
.venv/bin/alembic revision -m "short description"
```

Use the next repository naming convention, set `down_revision` to the current
head, and add a focused migration or contract test when behavior can regress.

## Proceedings metadata review (058)

Revision 058 adds staging.public_proceedings.metadata_quality and an append-only
meta.proceeding_metadata_reviews ledger, and pauses the additional wrong-jurisdiction
Jackson/Windsor source policies. The separately invoked review_proceeding_metadata
command performs reviewed SCD2 repairs; schema migration alone does not repair or
release historical records. See the [cleanup report](../research/municipal-source-cleanup-2026-09-04.md)
for the dry-run/apply workflow and local verification.

Revision 059 adds caller-permission SQL functions for parcel brief source context
and its SHA-256 fingerprint. Generation and API serving use the same database
definition for property/entity facts, resolved owner names, portfolio membership
and totals. Upgrade changes no source data; downgrade removes only these
functions and must be paired with compatible application code.

Revision 061 adds extraction_details to proceeding extractions, a shared
proceeding_parcel_matches resolver for explicit IDs and unique municipality-scoped
addresses, and persistent proceeding_project_aliases. Street-only, ranged and
ambiguous addresses abstain. Source text and historical inference payloads are
unchanged. Runtime and human-resolution projection writers preserve the new
contract; deploy the migration before the matching application code. Downgrade
removes the new contract projection and alias table and must be paired with
compatible code; existing project watches must be reviewed before discarding aliases.

### 062 — parcel geography proximity index

Adds idx_parcels_current_geography, a partial GiST expression index on
staging.parcels (geom::geography), restricted to current rows with geometry.
Supports meter-based nearby parcel and event searches after removing the
inaccurate degree envelope. The transactional index build can block writes;
measure it on a representative restore and schedule deployment accordingly.
Downgrade removes only this index.

### Schema-test isolation

Run pipelines/tests/test_schema_integration.py against a clean migrated
countyiq_test database. API integration fixtures add a synthetic municipality
policy and change Hanover's jurisdiction for synthetic parcel matching, so a
database already seeded by api/tests is not migration seed state. Use a separate
Compose project/port for schema checks; do not reset a populated local database
or relax exact migration assertions to accommodate API fixtures. Set
DATABASE_PORT and DATABASE_NAME=countyiq_test explicitly for the schema suite.
The 2026-09-04 review verified a fresh 001 -> 062 chain and all 23 schema checks
on a separate localhost:5435 instance.

### 083 — emerging evidence query performance

Adds a current-row GiST geography index for planning proximity and narrows
property municipal-evidence reads to inference IDs linked to the requested PIDN.
The existing final relationship, current-source, and rights predicates remain
in force. The migration changes no packet fields or retained reviews. Its index
build runs during the ordinary quiesced deployment window; downgrade restores
the original predicate and drops only the added index.

The isolated full-data rehearsal preserved all four scope hashes, all 20 property
packets, and all 13 current analysis IDs. Individual scope reconstruction fell
from 2.30/3.40/2.96/0.40 seconds to 0.50/0.61/0.60/0.41 seconds; the full current
analysis query fell from 12.46 to 5.67 seconds. These are local measurements,
not a production latency guarantee. Upgrade/downgrade packet equality was also
verified in a rolled-back transaction.

### 084 — shared current inputs for emerging cases

Materializes the live municipal scope inputs once for the current published
analyses, then passes those typed rows to copies of the canonical source
builders. Full source equality, publication selection, policy dates, and source
rights remain live in the request's database snapshot. This is query-local
reuse; no retained cache or asynchronous refresh is introduced.

The isolated rehearsal returned the same four scope packets and 13 current
analysis IDs. Full-feed source validation fell from 5.67 seconds with migration
083 to 0.61 seconds with 084. The original single-scope builder remains the
producer contract. Downgrade restores the original serving function calls and
removes only the two helper functions. Future changes to the scoped-input view's
row type or canonical source builders must update the typed helpers as well.

### 085 — environmental geography proximity index

Adds a current-row GiST index matching the geography expression used by
meter-based environmental context reads. The existing geometry index does not
support that expression. It changes no query predicates or retained data.
The isolated rehearsal preserved all four full source packets and reduced
the shared current-analysis query from 0.61 to 0.28 seconds. Downgrade drops
only this index; the build uses the ordinary quiesced deployment window.

### 063 — scoped municipal event types

Expands chk_intelligence_events_type to accept policy_action, recommendation,
withdrawn, removed and scoped_decision, matching current event builders and API
filters. Apply before publishing events from the new extraction contract.
Existing events are not rewritten. Downgrade validates the older type set and
refuses while any newer types remain; it does not delete or relabel events.

### 086 — indexed emerging case candidates

Adds a rebuildable summary index for the latest accepted analysis in each scope.
History and publication triggers maintain it in the same writer transaction;
concurrent decisions for a scope serialize their projection. A newer unpublished
analysis supersedes an older publication, while an action on an older analysis
cannot change the latest publication state. The index retains no source packet
or evidence excerpts. Its search, parcel, commercial, and ordering
indexes support filtering before a bounded candidate page is selected.

An index entry is not proof of source currentness. The API still compares every
selected inference's source against the canonical builder, including current
rights and policy dates, before serving any summary or detail. Pagination never
requires that check for the entire collection. The existing full current views
remain available for audit and compatibility. Rebuilding the projection is not
executable by the read-only API role. Downgrade removes only these rebuildable
objects and requires the preceding API version; immutable reviews and publication
actions remain intact.
