# Production PostgreSQL latency review — September 7, 2026

Read-only diagnosis of the Properties shortlist, map property selection, and
municipality profiles. Observations were collected around 7:57–8:01 p.m. Eastern
on September 7 (23:57–00:01 UTC, September 7–8).

## Findings

The largest confirmed list/feed delay is PostgreSQL JIT compilation. A separate
map delay comes from calculating detailed soil coverage before displaying a
summary that does not use it. No Dagster asset jobs were running or queued when
checked.

| Live API operation | Normal configuration | JIT disabled in test transaction | Result comparison |
| --- | ---: | ---: | --- |
| Properties opportunity shortlist, first 200 rows | 4,146 / 4,085 ms | 65 / 64 ms | Entire response identical |
| Springettsbury municipality profile | 185 ms | 122 ms | Entire response identical |
| Springettsbury activity feed, first 6 rows | 5,959 ms | 16 ms | Entire response identical |
| Large Warrington parcel report, `49000NF0093A0` | 3,362 ms | 3,295 ms | Entire response identical |

These are direct calls to deployed API functions inside the production API
container, using production data and its existing database credentials. They
exclude HTTP, authentication, connection-pool contention, network transfer and
browser rendering. They are small diagnostic samples, not latency percentiles
or guarantees for every municipality or parcel.

### 1. JIT dominates the Properties query

The live database has `jit=on` and `jit_above_cost=100000`. The current radar view
expands source-freshness checks into a complex plan. The measured plan generated
219 JIT functions, even though little execution work was needed.

`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` on the deployed shortlist query showed:

- JIT on: 3,977.558 ms execution, including 3,967.545 ms JIT compilation.
- JIT off: 9.494 ms execution.
- Planning took about 9 ms in each case.
- Both plans reported 2,473 shared-buffer hits, zero shared-buffer reads, and
  zero temporary-block reads/writes at the root.

This directly attributes nearly all the measured SQL execution delay to
compilation, rather than disk reads or a missing spatial index. PostgreSQL's
[JIT guidance](https://www.postgresql.org/docs/16/jit-decision.html) explains that
compilation overhead can exceed the benefit for short queries.

The transaction-local on/off/on/off comparison returned the exact same 200-row
response each time. Source policy and freshness predicates were retained.

Recommended first change: disable JIT specifically for API database connections.
Possible implementation points are `api/lib/database.py:_connection_kwargs`
or the API role settings in `pipelines/init-db/03-api-role.sh`. A role default
requires new pooled connections before it applies. Keep the pipeline connection
policy separate, since its workload differs. Validate deployed API behavior and
persist the setting in the deployment contract.

### 2. Municipality rendering waits for the activity feed

The Springettsbury profile itself returned in 185 ms, but its six-item feed
took 5.96 seconds with normal settings and 16 ms with JIT disabled. Both feed
responses were identical. This feed comparison isolates the same setting; a
separate feed `EXPLAIN ANALYZE` was not collected.

`frontend/src/pages/MunicipalityDetail.tsx:62` fetches the profile first, then
fetches the feed at line 77. The page stays in its loading state until both
requests finish. Consequently, the slow feed hides an already-loaded profile.

Recommended companion change: render the profile when ready and load its feed
independently, with a loading/error state confined to the activity section.

The profile's parcel aggregate also spent roughly 87–130 ms filtering with
`UPPER(municipality) LIKE ...`. Normalize municipality matching or evaluate a
matching expression index only after the multi-second issues are addressed;
this aggregate was not the main observed delay.

### 3. Map selection computes soils unnecessarily

`frontend/src/pages/MapView.tsx:602` requests the complete property report.
`api/routes/parcels.py:605` calls `public.parcel_soil_units` before returning that
report. The function, defined in migration 066, clips soil polygons, makes
geometry valid, transforms coordinates and unions overlaps to calculate area
coverage. The map's summary panel does not display these soil results.

For the large Warrington sample, the soil query consumed 3,275 ms of the
3,362 ms report. With JIT off, it still consumed 3,235 ms of a 3,295 ms report.
Another large parcel in Manheim took approximately 2.1 seconds. Smaller sampled
York City, York Township and Shrewsbury parcels generally returned in tens of
milliseconds, with initial samples up to approximately 117 ms.

Live GiST indexes already exist for soils, parcel geometry, parcel geography,
structures and flood zones. Simply adding those indexes again is not a fix.

Recommended change: provide a map summary response that computes only displayed
facts, or defer detailed soil facts to a separate report request. Preserve the
summary's existing flood, structure, ownership and evidence behavior. For the
full report, consider storing deterministic soil facts keyed to current parcel
and soil versions, with explicit invalidation when those inputs change. That
larger design needs freshness tests before implementation.

The current map effect also ignores stale responses without aborting its fetch.
Canceling obsolete browser requests can reduce unnecessary client work, but
must not be assumed to cancel an already-running synchronous database query.

## Dagster and server activity

The live Dagster GraphQL API returned an empty result for runs in `STARTED`,
`STARTING`, `QUEUED` and `NOT_STARTED` states. Recent daemon logs showed sensor
checks returning empty results or unchanged integrity state. The daemon was
running, but there was no evidence of an asset materialization competing with
these requests at that time.

A PostgreSQL activity snapshot captured long API feed queries and a soil query.
Dagster was updating its own scheduler metadata. A separate container snapshot
showed PostgreSQL at approximately 95% CPU and the Dagster daemon at 6%; that
point-in-time CPU reading does not establish sustained saturation.

## Scope and follow-through

The production release receipt reported commit
`7082d3f823920c4231b0695b8867c08d5c413b63`, schema 069, deployed at
2026-09-07 23:48:09 UTC.

All database probes used read-only transactions and a 15-second statement
timeout. JIT changes used `SET LOCAL` on isolated diagnostic transactions.
No persistent database setting, schema, application code, scheduler state or
production deployment was changed. Existing workspace changes were preserved.

Implement and measure in this order: API-scoped JIT configuration; independent
municipality section loading; map summary/report separation. Then reassess
remaining query plans before undertaking general index or memory tuning.
