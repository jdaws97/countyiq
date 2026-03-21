# Entity Resolution

## What it does

Entity resolution answers the question: "Are these two records from different sources talking about the same person, business, or property?" Your platform pulls owner names from assessment records, deed transfers, business filings, professional licenses, and liquor licenses — all with slightly different formatting, abbreviations, and errors. Entity resolution links them together into a single canonical entity.

## Approach: Deterministic matching in PostgreSQL

For the MVP, all matching logic runs as SQL inside the `enrichment/owners.py` Dagster asset. No external tools, no Spark, no ML models. Just PostgreSQL functions using the `pg_trgm` extension (already planned for installation) and well-designed normalization logic.

The approach has three stages:

**Stage 1: Normalize.** Before comparing anything, clean and standardize all names and addresses into a consistent format.

Name normalization:
- Uppercase everything
- Strip suffixes: JR, SR, II, III, IV
- Strip entity types: LLC, INC, CORP, LP, LTD, CO, TRUST, ESTATE
- Strip punctuation and extra whitespace
- Handle common abbreviations: WM → WILLIAM, ROBT → ROBERT, CHAS → CHARLES
- Result: "John A. Smith Jr." → "JOHN A SMITH"
- Result: "York Properties, LLC" → "YORK PROPERTIES"

Address normalization:
- Uppercase everything
- Standardize street types: STREET/ST → ST, AVENUE/AVE → AVE, ROAD/RD → RD, etc.
- Standardize directionals: NORTH/N → N, SOUTH/S → S, etc.
- Strip unit/apt/suite numbers (these vary wildly across sources)
- Pad zip codes to 5 digits
- Result: "123 North Main Street, Apt 2" → "123 N MAIN ST"

These normalizations live as PostgreSQL functions in the `public` schema so they can be reused everywhere:

```sql
CREATE OR REPLACE FUNCTION normalize_name(raw_name TEXT)
RETURNS TEXT AS $$
    SELECT UPPER(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                TRIM(raw_name),
                '\s+(JR|SR|II|III|IV|LLC|INC|CORP|LP|LTD|CO|TRUST|ESTATE)\.?$',
                '', 'gi'
            ),
            '[^A-Za-z0-9\s]', '', 'g'
        )
    );
$$ LANGUAGE SQL IMMUTABLE;

CREATE OR REPLACE FUNCTION normalize_address(raw_address TEXT)
RETURNS TEXT AS $$
    -- Similar pattern: uppercase, standardize types, strip units
    ...
$$ LANGUAGE SQL IMMUTABLE;
```

**Stage 2: Match.** Compare normalized records across sources using a tiered confidence system:

| Tier | Rule | Confidence | Example |
|---|---|---|---|
| Exact | Normalized name AND normalized address match exactly | 0.95 | "JOHN SMITH" + "123 N MAIN ST" appears in both assessment and deeds |
| Strong | Normalized name exact match + address similarity > 0.8 (pg_trgm) | 0.80 | "JOHN SMITH" at "123 N MAIN ST" vs "123 NORTH MAIN STREET" |
| Fuzzy name | Name similarity > 0.85 (pg_trgm) + exact address | 0.70 | "JOHN A SMITH" vs "JOHN SMITH" at same address |
| Business alias | Normalized business name similarity > 0.8 + same municipality | 0.65 | "YORK PROPERTIES" vs "YORK PROPS" in same township |
| Address only | Same parcel ID across sources (strongest geographic link) | 0.90 | Assessment and deed both reference parcel 43-000-01-0001 |

The parcel ID match (last row) is actually the most reliable link you have — if two records reference the same parcel, they're almost certainly related to the same property, even if the owner names differ slightly (could be a trust, an LLC, etc.).

```sql
-- MVP example: Match owners across GIS parcels and assessment records using PIDN
-- This is the core MVP matching query — parcels + assessment only.
WITH matched_pairs AS (
    SELECT
        p.owner_full AS gis_owner,
        a.owner_name AS assessment_owner,
        p.pidn,
        similarity(normalize_name(p.owner_full), normalize_name(a.owner_name)) AS name_score,
        CASE
            WHEN normalize_name(p.owner_full) = normalize_name(a.owner_name)
                AND normalize_address(p.propadr) = normalize_address(a.address) THEN 0.95  -- Exact name + exact normalized address
            WHEN normalize_name(p.owner_full) = normalize_name(a.owner_name)
                AND similarity(p.propadr, a.address) > 0.8 THEN 0.80  -- Exact name + fuzzy address
            WHEN similarity(normalize_name(p.owner_full), normalize_name(a.owner_name)) > 0.85
                AND p.pidn = a.pidn THEN 0.70  -- Fuzzy name + same parcel
            WHEN p.pidn = a.pidn THEN 0.90  -- Address only: same parcel ID (strongest geographic link)
            ELSE NULL
        END AS confidence
    FROM staging.parcels p
    JOIN staging.assessment_properties a ON (
        p.pidn = a.pidn  -- PIDN is the primary join key
        OR (similarity(normalize_name(p.owner_full), normalize_name(a.owner_name)) > 0.7
            AND similarity(p.propadr, a.address) > 0.7)
    )
    WHERE p.valid_to IS NULL  -- Current records only (SCD Type 2)
)
SELECT *
FROM matched_pairs
WHERE confidence IS NOT NULL;

-- Phase 2 example: Add deeds to the matching pool (when deeds pipeline is built)
-- Same pattern — join staging.deeds on PIDN or name+address similarity
```

**Stage 3: Cluster.** Group matched records into entities. Each entity gets a canonical name (the most frequently occurring normalized form) and a canonical address (from the most authoritative source — assessment data, since it's county-maintained).

## Schema

```sql
-- Resolved entities
CREATE TABLE public.owners (
    owner_id        SERIAL PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    canonical_addr  TEXT,
    entity_type     TEXT,  -- 'person', 'business', 'trust', 'government'
    municipality    TEXT,
    parcel_count    INTEGER DEFAULT 0,
    first_seen      DATE,
    last_seen       DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Links back to every source record
CREATE TABLE public.owner_source_links (
    link_id         SERIAL PRIMARY KEY,
    owner_id        INTEGER REFERENCES public.owners(owner_id),
    source_type     TEXT NOT NULL,  -- 'assessment', 'deed', 'business_filing', 'license', 'liquor'
    source_id       TEXT NOT NULL,  -- Original ID from that source
    source_name     TEXT,           -- Original (un-normalized) name from source
    source_address  TEXT,           -- Original (un-normalized) address from source
    match_tier      TEXT,           -- 'exact', 'strong', 'fuzzy_name', 'business_alias', 'parcel_link'
    confidence      NUMERIC(3,2),   -- 0.00 to 1.00
    matched_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(source_type, source_id)  -- One link per source record
);

-- Indexes for fast lookups
CREATE INDEX idx_owners_name ON public.owners USING gin (canonical_name gin_trgm_ops);
CREATE INDEX idx_owners_municipality ON public.owners (municipality);
CREATE INDEX idx_owner_links_owner ON public.owner_source_links (owner_id);
CREATE INDEX idx_owner_links_source ON public.owner_source_links (source_type, source_id);
```

## What this enables

Once the `owners` table is populated, the platform can answer questions like:

- **"Who owns the most parcels in Conewago Township?"** — Query `owners` joined to `owner_source_links` where source_type = 'assessment', grouped by owner_id, filtered by municipality.
- **"Show me everything we know about York Properties LLC"** — Find the owner_id, then pull all source links — every parcel they own, every deed transfer, business filing details, any licenses.
- **"Which businesses in this area have both a liquor license and recent code violations?"** — Join owners to PLCB source links and permit/violation source links through the same owner_id.

## Why this design scales to other counties

The `owners` table and `owner_source_links` table know nothing about York County specifically. The normalization functions are generic (they handle Pennsylvania address patterns, but that's a config change, not a code change). The matching tiers work on any name + address data. If you ever add Lancaster County, you'd create the same schema in a separate database (or a separate schema within the same database), run the same normalization and matching logic against Lancaster's data sources, and get a resolved entity set for Lancaster.

The scrapers change per county. The entity resolution doesn't.

## Dagster asset: `enrichment/owners.py`

Entity resolution has two scopes: an MVP contract (parcels + assessment only) and a Phase 2 enriched contract (all sources). The Dagster asset dynamically resolves whichever sources are available.

**MVP resolution (parcels + assessment):**
- Matches owner names from `staging.parcels` (GIS `owner_full` field) against `staging.assessment_properties` owner records
- Joins on PIDN (strongest link — same parcel across both sources)
- Falls back to name + address fuzzy matching (pg_trgm) for records without a PIDN match
- **Future fallback (after AddressPts layer is loaded):** When PROPADR is messy or missing, match owner mailing addresses against `staging.address_points` for geocoded resolution. This is a second-chance geocoder that comes free from the GIS portal.
- This already provides meaningful value: unified ownership across the two largest datasets

**Phase 2 enriched resolution (+ deeds, business filings, licenses):**
- Same matching logic, but with additional source tables feeding into the candidate pool
- Each new source type gets added to the `owner_source_links.source_type` enum as its pipeline is built
- Adding a source to resolution = adding it to the deps list and the matching query

```python
# MVP deps — only parcels + assessment exist at launch
MVP_DEPS = ["parcels", "assessment_properties"]

# Phase 2 deps — added one at a time as pipelines are built.
# Dagster won't fail if these don't exist yet; use check_fn or config flag.
PHASE2_DEPS = ["deeds", "business_filings", "pals_licenses", "plcb_licenses"]

@asset(
    group_name="enrichment",
    deps=MVP_DEPS,  # Start with MVP; add Phase 2 deps as sources come online
    description="Resolved owner entities across all available data sources",
)
def owners(context: AssetExecutionContext, database):
    """Run entity resolution across all loaded source tables"""

    # Detect which source tables actually have data
    available_sources = database.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'staging'
        AND table_name IN ('parcels', 'assessment_properties', 'deeds',
                           'business_filings', 'pals_licenses', 'plcb_licenses')
    """).fetchall()
    source_tables = [row[0] for row in available_sources]
    context.log.info(f"Running entity resolution against: {source_tables}")

    # 1. Normalize all source names/addresses (using SQL functions)
    # 2. Run tiered matching (exact → strong → fuzzy → parcel-link)
    # 3. Cluster matches into entities
    # 4. Write to public.owners + public.owner_source_links
    # 5. Log stats: total entities, match distribution by tier

    stats = database.execute_entity_resolution(source_tables)
    context.log.info(
        f"Resolved {stats['total_entities']} entities "
        f"from {stats['total_source_records']} source records "
        f"across {len(source_tables)} sources. "
        f"Match distribution: {stats['tier_counts']}"
    )
```

**MVP:** This asset depends only on `parcels` and `assessment_properties`. Dagster runs it after the weekly GIS + Assessment refresh completes (Sunday). It dynamically detects which staging tables have data, so it won't break when Phase 2 tables don't exist yet.

**Phase 2:** As each new source pipeline is built and its staging table is populated, entity resolution automatically picks it up on the next run. Update the `deps` list to include the new source so Dagster waits for it before running resolution.

## Known limitations and when to upgrade

| Limitation | Impact | When to upgrade |
|---|---|---|
| No ML confidence scoring | Rigid tiers; edge cases fall through | When false positive/negative rate is unacceptable |
| No incremental matching | Full rebuild on every run | When dataset grows large enough that full rebuild is slow (>30 min) |
| No human-in-the-loop review | Ambiguous matches auto-resolved by tier | When match accuracy is critical for official use |
| Name abbreviation handling is limited | Custom abbreviation list needs maintenance | When common abbreviations cause consistent misses |
| No cross-county entity linking | Each county is a separate entity universe | When multi-county product is in scope |

**Upgrade path:** If deterministic matching isn't sufficient, the next step is **Zingg** (open-source, Spark-based ML matching). The schema doesn't change — Zingg would replace the matching logic in Stage 2, outputting to the same `owners` and `owner_source_links` tables. The normalization functions and schema are already designed to be tool-agnostic.
