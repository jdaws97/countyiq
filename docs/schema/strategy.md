# Schema & Identifier Strategy

### Schema Strategy

**Raw data goes to S3, not RDS.** Every pipeline run dumps its unmodified response to `s3://york-county-raw/<source>/<date>/`. This is the audit trail and replay source. No `raw` schema exists in RDS.

| Schema | Purpose | Example Tables |
|---|---|---|
| `staging` | Cleaned, normalized, change-tracked data (SCD Type 2). This is where all source data lives after parsing. | `staging.parcels`, `staging.assessment_properties`, `staging.flood_zones`, `staging.crimewatch_incidents` |
| `public` | Entity-resolved output and cross-source views | `public.owners`, `public.owner_source_links`, `public.properties` (view joining staging.parcels + staging.assessment_properties) |
| `meta` | Application metadata — NOT Dagster internals (those are in the separate `dagster` database) | `meta.infra_metrics`, `meta.pipeline_status`, `meta.data_quality_checks` |

**Where are the staging DDLs?** Individual staging table DDLs (e.g., `staging.parcels`, `staging.assessment_properties`) are created via Alembic migrations at build time — they're not pre-defined in documentation because their exact columns depend on what each data source actually returns. The `meta` schema DDL is pre-defined in `docs/schema/meta.md` because it's application-owned. Staging tables follow the SCD Type 2 pattern: source-specific columns + `valid_from TIMESTAMPTZ DEFAULT NOW()` + `valid_to TIMESTAMPTZ` (NULL = current). See `docs/schema/migrations.md` for the Alembic workflow.

**Note:** `public.properties` is a **PostgreSQL view**, not a table. It joins `staging.parcels` (geometry, ownership, sale history) with `staging.assessment_properties` (detailed assessment data, permits, delinquent taxes) on the canonical parcel identifier (PIDN). This avoids data duplication while providing a unified query target for the API.

```sql
-- public.properties is a VIEW, not a table
CREATE VIEW public.properties AS
SELECT
    p.pidn,
    p.geom,
    p.owner_full,
    p.propadr,
    p.aprtotal,
    p.saledt,
    p.price,
    p.municipality,
    p.school_dis,
    p.acres,
    p."class",
    a.permits,
    a.delinquent_taxes,
    a.value_history,
    p.valid_from,
    p.valid_to
FROM staging.parcels p
LEFT JOIN staging.assessment_properties a
    ON p.pidn = a.pidn
    AND a.valid_to IS NULL  -- Current assessment records only (SCD Type 2)
WHERE p.valid_to IS NULL;   -- Current parcel records only (SCD Type 2)
```

**Dagster metadata separation:** Dagster's internal database (`dagster` on the same RDS instance) stores run history, event logs, and schedule state. The `meta` schema in `york_county_intel` stores application-level summaries that the API can query — specifically, a Dagster sensor writes summarized pipeline status and infra metrics to `meta` tables. This keeps the API decoupled from Dagster's internal schema (which can change between Dagster versions).

### Identifier Strategy

**The canonical parcel identifier is PIDN** (Parcel ID Number), a 13-character string from the GIS data (e.g., `4300006006500`). This is the primary key for `staging.parcels` and the join key across all source tables.

The assessment database uses a different identifier — **PARID**, an 18-digit string (e.g., `46000060065000000`). PARID encodes the same district/block/map/parcel components as PIDN but in a different format with zero-padding.

**Crosswalk:** The PIDN and PARID contain the same underlying components:

```
PIDN format:    DD-BBB-MM-PPPPPP      (13 chars, from GIS DISTRICT+BLOCK+MAP+PARCEL fields)
PARID format:   DD000BBB0MM00PPPPPP   (18 digits, zero-padded, from Assessment portal)

Example:
  GIS:        PIDN = "4300006006500"
              DISTRICT=43, BLOCK=000, MAP=06, PARCEL=006500

  Assessment: PARID = "43000060065000000"
```

**Conversion function (used by the assessment pipeline on ingest):**

```sql
CREATE OR REPLACE FUNCTION staging.parid_to_pidn(parid TEXT) RETURNS TEXT AS $$
    -- Strip zero-padding to reconstruct PIDN from PARID
    SELECT CONCAT(
        SUBSTRING(parid FROM 1 FOR 2),     -- District (2 digits)
        SUBSTRING(parid FROM 4 FOR 3),     -- Block (3 digits, skip zero pad)
        SUBSTRING(parid FROM 8 FOR 2),     -- Map (2 digits, skip zero pad)
        SUBSTRING(parid FROM 11 FOR 6)     -- Parcel (6 digits)
    );
$$ LANGUAGE sql IMMUTABLE;
```

**All tables use PIDN as the join key.** The assessment pipeline converts PARID → PIDN on ingest. No table stores PARID as a primary key.

**Entity identifiers:**

| Entity | Primary Key | Type | Rationale |
|---|---|---|---|
| Parcels | `pidn` | TEXT(13) | Natural key from GIS; stable across refreshes |
| Owners (resolved entities) | `owner_id` | SERIAL | Synthetic key; entities are created by resolution, not by any source |
| Source links | `link_id` | SERIAL | Synthetic key for the join table |
| All staging tables | Source-specific natural key + `valid_from` | Varies | SCD Type 2 requires composite key |

**Why SERIAL (not UUID) for owners:** Owner entities are created and consumed entirely within this platform. They're never shared with external systems. SERIAL is simpler, uses less storage, and is faster for joins. If CountyIQ ever needs to federate owner data across county instances, UUIDs can be added as an additional column without changing the primary key.

---
