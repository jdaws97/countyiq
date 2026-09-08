# Activity query timeout, September 8, 2026

The owner reported that Activity waited and then returned HTTP 500. Production
API logs identified `fetch_feed`'s main query and PostgreSQL's statement timeout.
Backfill clients were drained during diagnosis and release.

## Cause and change

At 515 accepted accounts and 21,732 current municipal records, the old account
count took 51.158 seconds. Its member aggregate scanned all 21,732 candidates for
each account and read 7,343,415 temporary database blocks. The query also built
complete source payloads for bundles without an accepted account.

Migration 076 keeps the same complete county-wide identity resolution in a
compact scope view. It loads full evidence only for bundles with accepted
accounts, checks their complete source-record snapshots, and joins member keys
once. Address ambiguity checks use a combined current-municipality/address
index. First-observation dates are aggregated once per proceeding and retain
each card's earliest matching accepted observation.

The Activity view excludes records that lack the required explanation before
building individual evidence-card validation inputs. It retains current source,
permission, property/entity connection, complete bundle, English presentation,
and matter-coverage checks. The delinquency baseline query reads the event table
directly because those events pass through the current-source view unchanged.
No timeout was increased, model output changed, or stale-data cache introduced.

## Verification before deployment

- A transaction on production data created temporary candidate views and a
  transaction-scoped index, then rolled everything back. The exact default
  Activity SQL returned three events in 6.264 seconds with JIT disabled, matching
  API connection settings. This is SQL execution time, not a browser measurement.
- All 21,732 compact scopes matched the old resolver exactly, including bundle
  keys and record positions.
- Fourteen complete account rows across eleven sampled bundles matched exactly.
  The sample included all accepted non-selection bundles and eight selection
  bundles. All evidence columns on the sample's 24 proceedings also matched.
  The old sample query needed its bundle restriction inside the accepted CTE;
  the original unbounded version exceeded the 60-second diagnostic timeout.
- The clean release checkout passed 1,865 non-integration pipeline tests.
  Targeted database/API tests covered bundle additions, source changes, municipal
  and global rights, changed or ambiguous addresses, owner changes, pagination,
  search, following, and per-card first-observation times. Feed unit checks and
  all 16 quality-release tests passed.

The new migration participates in Pass 0 and record-mode Pass 3 quality receipts.
Production browser latency and performance after the remaining account backfill
must be measured separately; the pre-deploy timing is not a guarantee at a larger
accepted population.
