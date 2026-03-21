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

**Stage 2: Match.** Compare normalized records across sources using a tiered confidence system. All fuzzy matches are scoped to the same municipality to reduce false positives ("JOHN SMITH" in Conewago shouldn't match "JOHN SMITH" in Spring Garden):

| Tier | Rule | Confidence | Example |
|---|---|---|---|
| Parcel link | Same PIDN across sources | 0.95 | Assessment and GIS both reference parcel 43-000-01-0001. Strongest link — even if owner names differ (trust, LLC, etc.) |
| Exact | Normalized name AND normalized address match exactly | 0.90 | "JOHN SMITH" + "123 N MAIN ST" appears in both assessment and GIS |
| Strong | Normalized name exact + address similarity > 0.8 (pg_trgm), same municipality | 0.80 | "JOHN SMITH" at "123 N MAIN ST" vs "123 NORTH MAIN STREET" in Conewago |
| Fuzzy name | Name similarity > 0.85 (pg_trgm) + same PIDN | 0.70 | "JOHN A SMITH" vs "JOHN SMITH" on same parcel |
| Business alias | Normalized business name similarity > 0.8 + same municipality | 0.65 | "YORK PROPERTIES" vs "YORK PROPS" in same township |
| Address point geocode | Owner mailing address matches `staging.address_points`, resolved point falls within a parcel polygon | 0.75 | Assessment mailing address "123 N MAIN STREET" → address point → ST_Within → parcel PIDN. Catches cases where PROPADR formatting prevents direct matching. |

**Municipality scoping:** The municipality spatial join (from `staging.municipalities`) must run before entity resolution. Fuzzy matches (Strong, Business alias) are restricted to `WHERE p.municipality = a.municipality`, which both reduces false positives and makes the pg_trgm similarity joins faster (smaller candidate set per municipality).

**Address point bridge:** When `staging.address_points` has data, entity resolution gains an extra matching path. For assessment records where the PIDN join misses (e.g., PARID→PIDN conversion failed or PIDN is absent), normalize the assessment address → match against address points → use `ST_Within(addr_point.geom, parcel.geom)` to find the containing parcel → link back to PIDN. This is a second-chance geocoder that comes free from the GIS portal.

```sql
-- MVP matching query: parcels + assessment, scoped by municipality
WITH matched_pairs AS (
    SELECT
        p.owner_full AS gis_owner,
        a.owner_name AS assessment_owner,
        p.pidn,
        p.municipality,
        similarity(normalize_name(p.owner_full), normalize_name(a.owner_name)) AS name_score,
        CASE
            -- Tier: parcel_link (0.95) — same PIDN is the strongest link
            WHEN p.pidn = a.pidn THEN 0.95
            -- Tier: exact (0.90) — normalized name + address match exactly
            WHEN normalize_name(p.owner_full) = normalize_name(a.owner_name)
                AND normalize_address(p.propadr) = normalize_address(a.address) THEN 0.90
            -- Tier: strong (0.80) — exact name + fuzzy address, same municipality
            WHEN normalize_name(p.owner_full) = normalize_name(a.owner_name)
                AND similarity(normalize_address(p.propadr), normalize_address(a.address)) > 0.8
                AND p.municipality = a.municipality THEN 0.80
            -- Tier: fuzzy_name (0.70) — fuzzy name + same PIDN
            WHEN similarity(normalize_name(p.owner_full), normalize_name(a.owner_name)) > 0.85
                AND p.pidn = a.pidn THEN 0.70
            ELSE NULL
        END AS confidence,
        CASE
            WHEN p.pidn = a.pidn THEN 'parcel_link'
            WHEN normalize_name(p.owner_full) = normalize_name(a.owner_name)
                AND normalize_address(p.propadr) = normalize_address(a.address) THEN 'exact'
            WHEN normalize_name(p.owner_full) = normalize_name(a.owner_name) THEN 'strong'
            WHEN similarity(normalize_name(p.owner_full), normalize_name(a.owner_name)) > 0.85 THEN 'fuzzy_name'
            ELSE NULL
        END AS match_tier
    FROM staging.parcels p
    JOIN staging.assessment_properties a ON (
        p.pidn = a.pidn  -- PIDN is the primary join key
        OR (
            p.municipality = a.municipality  -- Municipality scoping reduces false positives
            AND similarity(normalize_name(p.owner_full), normalize_name(a.owner_name)) > 0.7
        )
    )
    WHERE p.valid_to IS NULL AND a.valid_to IS NULL
)
SELECT * FROM matched_pairs WHERE confidence IS NOT NULL;

-- Address point bridge: for unmatched assessment records, geocode through address_points
-- Only runs when staging.address_points has data
WITH unmatched_assessment AS (
    SELECT a.* FROM staging.assessment_properties a
    WHERE a.valid_to IS NULL
    AND a.pidn NOT IN (SELECT pidn FROM matched_pairs WHERE confidence IS NOT NULL)
),
geocoded AS (
    SELECT
        ua.owner_name,
        ua.address,
        p.pidn,
        p.municipality,
        0.75 AS confidence,
        'address_geocode' AS match_tier
    FROM unmatched_assessment ua
    JOIN staging.address_points ap
        ON similarity(normalize_address(ua.address), normalize_address(ap.full_address)) > 0.85
        AND ap.valid_to IS NULL
    JOIN staging.parcels p
        ON ST_Within(ap.geom, p.geom)
        AND p.valid_to IS NULL
)
SELECT * FROM geocoded;

-- PLCB cross-reference: match licensees to resolved owners
-- Runs after owners table is populated from parcels + assessment
INSERT INTO public.owner_source_links (owner_id, source_type, source_id, source_name, source_address, match_tier, confidence)
SELECT
    o.owner_id,
    'plcb_license',
    l.lid,
    l.licensee,
    l.premises_address,
    'business_alias',
    GREATEST(0.65, similarity(normalize_name(l.licensee), o.canonical_name)) AS confidence
FROM staging.plcb_licenses l
JOIN public.owners o
    ON similarity(normalize_name(l.licensee), o.canonical_name) > 0.8
    AND o.municipality = l.municipality
WHERE l.valid_to IS NULL
ON CONFLICT (source_type, source_id) DO UPDATE
    SET confidence = EXCLUDED.confidence, matched_at = NOW();
```

**Stage 3: Cluster and classify.** Group matched records into entities. Each entity gets:

- **Canonical name:** Most frequently occurring normalized form across sources
- **Canonical address:** From the most authoritative source (assessment data, since it's county-maintained)
- **Entity type:** Classified by heuristic pattern matching on the canonical name (no LLM needed):

```sql
CASE
    WHEN canonical_name ~ '(LLC|INC|CORP|LP|LTD|CO\b|COMPANY|ASSOCIATES|PARTNERS|GROUP|HOLDINGS)'
        THEN 'business'
    WHEN canonical_name ~ '(TRUST|ESTATE|REVOCABLE|IRREVOCABLE|LIVING TRUST)'
        THEN 'trust'
    WHEN canonical_name ~ '(COUNTY|COMMONWEALTH|SCHOOL DIST|BOROUGH|TOWNSHIP|CITY OF|STATE OF|UNITED STATES)'
        THEN 'government'
    ELSE 'person'
END
```

This classification powers the frontend — the Top Owners dashboard distinguishes individual owners from institutional owners, and the owner profile page displays entity type.

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

- **"Who owns the most parcels in Conewago Township?"** — Query `owners` WHERE `municipality = 'Conewago Twp'` ORDER BY `parcel_count DESC`. Already computed during resolution.
- **"Show me everything we know about York Properties LLC"** — Find the owner_id (entity_type = 'business'), then pull all source links — every parcel they own, assessment data, and whether they hold a liquor license (PLCB cross-reference).
- **"Which businesses in this area have both a liquor license and property?"** — Join owners WHERE entity_type = 'business' to owner_source_links WHERE source_type IN ('plcb_license', 'assessment'). Group by owner_id HAVING COUNT(DISTINCT source_type) >= 2.
- **"Top institutional property owners"** — `SELECT * FROM public.owners WHERE entity_type IN ('business', 'trust') ORDER BY parcel_count DESC`. Distinguishes LLCs and trusts from individual owners.
- **"Flag properties where assessment PIDN lookup failed"** — Address point bridge records (match_tier = 'address_geocode') indicate properties where the PARID→PIDN conversion didn't work and geocoding was needed as a fallback — a data quality signal.

## Why this design scales to other counties

The `owners` table and `owner_source_links` table know nothing about York County specifically. The normalization functions are generic (they handle Pennsylvania address patterns, but that's a config change, not a code change). The matching tiers work on any name + address data. If you ever add Lancaster County, you'd create the same schema in a separate database (or a separate schema within the same database), run the same normalization and matching logic against Lancaster's data sources, and get a resolved entity set for Lancaster.

The scrapers change per county. The entity resolution doesn't.

## Dagster asset: `enrichment/owners.py`

Entity resolution dynamically resolves whichever sources are available. It detects loaded staging tables at runtime and includes matching logic for each.

**MVP resolution (parcels + assessment + PLCB):**
- **Core match:** GIS `owner_full` against assessment `owner_name` via PIDN join (tier: parcel_link, 0.95)
- **Fuzzy fallback:** Name + address similarity scoped by municipality (tiers: exact, strong, fuzzy_name)
- **Address point bridge:** When `staging.address_points` has data, unmatched assessment records are geocoded through address points → `ST_Within` → parcel PIDN
- **PLCB cross-reference:** Normalized `licensee`/`premises_name` from `staging.plcb_licenses` matched against resolved owners by name + municipality (adds `source_type = 'plcb_license'` to `owner_source_links`)
- **Entity type classification:** Heuristic regex on canonical name → person/business/trust/government
- **Municipality scoping:** All fuzzy matches restricted to same municipality (requires municipality spatial join to have run first)

**Prerequisites (must run before entity resolution):**
1. `staging.parcels` loaded with `municipality` populated (requires municipalities pipeline + spatial join enrichment)
2. `staging.assessment_properties` loaded (when assessment pipeline is built)
3. `staging.address_points` loaded (optional — enhances matching but not required)
4. `staging.plcb_licenses` loaded (optional — adds cross-source links)

```python
@asset(
    group_name="enrichment",
    deps=["parcels_arcgis", "municipality_join"],  # Minimum deps for MVP
    description="Resolved owner entities across all available data sources",
)
def owners(context: AssetExecutionContext, database: DatabaseResource):
    """Run entity resolution across all loaded source tables."""

    # Detect which source tables actually have data
    available_sources = database.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'staging'
        AND table_name IN ('parcels', 'assessment_properties',
                           'address_points', 'plcb_licenses',
                           'deeds', 'business_filings', 'pals_licenses')
    """)
    source_tables = [row[0] for row in available_sources] if available_sources else []
    context.log.info(f"Running entity resolution against: {source_tables}")

    cur = database.cursor()
    try:
        # 1. Build candidate pairs via PIDN join + fuzzy matching (municipality-scoped)
        # 2. If address_points available, run address point bridge for unmatched records
        # 3. Cluster matches into entities (canonical name = most frequent normalized form)
        # 4. Classify entity type (person/business/trust/government)
        # 5. If plcb_licenses available, match licensees to resolved owners
        # 6. Write to public.owners + public.owner_source_links
        # 7. Update parcel_count on each owner
        ...
    finally:
        cur.close()
```

**Phase 2 enriched resolution (+ deeds, business filings, licenses):**
- Same matching logic, but with additional source tables feeding into the candidate pool
- Each new source type gets added to `owner_source_links.source_type` as its pipeline is built
- Adding a source to resolution = adding it to the deps list and a matching block in the SQL
- The Dagster asset dynamically detects which tables have data, so it won't break when Phase 2 tables don't exist yet

## Known limitations and when to upgrade

| Limitation | Impact | When to upgrade |
|---|---|---|
| No ML confidence scoring | Rigid tiers; edge cases fall through | When false positive/negative rate is unacceptable |
| No incremental matching | Full rebuild on every run | When dataset grows large enough that full rebuild is slow (>30 min) |
| No human-in-the-loop review | Ambiguous matches auto-resolved by tier | When match accuracy is critical for official use |
| Name abbreviation handling is limited | Custom abbreviation list needs maintenance | When common abbreviations cause consistent misses |
| No cross-county entity linking | Each county is a separate entity universe | When multi-county product is in scope |

**Upgrade path:** If deterministic matching isn't sufficient, the next step is **Zingg** (open-source, Spark-based ML matching). The schema doesn't change — Zingg would replace the matching logic in Stage 2, outputting to the same `owners` and `owner_source_links` tables. The normalization functions and schema are already designed to be tool-agnostic.
