# Loading performance release — September 7, 2026

Deployed at 8:19 p.m. Eastern, September 7 (2026-09-08 00:19:11 UTC), following
the user's authorization to make the slow Properties, map and municipality
surfaces faster.

## Production result

The live API connection reports `countyiq_api`, `jit=off`, and read-only
transactions. Measurements use the deployed API functions and their normal
connection pool against production data, without transaction-local tuning.

| Operation | Before | After, two samples |
| --- | ---: | ---: |
| Properties opportunity shortlist, 200 rows | 4,085–4,146 ms | 97 / 71 ms |
| Springettsbury activity feed, 6 rows | 5,959 ms | 27 / 16 ms |
| Map selection for large Warrington parcel `49000NF0093A0` | 3,362 ms, full report | 110 / 48 ms, summary |
| Springettsbury profile | 185 ms | 153 / 109 ms |

These are server-side samples, excluding browser, authentication and network
time. The summary's entire response equals the corresponding fields of the
complete production report. Detailed reports retain their soil coverage: the
same large parcel's full report took 3,053 ms and returned 29 soil units.

## Changes

- API connections disable PostgreSQL JIT compilation. Pipeline connection
  settings are unchanged.
- Map selection requests `/api/parcels/{pidn}/summary`, preserving displayed
  property facts and governed source explanations while skipping the report's
  direct soil calculation. Superseded map fetches are aborted on the client.
- Municipality profiles render before the recent-activity feed completes.
  Feed loading and failure are confined to that section.

The new map route shares the report's existing source policy, snapshot and
explanation freshness checks. It does not serve an unverified cached response.

## Verification

- Focused API checks: 17 passed, covering the pool, OpenAPI, spatial facts,
  summary/full-report parity, explanation revocation, API JIT setting and
  transaction snapshots.
- Wider API contracts, radar and role boundaries: 28 passed (including one
  previously executed connection check).
- Frontend: TypeScript, ESLint, production build and all 43 tests passed.
  Changed Python and frontend files passed their formatters.
- Existing live storage-guard compatibility: all 8 script tests passed,
  including Docker-isolated integration scenarios; shell syntax passed.
- Browser checks with local real data showed the municipality profile while
  its feed was deliberately held, confined a simulated feed failure to the
  activity section, and verified the map panel using only the new summary
  request. The map summary took 112 ms in the independently verified Firefox
  session. A combined scripted sequence lost its CLI browser session during
  map navigation; the map check was completed separately.

Browser captures:
[municipality while activity loads](../../output/playwright/loading-performance/municipality-feed-pending.png)
and [map summary](../../output/playwright/loading-performance/map-summary.png).

## Deployment receipt

- Release: `5d75207c9996c3eca06873b12293a76e2e759214`.
- Previous release: `7082d3f823920c4231b0695b8867c08d5c413b63`.
- Schema before and after: 069; no new migration.
- Verified rollback backup: `20260908T001736Z-pre-deploy-5d75207c9996`.
- Immutable receipt:
  `/var/lib/countyiq/releases/20260908T001911Z-5d75207c9996c3eca06873b12293a76e2e759214.env`.
- Isolated deployment checkout:
  `/opt/countyiq-loading-performance-20260907`.
- Local release branch: `codex/loading-performance` in
  `/home/jdaws/countyiq-latency-release-20260907`.

The normal deploy script completed its backup upload/download verification,
schema check, service health checks and Access-authenticated public readiness
check before promoting the receipt.

The first attempt stopped before backup because the committed storage guard
still allowed only 9 GB, while the live environment and its existing uncommitted
guard already supported 20 GB. The script restarted the previous services and
did not promote a release. The successful release includes that exact live
guard compatibility change and its existing regression tests; it did not raise
the configured production limit. The original remote working-tree change and
unrelated local work were preserved.

Reload the app to load the new map and municipality frontend code. The API
performance setting is already active for the deployed workers.
