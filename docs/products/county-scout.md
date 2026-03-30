# County Scout

County Scout is a CountyIQ product for long-running public-source discovery and monitoring. The initial build targets York County, PA and answers five operational questions for each source:

1. What public source exists?
2. What signals does it contain?
3. What is the cheapest viable extraction path?
4. How fragile or risky is the source to rely on?
5. Is it valuable enough to promote into a monitored source registry?

## Scope

The current implementation focuses on York County and the first set of public-interest domains:

- development and land-use activity
- planning and zoning actions
- permit and environmental activity
- procurement and bids
- tax sale and delinquency signals
- parcel, assessment, and property signals
- infrastructure and public-works activity
- commissioner and meeting-packet decision signals

## Runtime Shape

County Scout runs as two Dagster assets in the `scout` group:

- `county_scout_discovery`
  discovers and classifies source candidates from a curated York County seed catalog
- `county_scout_monitor`
  re-checks promoted sources for changes, outages, or new blockers

Schedules:

- discovery: weekly, Wednesday 01:30
- monitoring: daily, 06:30

## Persistence

County Scout stores state in the existing `meta` schema:

- `meta.source_candidates`
  current classification of every discovered source
- `meta.source_registry`
  promoted monitored sources
- `meta.source_observations`
  append-only probe history

This keeps discovery state queryable from the API without giving it any direct dependency on external services.

## API

County Scout exposes four inspection surfaces through FastAPI:

- `GET /api/scout/summary`
- `GET /api/scout/registry`
- `GET /api/scout/candidates`
- `GET /api/scout/sources/{source_key}`

## Seed Catalog

The initial York County seed catalog includes:

- York County official site
- York County GIS hub
- York County assessment portal
- York County bids
- York County tax-sale information
- York County commissioners meetings
- York County Planning Commission
- YCPC subdivision activity reports
- York County Conservation District pending plan review list
- PA DEP eFACTS
- PA Open Data
- PennDOT projects
- PA business search
- York City RFPs
- PLCB licensing

The discovery engine probes each seed, extracts relevant linked documents/endpoints, and scores them for promotion.
