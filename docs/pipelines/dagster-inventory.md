# Dagster Pipeline Inventory

**Review date:** 2026-08-30
**Scope:** all 45 registered assets, 18 jobs, 7 schedules, and 3 sensors

## Operational truth

CountyIQ is not deployed, so none of the code-defined schedules or sensors is
currently running unattended. “Weekly” and “monthly” below mean selected by a
registered schedule if the planned Dagster daemon is deployed and the schedule
is enabled. Local materializations are operator runs, not evidence of a live
production cadence.

The scheduled graph is cost-isolated: `weekly_deterministic_enrichment` targets
only the seven no-provider enrichment assets, PA DOS has its own bounded batch,
and every model-backed Pass 0-4 is disabled by default, manual-only, and capped
at 25 outer work items by default when explicitly enabled. The
full-group `enrichment_refresh` job remains registered for an explicitly funded
operator run but has no schedule.

Importance labels:

- **Critical** — required for the alpha evidence loop or a foundational ID/data contract.
- **Important** — powers a shipped product surface or materially improves its screening.
- **Conditional** — useful only behind an existing policy, privacy, or paid-selection gate.
- **Defer** — no current alpha dependency; keep inactive until its reactivation condition exists.
- **Retire candidate** — no meaningful product consumer; remove after compatibility confirmation.

## Jobs, schedules, and sensors

| Runtime object | Code cadence | What it selects | Assessment |
|---|---:|---|---|
| `arcgis_refresh` | Sunday 02:00 | 10 configured parcel/reference ArcGIS assets | Keep. Foundational source baseline. |
| `radar_refresh` | Sunday 02:30 | 11 configured development-screening assets | Keep. Direct input to deterministic Radar signals. |
| `scraper_refresh` | Sunday 03:00 | Bounded municipal proceedings and sheriff sales | Keep. Proceedings defaults to 250 document requests total and 25 per body, newest first, with database rows as resume checkpoints. |
| `pa_dos_refresh` | Sunday 03:30 | One bounded PA DOS batch | Keep. Defaults to 500 names, 30-day hit refresh, and 180-day negative-cache refresh. |
| `fema_refresh` | Sunday 04:00 | FEMA flood zones | Keep. Property and Radar diligence input. |
| `bulk_refresh` | First of month 05:00 | PLCB licenses and tax claims | Keep conditional. The cadence suits low-frequency sources; source and privacy controls remain mandatory. |
| `deterministic_enrichment_refresh` | Sunday 08:00 | Seven no-provider enrichment assets | Keep. This is the scheduled, cost-isolated rebuild path. |
| `enrichment_refresh` | Manual | Entire enrichment group, deterministic and paid | Keep only as an explicitly funded operator convenience. All paid passes still require per-pass opt-in. |
| `proceedings_refresh` | Manual | One bounded proceedings scraper | Keep for targeted recovery; the same request caps apply. |
| Pass 0, 1, 2, 3, 4 manual jobs | Manual | One model-backed pass each; Pass 1 also refreshes municipality assignments and candidate pairs | Keep. These are the correct paid-pilot and selective-backfill controls. Pass 4 remains off. |
| `intelligence_data_refresh` | Manual | PA DOS + proceedings + paid Pass 0 | Rename or retire later. Its name hides a paid call boundary. |
| `intelligence_full_pipeline` | Manual | Passes 1-4 plus deterministic momentum/events | Keep only as an explicitly funded operator convenience; never treat it as the safe default. |
| Success/failure sensors | Daemon-driven | Slack run outcome messages plus the latest application-health projection in `meta.job_run_status` | Important after deployment; the database projection runs regardless of Slack configuration and remains inert until a daemon processes run events. |
| `intelligence_integrity_guard` | Every five minutes | Aggregate unresolved contradiction age and projection/provenance health | Critical during paid passes. State-change cursoring avoids repeated alerts; warning/critical webhooks remain optional. |

## Asset-by-asset review

### Foundational ArcGIS sources

| Asset | Use and product consumer | Importance and disposition |
|---|---|---|
| `parcels_arcgis` | County parcel baseline used by search, map/property pages, scores, joins, change detection, owners, and nearly every enrichment path. | **Critical — keep weekly.** |
| `municipalities_arcgis` | Municipal boundaries, municipality pages, parcel municipality assignment, and search filters. | **Critical — keep weekly.** |
| `structures_arcgis` | Property details, vacancy/improvement screening, scores, and deterministic signals. | **Important — keep weekly.** |
| `address_points_arcgis` | Address search and county statistics. | **Important — keep weekly.** |
| `zoning_arcgis` | Map layer, property context, and zoning-derived signals. | **Important — keep weekly.** |
| `penndot_projects_arcgis` | Projects API/map and transportation proximity signals. | **Important — keep weekly.** |
| `penndot_roads_arcgis` | Road-name/location search planner. | **Important — keep weekly.** |
| `zipcodes_arcgis` | ZIP search and spatial filtering. | **Important — keep weekly.** |
| `traffic_counts_arcgis` | AADT input in deterministic parcel/score calculations. | **Important — keep while that score ships.** Reassess alongside `local_traffic_counts_arcgis` to avoid unexplained duplicate traffic concepts. |
| `roads_arcgis` | Only the ops row-count surface reads `staging.roads`; product search uses PennDOT roads. | **Retire candidate.** Remove from the weekly job after confirming no external consumer or intended county-road map layer. |

### Development Radar sources

All eleven assets are deterministic, authorized screening inputs to
`development_signals`; most are not meant to be standalone customer datasets.
Their value is the combined parcel-level Radar score and evidence trail.

| Asset | Use | Importance and disposition |
|---|---|---|
| `planning_subdivisions_arcgis` | Active plans/subdivision activity. | **Critical — keep.** This is locally differentiated development evidence. |
| `growth_areas_arcgis` | Growth-area context and site-readiness scoring. | **Important — keep.** |
| `future_landuse_arcgis` | Future-land-use mismatch/context signals. | **Important — keep.** |
| `conservation_easements_arcgis` | Parcel exclusion/constraint evidence. | **Important — keep.** |
| `ag_security_arcgis` | Agricultural Security Area planning context. | **Important — keep.** Enrollment is not a development prohibition or conservation easement. |
| `zoning_overlays_arcgis` | Development overlay and site-readiness evidence. | **Important — keep.** |
| `business_parks_arcgis` | Economic-park opportunity/site-readiness evidence. | **Important — keep.** |
| `industrial_parks_arcgis` | Industrial-park opportunity/site-readiness evidence. | **Important — keep.** |
| `soils_arcgis` | Soil suitability/constraint evidence. | **Important — keep.** |
| `local_traffic_counts_arcgis` | Local traffic activity/site-readiness evidence. | **Important — keep.** Clarify its distinction from PennDOT AADT in user-facing labels. |
| `pa_dep_environmental_diligence` | Storage-tank/cleanup proximity screening, explicitly not a contamination claim. | **Conditional — keep** with attribution, conservative language, and current source-rights controls. |

### Bulk, FEMA, and manual compatibility sources

| Asset | Use and product consumer | Importance and disposition |
|---|---|---|
| `fema_flood_zones` | Property flood context, search filters, scores, and Radar constraints. | **Important — keep weekly.** |
| `plcb_licenses` | License page, municipality counts, owner/entity corroboration. | **Important — keep monthly** under the recorded source policy. |
| `tax_claims` | Delinquency events, municipality aggregates, owner/entity context, and gated distress scoring. | **Conditional — keep monthly.** Privacy and restricted-distress gates are part of the data contract. |
| `pa_open_data` | Manual generic compatibility table; only ops row counts read it and no alpha surface depends on it. | **Retire candidate.** Keep manual until a migration confirms it has no external operator use, then remove asset/table/ops entry together. |

### Scrapers

| Asset | Use and product consumer | Importance and disposition |
|---|---|---|
| `public_proceedings_scrape` | Retrieves authorized municipal minutes/agenda documents for Pass 0; this evidence powers development events and the feed. | **Critical — keep.** It is CountyIQ’s strongest local differentiation, but coverage and source-health warnings must remain visible. |
| `pa_dos_entities` | Deterministic PA business lookup that supplies corporate evidence for ambiguous Pass 1 clusters. | **Conditional — keep, but split/cap before scheduling.** Request count scales with distinct parcel-owner names and can be operationally large even though it has no LLM fee. |
| `sheriff_sales_scrape` | Sheriff-sale input to restricted distress scoring. | **Conditional — keep** only while the restricted-distress lane is intentionally supported; otherwise unschedule rather than presenting it as core alpha evidence. |

### Deterministic enrichment

| Asset | Use and product consumer | Importance and disposition |
|---|---|---|
| `municipality_join` | Assigns municipality to current parcels. | **Critical — keep.** Foundational for search, aggregation, owner, and proceedings linkage. |
| `entity_candidate_pairs_refresh` | Populates the trigram materialized view consumed by Pass 1 after parcel municipalities are current. | **Critical — keep.** The audit found the view was created `WITH NO DATA` and had no previous refresh asset, making fresh Pass 1 selection invalid. |
| `development_signals` | Spatial/rule joins source layers into evidence-bearing parcel signals. | **Critical — keep.** Core deterministic intelligence layer. |
| `owner_resolution` | Creates the stable `public.owners` identity space and source links. | **Critical — keep.** Entity and owner routes depend on this contract. |
| `parcel_events` | Derives transfer, value, and structure changes from parcel SCD2 versions. | **Critical — keep.** The first load establishes a baseline; useful change events appear on later snapshots. |
| `intelligence_events` | Rebuilds the unified feed from deterministic events and cached Pass 0 output without calling a model. | **Critical — keep.** It is the serving ledger for the alpha loop. |
| `development_momentum` | Aggregates signals into Radar scores; uses Pass 2 evidence when present and raw deterministic weights as a fallback. | **Critical — keep.** The no-LLM fallback makes it safe for the deterministic first load. |

### Model-backed enrichment

| Asset | Use and product consumer | Importance and disposition |
|---|---|---|
| `proceeding_extraction` (Pass 0) | Converts heterogeneous municipal documents into source-linked development matters. | **Critical but paid.** Backfill only after deterministic source QA, estimate, capped pilot, and human review. |
| `entity_verification` (Pass 1) | Resolves only ambiguous owner/entity clusters after deterministic matching. | **Conditional and paid.** Important to entity case files, but should never process obvious exact matches. |
| `signal_validation_batched` (Pass 2) | Cross-checks shortlisted parcels with at least two interpretive signals. | **Conditional and paid.** Keep the multi-signal gate; do not run on all parcels. |
| `brief_generation` (Pass 3) | Cached parcel synthesis for medium/high validated evidence. | **Conditional and paid.** Useful supporting UX, not a prerequisite for deterministic property/feed surfaces. |
| `owner_briefs` (Pass 3b) | Cached portfolio synthesis for owners with at least three signaled parcels. | **Conditional and paid.** Generate only after owner and Pass 2 quality are proven. |
| `county_narratives` (Pass 4) | Cross-parcel/county synthesis, exposed only as optional parcel context. | **Defer.** Disabled by default, not required by the alpha loop, and excluded from the estimator total. |

### Paused sources

| Asset | Use | Importance and disposition |
|---|---|---|
| `cdbg_housing_arcgis` | Housing locations whose publication/privacy posture is unresolved. | **Defer/paused.** Keep outside schedules and scoring until review clears it. |
| `ecodev_candidates_arcgis` | Candidate parcels without recorded reuse approval. | **Defer/paused.** Keep outside schedules and expire it from current scoring until written approval exists. |

## Local deterministic inspection

The 2026-08-30 inspection used the local `postgres-test` database. Every model
pass gate was false, `OPENROUTER_API_KEY` was empty, and
`meta.intelligence_passes` remained at zero. No paid backfill was launched.

| Run | Result | Observed output |
|---|---|---|
| `arcgis_refresh` (`87d720ff-26f7-4e0f-b841-79c25fbed20c`) | Success in 58m26s; parcel count and schema checks passed. | 175,928 parcels, 72 municipalities, 292,201 structures, 191,743 address points, 1,700 zoning rows, 78 PennDOT projects, 2,272 PennDOT roads, 51 ZIPs, 1,821 traffic counts, and 34,065 county roads. |
| `radar_refresh` (`dc231c22-1b34-46a8-8167-add7b98c7318`) | Success in about 35s. | 26,904 subdivisions, 27 growth areas, 1,659 future-land-use rows, 976 conservation easements, 4,493 agricultural-security rows, 85 zoning overlays, 504 economic-development park rows, 16,735 soils, 3,010 local traffic counts, and 1,698 PA DEP diligence sites. |
| `fema_refresh` (`932fc98f-87e9-406b-85f8-f3411c862420`) | Success in about 32s. | 4,000 current flood-zone rows. |
| `bulk_refresh` (`1d74280f-8571-4111-ae4c-e1fdcd6815e1`) | Success in 2m13s. | 1,361 PLCB licenses and 36,939 tax claims. |
| `sheriff_sales_scrape` (`d38dd8fc-f862-42cc-81d9-c1630c1aa27f`) | Success in about 3s. | 126 current sheriff-sale rows. |
| `proceedings_refresh` (`fda68860-8cc2-445d-bb9e-130e317d9076`) | Intentionally stopped after about 63 minutes when all but one worker had drained and the remaining uncapped source was serially timing out on old PDFs. | Partial snapshot: 6,371 documents across 94 bodies; 990 have no extracted text, four dates are more than 90 days in the future, and observed dates span 1972-06-06 through an implausible 2030-05-11. |
| `deterministic_enrichment_refresh` (`ec7968d9-368e-4214-aab1-8d5566716a6b`) | Success in 21m14s; all selected checks passed. | 337,267 development signals, 158,990 momentum rows, 146,813 owners, 189,014 owner-source links, 19,870 candidate entity pairs, 3,538 intelligence events, and zero paid-pass rows. The first parcel snapshot correctly produced zero change events. |

The local machine had no R2 credentials. Source rows were allowed to continue
because archive strictness was false, but every attempted raw archive emitted a
warning. Production must provide R2 credentials and keep
`COUNTYIQ_ARCHIVE_STRICT=true`; otherwise a green source load would not satisfy
the evidence-retention contract. All 94 recorded source-rights decisions were
allowed.

PA DOS was not run blindly. Its production selector found 9,871 uncached entity
names. At the built-in 250 ms throttle that is at least 41 minutes and can make
nearly two SODA queries per name. Add a durable cursor and per-run request cap
before scheduling it. Consequently the current Pass 1 estimate excludes the
corporate evidence needed to reason safely about shared-office addresses.

The deterministic run exposed three additional quality/performance risks:

- `owner_resolution` merged business-name groups solely because they shared a
  mailing address, including groups of 34, 28, 25, 26, and 39 names. Shared
  offices, registered agents, and mail drops make this unsafe as a high-
  confidence identity rule; those merges need an ambiguity tier rather than
  unconditional portfolio consolidation.
- The 17 signal types are not equally selective. `growth_area` applies to
  125,816 parcels and `environmental_diligence` to 60,209, while rarer signals
  such as `economic_development_park` apply to 456. Product labels and ranking
  must distinguish broad context from unusual development events.
- The first-load job ran large spatial joins, owner linking, and candidate-pair
  computation concurrently. The candidate view took 12m43s and the signal
  rebuild 21m01s, with the environmental join dominating. Use Dagster pools or
  incremental rebuilds before putting this workload on a shared production
  database.

### Paid-backfill estimate from the inspected snapshot

The read-only estimator sampled 50 production-shaped prompts per eligible pass
and used current production selectors. With Luna for Passes 0-3, the uncapped
first backfill is approximately 26,117 calls and **$39.4118** under the visible
planning assumptions; the maximum-output/retry ceiling is intentionally much
higher and is not a spending recommendation.

| Pass | Eligible units | Planning calls | Planning cost |
|---|---:|---:|---:|
| Pass 0 | 6,131 proceedings | 6,131 | $11.1658 |
| Pass 1 | 6,108 candidate clusters | 12,772 | $20.5169 |
| Pass 2 | 7,214 parcels | 7,214 | $7.7291 |
| Pass 3 / 3b | 0 until validated evidence exists | 0 | $0.0000 |

Pass 0's last-365-day scenario is still about 1,064 calls / $1.9378, and its
last-730-day scenario is 1,751 calls / $3.1889. GLM 5.3 Flash as the Pass 2
challenger lowers that pass's modeled cost from $7.7291 to $3.6326, reducing the
same overall plan to $35.3153; it does not make a full backfill economical. A
hard-capped frozen GLM/Luna pilot has now been completed. The next paid check is
a similarly bounded live-shadow sample only after deterministic backfill makes
the signal/source mix representative—not any current full selector.

## Recommended operating sequence

1. Materialize and inspect deterministic source jobs.
2. Run `deterministic_enrichment_refresh` and verify row counts, checks, source
   rights receipts, and that no new `meta.intelligence_passes` rows appeared.
3. Run `scripts/estimate_llm_backfill.py`; review the exact candidate volume,
   prompt sample, planning estimate, and retry/output ceiling.
4. Run a small pass-specific paid pilot and human-review its outputs.
5. Approve or reject the remaining paid backfill by pass. Keep Pass 4 off.

The deployment blockers identified in this review are now addressed in code:
scheduled enrichment is deterministic-only; paid passes are opt-in and
manual-only; PA DOS is separately scheduled and capped; proceedings is capped,
newest-first, resumable, and rejects implausibly future dates. Do not add paid
pass schedules without a separately approved cadence and budget guard.
