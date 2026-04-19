# Open Items

This is the working backlog for the repo as it exists now, not the original MVP build sheet.

## Highest Priority

Driven by the RE investor/developer lane — see `docs/products/real-estate-intelligence.md`.

| Item | Status | Notes |
|---|---|---|
| Surface cross-signal insight + linked proceedings on property page | In progress | Phase A, this branch. Data already exists in `meta.intelligence_passes` and `staging.proceeding_extractions`. |
| County feed page (`/feed`) over Pass 4 narratives | In progress | Phase A, this branch. |
| Entity profile page (`/entity/:id`) over `public.entity_graph` | Designed | Phase A, next plan. The moat — must ship before outreach. |
| Clerk auth + watchlists + alerts + weekly email | Blocked | Phase B. The retention loop. Blocked on auth decision and SMTP vendor. |
| 10 investor interviews for price discovery | Not started | Phase C. Target YBA, PA REIA local chapter. |
| Finalize VPS provider | Open | Hostinger is the current preferred option to evaluate. Hetzner remains the historical baseline. |
| Resolve legacy infra path | Done | The AWS/Terraform tree has been moved to `archives/infrastructure/aws-terraform/` so it no longer competes with the active VPS docs. |
| Sweep remaining stale docs | In progress | The core source-of-truth docs are being consolidated, but older deep docs still need a second pass for terminology cleanup. |
| Tighten `.env` / deployment defaults | Open | Make the production model lineup, archive path, and host expectations explicit in deploy scripts and ops docs. |
| `COUNTYIQ_ARCHIVE_DIR` volume-mounted in production | Open | Archives are currently lost on container restart unless the env var is set and the path is mounted. |

## Intelligence Platform

| Item | Status | Notes |
|---|---|---|
| Evaluate Qwen 3.5 against current passes | Open | Current working defaults are Grok 4.1 Fast for Pass 0 and MiMo V2 Flash for Passes 1-4. Qwen remains worth re-testing. |
| Decide per-pass production model policy | Open | Keep "one model for all later passes" vs per-pass specialization under explicit operator control. |
| Harden archive retention strategy | Open | Runtime archives currently exist, but retention and cleanup policy should be standardized. |
| Verify pass docs against code | Open | Pass 0-4 are live in code; deeper docs should match actual env vars and current job wiring. |

## Product And Pipeline Hardening

| Item | Status | Notes |
|---|---|---|
| CORS lockdown | Open | Replace `allow_origins=["*"]` once the final production domains are known. |
| Reconcile schedules docs with actual jobs | Open | Jobs and schedules evolved significantly; docs still lag in a few places. |
| Verify flaky / changing public sources | Open | Sheriff sales, recorder flows, and other fragile sources still need ongoing live verification. |
| Revisit AWS/Lambda leftovers in code | In progress | The dead Lambda adapter is gone and the Terraform stack is archived; keep trimming any remaining stale references in executable code. |

## Repository Cleanup

| Item | Status | Notes |
|---|---|---|
| Remove generated artifacts from version control | In progress | Playwright screenshots/logs and ad hoc screenshots should stay out of git. |
| Decide fate of root Playwright-only package files | Open | The repo root has a minimal Node package used for tooling; keep only if still needed. |
| Standardize archive locations | Open | Historical docs and runtime archives should stay clearly separated. |
