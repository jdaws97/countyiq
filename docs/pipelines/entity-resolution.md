# Entity Resolution

## What it does

Entity resolution answers the question: "Are these two records from different sources talking about the same person, business, or property?" Owner names arrive from GIS parcels, tax claims, PLCB liquor licenses, PA corporate filings, and public proceedings — all with slightly different formatting, abbreviations, and errors. Entity resolution links them into a single canonical owner.

## Single identity space

`public.owners` is the **only** owner identity space. The API serves
`/api/owners/{owner_id}` from it directly, and `owner_id` is **stable across
rebuilds**: the `owner_resolution` asset upserts by `canonical_name`
(unique constraint, migration 025) instead of truncating and restarting the
sequence, so profile URLs survive re-runs.

`public.entity_graph` still exists, but only as **Pass 1's output table**
(`entity_verification` — LLM-verified alias clusters and relationships).
`owner_resolution` reads it and folds the results onto the owner rows:
`aliases`, `relationships`, `verification_status`, `verification_reasoning`,
`verified_at`. There is no separate entity-graph ID space in the API anymore.

## How resolution works (`pipelines/countyiq/assets/enrichment/owners.py`)

**Stage 1 — Normalize.** Python-side name normalization: uppercase, strip
parentheticals, iteratively strip entity/person suffixes (LLC, INC, TRUST, JR,
…), collapse whitespace. Raw names with the same normalized form group
together ("SMITH JOHN A" + "SMITH JOHN A JR").

**Stage 2 — Cluster.** One evidence-backed merge pass runs over normalized
groups with a union-find. Shared-address groups are measured for review but do
not merge automatically:

1. **Shared-address ambiguity detection:** business-classified groups sharing
   normalized `mail_addr_full` are counted in materialization metadata. They
   remain separate because registered agents, accountants, virtual offices,
   and large landlords can host unrelated entities at one address.
2. **Entity-graph merge** (`match_tier = 'entity_graph'`, confidence 0.9):
   groups whose names appear in the same `entity_graph` row's
   `canonical_name`/`linked_names` merge, and the owner row inherits that
   row's verification metadata and relationships.

**Stage 3 — Canonicalize and classify.** Canonical name = the variant holding
the most parcels (tie → shortest). Entity type is a priority vote across all
variants: `government > trust > business > person`.

**Stage 4 — Upsert.** Owners upsert by `canonical_name` (parcel_count,
mode-municipality, mode-mailing-address, aliases, verification fields);
owners that disappeared are deleted. `owner_source_links` is rebuilt:

| source_type | match | confidence |
|---|---|---|
| `parcel` | normalized name / entity graph | 1.0 / 0.9 |
| `tax_claim` | PIDN join through parcel links | 0.95 |
| `plcb_license` | trigram `%` match, municipality-scoped | similarity (>0.6) |
| `plcb_license` | trigram `%` match, unscoped fallback | similarity × 0.8 (>0.75) |

PLCB matching sets `pg_trgm.similarity_threshold` and uses the `%` operator
so the planner can drive the join from the small license table through
`idx_owners_name` (GIN trigram) instead of computing `similarity()` across
the owners × licenses cross product.

## Ordering

`owner_resolution` depends on `municipality_join` (PLCB scoping needs
`staging.parcels.municipality`). `owner_briefs` (Pass 3b) depends on
`owner_resolution` and keys briefs by `canonical_name`, which survives both
rebuilds and cluster re-merges.

## Validation queries (run after resolution)

```sql
-- 1. Distribution by match tier (any tier dominating suspiciously?)
SELECT match_tier, COUNT(*), ROUND(AVG(confidence), 2)
FROM public.owner_source_links
GROUP BY match_tier ORDER BY COUNT(*) DESC;

-- 2. Possible over-merges (persons with huge portfolios)
SELECT canonical_name, entity_type, parcel_count, municipality
FROM public.owners
WHERE entity_type = 'person' AND parcel_count > 100
ORDER BY parcel_count DESC LIMIT 20;

-- 3. Shared-address links should never be emitted automatically
SELECT COUNT(*) AS unsafe_address_links
FROM public.owner_source_links
WHERE match_tier = 'shared_mail_addr';

-- 4. Entity type distribution (expect ~80% person, ~15% business,
--    ~3% trust, ~2% government)
SELECT entity_type, COUNT(*),
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM public.owners GROUP BY entity_type;
```

## Known limitations and when to upgrade

| Limitation | Impact | When to upgrade |
|---|---|---|
| Address-only evidence does not merge LLC portfolios | Legitimate one-owner/many-LLC portfolios stay split until stronger evidence exists | Use officers, registered agents plus corroborating evidence, deeds, or reviewed Pass 1 links; never promote address alone to identity |
| Full rebuild every run | Fine at county scale (~200K names) | Incremental matching when rebuild exceeds ~30 min |
| No ML confidence scoring | Rigid tiers; edge cases fall through | Zingg or similar when false positive/negative rate is unacceptable — same tables, only Stage 2 changes |
| No cross-county entity linking | Each county is a separate entity universe | When multi-county product is in scope |
