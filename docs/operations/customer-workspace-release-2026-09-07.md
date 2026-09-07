# Customer workspace release — September 7, 2026

This release packages the customer workspace redesign and its read-serving
contracts. The user authorized VPS deployment in the redesign conversation.

## Scope

- Shared navigation, overview, activity investigation, mapped property views,
  source reader, comparison links, directories, and mobile/print behavior.
- Matching API presenters, public-reference search, source-aware feed and watch
  serving, and property source explanations.
- Migrations 067–069: accepted evidence/explanation types and live serving views.
- The durable customer-experience contract and frontend architecture update.

The release is built in an isolated checkout from the existing main commit.
Unrelated ingestion, model harness, prompt, OCR and benchmark work is excluded.
Pipeline producers and schedules retain the previously deployed implementation.
No local inference history or demonstration records are imported. Therefore live
coverage and explanations reflect the VPS's existing accepted data; the local
screenshots are not a promise that those same records already exist in production.
Paid passes and backfill remain disabled.

## Verification and rollout

Frontend tests, TypeScript, lint and production build pass. API unit and database
contract tests cover serving through the real read-only role. The 066-to-069
upgrade was rehearsed in a separate local test database. New serving tests verify
that a changed source bundle retracts a property explanation. Dagster definitions
import successfully from the release checkout.

Use `docker/deploy.sh` with the exact release commit. Its normal production
sequence takes and remotely verifies a rollback backup, quiesces writers, applies
migrations, refreshes runtime grants, replaces images, verifies internal and
Access-authenticated readiness, and writes an immutable release receipt.

The receipt in `/var/lib/countyiq/releases/current.env` is authoritative for the
live commit, backup and schema. Retain the previous images and backup. A code-only
rollback keeps the additive schema and uses the existing reviewed runbook; do not
run an automatic database downgrade.
