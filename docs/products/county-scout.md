# County Scout

County Scout is an internal CountyIQ source-discovery and monitoring subsystem,
not an alpha customer product. It supports the evidence layer by answering five
operational questions for each source:

1. What public source exists?
2. What signals does it contain?
3. What is the cheapest viable extraction path?
4. How fragile or risky is the source to rely on?
5. Is it valuable enough to promote into a monitored source registry?

## Current product decision

County Scout is not used by the current product and is not worth activating for
the York alpha. As of the 2026-08-27 completion audit, its candidate, registry,
and observation tables all contain zero rows; it contributes no score, feed,
case-file, or frontend signal. The reviewed source register and explicit
source-onboarding workflow provide better evidence with substantially lower
legal and operational risk.

Keep the implementation paused as an offline research prototype, not active
product infrastructure. Reconsider it only when multi-county expansion creates
enough source-discovery volume to justify redesigning Scout as candidate-only
discovery: no automatic fetch, retention, monitoring, or promotion before a
human rights review approves the exact source and origin.

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
  discovers and classifies source candidates from York's curated catalog or a
  manifest-derived starter catalog for another county
- `county_scout_monitor`
  re-checks promoted sources for changes, outages, or new blockers

Both jobs remain registered for inspection but are absent from schedules and
blocked by the paused `county_scout` source policy, including manual runs. The
API fails closed under the same policy. Reactivation requires a reviewed
outbound-host boundary, source-by-source terms/robots evidence, retention rules,
and promotion criteria; validating cost or product value alone is insufficient.

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

The curated York County seed catalog includes:

- York County official site
- York County GIS hub
- York County assessment portal
- York County bids
- York County tax-sale information
- York County commissioners meetings
- York County Planning Commission
- YCPC building permit reports
- YCPC subdivision activity reports
- York County Conservation District pending plan review list
- PA DEP eFACTS
- PA Open Data
- PennDOT projects
- PA business search
- York City RFPs
- PLCB licensing

For other configured counties, the starter catalog is derived from manifest
GIS, tax, PennDOT, state-open-data, and municipal-proceedings URLs, so it never
falls back to York sources. The discovery engine probes each seed, extracts
relevant linked documents/endpoints, and scores them for promotion.
