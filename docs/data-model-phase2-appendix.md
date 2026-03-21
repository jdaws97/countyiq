# CountyIQ — Data Model Reference

> **⚠️ IMPORTANT: This document is partially outdated.**
>
> This was the original data model design document, written before the infrastructure plan was finalized. **The docs/ directory (specifically docs/schema/ and docs/infrastructure/) is the authoritative architecture reference.** Where the two documents conflict, the authoritative docs win.
>
> **Key differences from the current architecture:**
>
> | This Document Says | Current Architecture (Infra Plan) |
> |---|---|
> | UUIDs for all entity primary keys | `SERIAL` for `owner_id` (internal-only, no cross-system federation) |
> | `entity_relationships` adjacency list table | `owner_source_links` table (simpler, source-scoped) |
> | Cognito/Clerk authentication with `users` table | No auth for MVP; Cognito deferred to Phase 2 |
> | Graph-traversal queries via recursive CTEs on `entity_relationships` | Owner linkage via `owner_source_links` join; graph engine (Memgraph) only in Phase 3 if needed |
> | Neon PostgreSQL (serverless) | AWS RDS PostgreSQL (db.t3.micro) |
> | `raw.*` schema in database | No `raw` schema — raw data goes to S3 only; `staging.*` is first RDS schema |
> | `public.properties` as a materialized table | `public.properties` as a VIEW joining `staging.parcels` + `staging.assessment_properties` |
> | PARID as primary parcel key | PIDN (13-char from GIS) is canonical; PARID→PIDN conversion function in infra plan |
>
> **What's still valid here:** The general table structures for Phase 2/3 expansion (business entities, permits, court records, etc.) are useful as a design reference for the entity types and column schemas. The SQL query examples demonstrate the kinds of cross-referencing CountyIQ enables. The Phase 1–3 progression is still the correct roadmap. Just be aware that identifiers, relationships, and infrastructure details have changed.
>
> **Role of this document going forward:** This is a **Phase 2/3 design appendix** — a reference for future entity types and column schemas when expanding beyond the MVP. The infra plan is the single-source-of-truth for all MVP schema (staging tables, public views, meta tables, entity resolution). Do not use this document to make implementation decisions about MVP.

## Architecture Overview

**Database:** PostgreSQL 16+ with PostGIS (spatial) + pg_trgm on AWS RDS (db.t3.micro, 20 GB gp3)

**Infrastructure:** AWS (RDS for database, EC2 for Dagster orchestration, S3 for raw data/static site/tiles, Lambda for FastAPI API, CloudFront for CDN, no auth for MVP)

**Design Principles:**
- RDS PostgreSQL is the single database — no separate graph, search, or NoSQL databases to operate
- PostGIS handles all spatial queries (flood zones, proximity, containment)
- Entity relationships modeled as an adjacency list table with recursive CTEs for multi-hop traversal (Phases 1-2); dedicated graph engine (Memgraph) introduced only in Phase 3 if query complexity demands it
- Every entity gets a stable UUID from day one, even before entity resolution is mature
- All tables include `created_at`, `updated_at`, and `source_id` for full provenance tracking
- Schema is append-friendly: historical records are never deleted, only superseded
- `raw_data JSONB` on source tables preserves original data for re-extraction as parsing improves

**Naming Conventions:**
- Relational tables: `snake_case` (e.g., `parcels`, `source_records`)
- Relationship types: `UPPER_SNAKE_CASE` stored as TEXT (e.g., `'OWNS'`, `'IS_PARTY_TO'`)
- These relationship type names are designed to map directly to graph edge labels if/when a dedicated graph engine is introduced in Phase 3

---

## Phase 1: MVP — Unified Property Intelligence

**Goal:** Every parcel in York County as a clickable, searchable entity with unified assessment, spatial, and ownership data. Cross-referencing that the county's own siloed tools can't do.

**Estimated record volumes:** ~175,000 parcels, ~175,000 assessment records, ~10 spatial reference layers, ~200,000 owner name records (pre-resolution).

**Infrastructure cost:** ~$0–7/month Year 1 (RDS + EC2 free tier, WAF ~$6.60); ~$32–36/month Year 2+ (see Infrastructure Plan, Cost Breakdown section)

### Relational Schema

```sql
-- =============================================================
-- AUTHENTICATION & USERS (deferred — no auth for MVP; consider Cognito or Clerk later)
-- =============================================================

CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_provider_id    TEXT NOT NULL UNIQUE,     -- from auth provider (Cognito/Clerk) — not implemented in MVP
    email               TEXT NOT NULL UNIQUE,
    display_name        TEXT,
    role                TEXT NOT NULL DEFAULT 'citizen',
                                                  -- 'admin', 'government', 'professional', 'citizen'
    organization        TEXT,                     -- firm name, township name, agency, etc.
    organization_type   TEXT,                     -- 'municipality', 'law_firm', 'real_estate', 'mortgage', 'other'
    stated_purpose      TEXT,                     -- required at signup: why they need access
    subscription_tier   TEXT DEFAULT 'free',      -- 'free', 'professional', 'government', 'enterprise'
    is_active           BOOLEAN DEFAULT true,
    last_login_at       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_users_auth ON users (auth_provider_id);
CREATE INDEX idx_users_email ON users (email);

CREATE TABLE user_permissions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    permission      TEXT NOT NULL,
    -- MVP permissions:
    --   'view_parcels', 'view_assessments', 'view_sales',
    --   'search_entities', 'export_basic'
    -- Phase 2 additions:
    --   'view_court_records', 'view_entity_profiles', 'view_documents',
    --   'create_alerts', 'export_advanced'
    -- Phase 3 additions:
    --   'natural_language_query', 'view_predictions', 'admin_panel'
    granted_at      TIMESTAMPTZ DEFAULT now(),
    granted_by      UUID REFERENCES users(id),   -- admin who granted, null if auto-granted by tier
    UNIQUE(user_id, permission)
);

-- Maps subscription tiers to default permissions (auto-granted on signup/upgrade)
CREATE TABLE tier_permissions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tier            TEXT NOT NULL,
    permission      TEXT NOT NULL,
    UNIQUE(tier, permission)
);

-- =============================================================
-- CORE REFERENCE TABLES
-- =============================================================

CREATE TABLE data_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,         -- 'yc_gis_parcels', 'yc_assessment', 'fema_nfhl'
    source_type     TEXT NOT NULL,                -- 'gis_layer', 'database', 'api', 'bulk_file', 'scrape'
    base_url        TEXT,
    refresh_cadence TEXT,                         -- 'daily', 'weekly', 'monthly', 'quarterly', 'on_demand'
    last_ingested   TIMESTAMPTZ,
    legal_basis     TEXT,                         -- 'public_record', 'right_to_know', 'open_data_portal', 'bulk_request'
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE municipalities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,                -- 'Spring Garden Township'
    municipal_code  TEXT UNIQUE,                  -- county-assigned code
    type            TEXT NOT NULL,                -- 'township', 'borough', 'city'
    geometry        GEOMETRY(MultiPolygon, 4326),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE school_districts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    district_code   TEXT UNIQUE,
    geometry        GEOMETRY(MultiPolygon, 4326),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE zoning_districts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    municipality_id UUID REFERENCES municipalities(id),
    zone_code       TEXT NOT NULL,                -- 'R-1', 'C-2', 'I-1'
    zone_name       TEXT,                         -- 'Single Family Residential'
    zone_category   TEXT,                         -- 'residential', 'commercial', 'industrial', 'agricultural', 'mixed'
    geometry        GEOMETRY(MultiPolygon, 4326),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE flood_zones (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_code       TEXT NOT NULL,                -- 'A', 'AE', 'X', 'VE'
    zone_desc       TEXT,                         -- 'Special Flood Hazard Area'
    is_high_risk    BOOLEAN NOT NULL DEFAULT false,
    geometry        GEOMETRY(MultiPolygon, 4326),
    source_id       UUID REFERENCES data_sources(id),
    effective_date  DATE,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- PARCEL — THE ANCHOR ENTITY
-- =============================================================

CREATE TABLE parcels (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id       TEXT NOT NULL UNIQUE,         -- county map/parcel number (e.g., '54-000-02-0067.00-00000')
    municipality_id UUID REFERENCES municipalities(id),
    school_district_id UUID REFERENCES school_districts(id),
    address_full    TEXT,                         -- normalized full address
    address_street  TEXT,
    address_city    TEXT,
    address_zip     TEXT,
    acreage         NUMERIC(10,4),
    land_use_code   TEXT,                         -- county land use classification
    land_use_desc   TEXT,
    zoning_code     TEXT,                         -- current zoning designation
    geometry        GEOMETRY(MultiPolygon, 4326),
    centroid        GEOMETRY(Point, 4326),        -- pre-computed for fast point queries
    source_id       UUID REFERENCES data_sources(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_parcels_geometry ON parcels USING GIST (geometry);
CREATE INDEX idx_parcels_centroid ON parcels USING GIST (centroid);
CREATE INDEX idx_parcels_parcel_id ON parcels (parcel_id);
CREATE INDEX idx_parcels_municipality ON parcels (municipality_id);
CREATE INDEX idx_parcels_zip ON parcels (address_zip);

-- =============================================================
-- ASSESSMENT RECORDS (HISTORICAL)
-- =============================================================

CREATE TABLE assessments (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id            UUID NOT NULL REFERENCES parcels(id),
    tax_year             INTEGER NOT NULL,
    owner_name_raw       TEXT,                    -- raw owner name as it appears in assessment
    owner_name_2_raw     TEXT,                    -- secondary owner if present
    assessed_land        NUMERIC(12,2),
    assessed_improvement NUMERIC(12,2),
    assessed_total       NUMERIC(12,2),
    market_value         NUMERIC(12,2),           -- if provided
    tax_amount           NUMERIC(12,2),
    homestead_exemption  BOOLEAN DEFAULT false,
    property_class       TEXT,                    -- 'residential', 'commercial', etc.
    year_built           INTEGER,
    living_area_sqft     INTEGER,
    bedrooms             INTEGER,
    bathrooms            NUMERIC(3,1),
    source_id            UUID REFERENCES data_sources(id),
    is_current           BOOLEAN DEFAULT true,    -- latest assessment for this parcel
    created_at           TIMESTAMPTZ DEFAULT now(),
    updated_at           TIMESTAMPTZ DEFAULT now(),
    UNIQUE(parcel_id, tax_year)
);

CREATE INDEX idx_assessments_parcel ON assessments (parcel_id);
CREATE INDEX idx_assessments_current ON assessments (parcel_id) WHERE is_current = true;
CREATE INDEX idx_assessments_owner ON assessments USING gin (owner_name_raw gin_trgm_ops);

-- =============================================================
-- ENTITIES (RESOLVED PEOPLE & ORGANIZATIONS)
-- =============================================================

CREATE TABLE entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     TEXT NOT NULL,                -- 'person', 'organization', 'government', 'trust'
    canonical_name  TEXT NOT NULL,                -- best/resolved name
    name_variants   TEXT[],                       -- all known name spellings
    entity_status   TEXT DEFAULT 'active',        -- 'active', 'merged', 'inactive'
    merged_into_id  UUID REFERENCES entities(id), -- if this entity was merged into another
    confidence      NUMERIC(3,2),                 -- entity resolution confidence (0.00-1.00)
    metadata        JSONB DEFAULT '{}',           -- flexible attributes per entity type
    source_ids      UUID[],                       -- which data sources contributed to this entity
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_entities_name ON entities USING gin (canonical_name gin_trgm_ops);
CREATE INDEX idx_entities_type ON entities (entity_type);
CREATE INDEX idx_entities_variants ON entities USING gin (name_variants);

-- Links raw source records to resolved entities
CREATE TABLE entity_source_links (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id        UUID NOT NULL REFERENCES entities(id),
    source_table     TEXT NOT NULL,               -- 'assessments', 'deed_records', etc.
    source_record_id UUID NOT NULL,               -- PK of the source record
    name_as_appears  TEXT NOT NULL,               -- the raw name string that matched
    match_score      NUMERIC(3,2),                -- similarity score
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- ENTITY RELATIONSHIPS (adjacency list — replaces graph DB for Phases 1-2)
--
-- This is the core relationship table that models all connections
-- between entities, parcels, and other objects. It serves the same
-- purpose as graph edges in a graph database. For multi-hop queries,
-- use recursive CTEs (see example queries below).
--
-- When/if Phase 3 introduces a dedicated graph engine (e.g., Memgraph),
-- this table becomes the source-of-truth that syncs into the graph.
-- The relationship_type values map directly to graph edge labels.
-- =============================================================

CREATE TABLE entity_relationships (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Source side: always an entity (person, org, trust, government)
    entity_id            UUID NOT NULL REFERENCES entities(id),
    -- Target side: polymorphic — exactly one of these should be non-null
    related_entity_id    UUID REFERENCES entities(id),
    related_parcel_id    UUID REFERENCES parcels(id),
    related_case_id      UUID,                    -- FK added in Phase 2 when court_cases table exists
    related_document_id  UUID,                    -- FK added in Phase 2 when recorded_documents table exists
    related_business_id  UUID,                    -- FK added in Phase 2 when business_entities table exists
    -- Relationship metadata
    relationship_type    TEXT NOT NULL,            -- Phase 1 types:
                                                  --   'OWNS', 'CO_OWNS', 'PREVIOUSLY_OWNED',
                                                  --   'SOLD_TO', 'BOUGHT_FROM',
                                                  --   'LIKELY_SAME_AS' (low-confidence entity match)
                                                  -- Phase 2 adds:
                                                  --   'IS_PARTY_TO', 'GRANTOR_OF', 'GRANTEE_OF',
                                                  --   'LIENHOLDER_OF', 'OFFICER_OF', 'MEMBER_OF',
                                                  --   'AGENT_FOR', 'APPLIED_FOR', 'CO_DEFENDANT',
                                                  --   'TRANSACTED_WITH', 'SHARES_ADDRESS',
                                                  --   'BUSINESS_ASSOCIATE'
    properties           JSONB DEFAULT '{}',      -- edge properties: role, confidence, context
    effective_date       DATE,
    end_date             DATE,                    -- null if current/ongoing
    is_current           BOOLEAN DEFAULT true,
    source_id            UUID REFERENCES data_sources(id),
    created_at           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_rel_entity ON entity_relationships (entity_id);
CREATE INDEX idx_rel_related_entity ON entity_relationships (related_entity_id);
CREATE INDEX idx_rel_parcel ON entity_relationships (related_parcel_id);
CREATE INDEX idx_rel_type ON entity_relationships (relationship_type);
CREATE INDEX idx_rel_current ON entity_relationships (entity_id, relationship_type) WHERE is_current = true;

-- Composite index for the most common traversal pattern:
-- "given this entity, find all current relationships of type X"
CREATE INDEX idx_rel_entity_type_current ON entity_relationships (entity_id, relationship_type)
    WHERE is_current = true;

-- =============================================================
-- PARCEL-ENTITY OWNERSHIP (convenience view over entity_relationships)
-- Kept as a table for backward compatibility and fast ownership lookups,
-- but ownership is ALSO recorded in entity_relationships for graph traversal.
-- Dagster pipeline keeps both in sync.
-- =============================================================

CREATE TABLE parcel_ownership (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id       UUID NOT NULL REFERENCES parcels(id),
    entity_id       UUID NOT NULL REFERENCES entities(id),
    ownership_type  TEXT DEFAULT 'owner',         -- 'owner', 'co-owner' (expands in later phases)
    effective_date  DATE,
    end_date        DATE,                         -- null if current
    is_current      BOOLEAN DEFAULT true,
    source_id       UUID REFERENCES data_sources(id),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_ownership_parcel ON parcel_ownership (parcel_id);
CREATE INDEX idx_ownership_entity ON parcel_ownership (entity_id);
CREATE INDEX idx_ownership_current ON parcel_ownership (parcel_id) WHERE is_current = true;

-- =============================================================
-- SPATIAL OVERLAY RESULTS (pre-computed)
-- =============================================================

CREATE TABLE parcel_spatial_overlays (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id       UUID NOT NULL REFERENCES parcels(id),
    overlay_type    TEXT NOT NULL,                -- 'flood_zone', 'school_district', 'municipality'
    overlay_id      UUID NOT NULL,                -- FK to the relevant spatial table
    overlap_pct     NUMERIC(5,2),                 -- % of parcel in this zone
    computed_at     TIMESTAMPTZ DEFAULT now(),
    UNIQUE(parcel_id, overlay_type, overlay_id)
);

-- =============================================================
-- SALES HISTORY (from assessment/deed data available in MVP)
-- =============================================================

CREATE TABLE sales (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id        UUID NOT NULL REFERENCES parcels(id),
    sale_date        DATE,
    sale_price       NUMERIC(14,2),
    buyer_raw        TEXT,
    seller_raw       TEXT,
    buyer_entity_id  UUID REFERENCES entities(id),
    seller_entity_id UUID REFERENCES entities(id),
    deed_book        TEXT,
    deed_page        TEXT,
    instrument_type  TEXT,                        -- 'warranty_deed', 'quit_claim', etc.
    source_id        UUID REFERENCES data_sources(id),
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_sales_parcel ON sales (parcel_id);
CREATE INDEX idx_sales_date ON sales (sale_date DESC);

-- =============================================================
-- INGESTION TRACKING & DATA QUALITY
-- =============================================================

CREATE TABLE ingestion_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL REFERENCES data_sources(id),
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    status          TEXT DEFAULT 'running',       -- 'running', 'completed', 'failed', 'partial'
    records_fetched INTEGER DEFAULT 0,
    records_created INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_skipped INTEGER DEFAULT 0,
    errors          JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE data_quality_issues (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_run_id UUID REFERENCES ingestion_runs(id),
    source_table     TEXT NOT NULL,
    source_record_id UUID,
    issue_type       TEXT NOT NULL,               -- 'missing_parcel_link', 'name_parse_failure',
                                                  -- 'duplicate_detected', 'geocode_failed'
    severity         TEXT DEFAULT 'warning',       -- 'info', 'warning', 'error'
    description      TEXT,
    resolved         BOOLEAN DEFAULT false,
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- BASIC ACCESS LOGGING (MVP — lightweight, expanded in Phase 2)
-- =============================================================

CREATE TABLE access_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    action_type     TEXT NOT NULL,                -- 'search', 'view_parcel', 'view_entity', 'export'
    target_type     TEXT,                         -- 'parcel', 'entity'
    target_id       UUID,
    query_text      TEXT,
    ip_address      INET,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_access_log_user ON access_log (user_id, created_at DESC);
```

### MVP Example Queries

```sql
-- "Show me all properties in 17404 in the flood zone"
SELECT p.parcel_id, p.address_full, a.assessed_total, fz.zone_code
FROM parcels p
JOIN parcel_spatial_overlays pso ON pso.parcel_id = p.id
    AND pso.overlay_type = 'flood_zone'
JOIN flood_zones fz ON fz.id = pso.overlay_id
    AND fz.is_high_risk = true
LEFT JOIN assessments a ON a.parcel_id = p.id AND a.is_current = true
WHERE p.address_zip = '17404';

-- "All properties owned by this entity"
SELECT p.parcel_id, p.address_full, p.acreage, a.assessed_total
FROM entities e
JOIN parcel_ownership po ON po.entity_id = e.id AND po.is_current = true
JOIN parcels p ON p.id = po.parcel_id
LEFT JOIN assessments a ON a.parcel_id = p.id AND a.is_current = true
WHERE e.canonical_name ILIKE '%smith%';

-- "Who else owns property on the same street as this parcel?"
SELECT DISTINCT e.canonical_name, p2.address_full, a.assessed_total
FROM parcels p1
JOIN parcels p2 ON p2.address_street = p1.address_street
    AND p2.id != p1.id
JOIN parcel_ownership po ON po.parcel_id = p2.id AND po.is_current = true
JOIN entities e ON e.id = po.entity_id
LEFT JOIN assessments a ON a.parcel_id = p2.id AND a.is_current = true
WHERE p1.parcel_id = '54-000-02-0067.00-00000';

-- "Parcels within 500 meters of a specific property"
SELECT p2.parcel_id, p2.address_full,
    ST_Distance(p1.centroid::geography, p2.centroid::geography) AS distance_m
FROM parcels p1, parcels p2
WHERE p1.parcel_id = '54-000-02-0067.00-00000'
    AND p1.id != p2.id
    AND ST_DWithin(p1.centroid::geography, p2.centroid::geography, 500)
ORDER BY distance_m;

-- "Entity relationship traversal: all entities connected within 2 hops"
-- (recursive CTE — equivalent to graph traversal without AGE)
WITH RECURSIVE entity_network AS (
    -- Seed: direct relationships of the target entity
    SELECT
        er.entity_id AS source_id,
        er.related_entity_id AS target_id,
        er.relationship_type,
        1 AS depth,
        ARRAY[er.entity_id] AS path
    FROM entity_relationships er
    WHERE er.entity_id = (SELECT id FROM entities WHERE canonical_name = 'John Smith' LIMIT 1)
        AND er.related_entity_id IS NOT NULL
        AND er.is_current = true

    UNION ALL

    -- Recursive: one more hop from discovered entities
    SELECT
        er.entity_id,
        er.related_entity_id,
        er.relationship_type,
        en.depth + 1,
        en.path || er.entity_id
    FROM entity_relationships er
    JOIN entity_network en ON er.entity_id = en.target_id
    WHERE en.depth < 2
        AND er.related_entity_id IS NOT NULL
        AND er.is_current = true
        AND er.entity_id != ALL(en.path)  -- prevent cycles
)
SELECT DISTINCT
    e.canonical_name,
    e.entity_type,
    en.relationship_type,
    en.depth
FROM entity_network en
JOIN entities e ON e.id = en.target_id
ORDER BY en.depth, e.canonical_name;
```

---

## Phase 2: Intermediate — Activity & Relationship Layer

**Goal:** Bring in court records, deeds, liens, business registrations, permits, and government actions. Build the full entity relationship network. Enable monitoring, alerting, and anti-misuse detection.

**New record volumes:** ~500K+ court docket entries (historical), ~300K deed/mortgage records, ~50K business entities, ~10K permits/year, growing daily via ingestion pipelines.

**Infrastructure cost:** ~$40-80/month (RDS storage growth, S3 growth, potential t3.small upgrade — see Infrastructure Plan for detailed breakdown)

### New Tables

```sql
-- =============================================================
-- COURT CASES (from UJS Portal bulk data request)
-- =============================================================

CREATE TABLE court_cases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    docket_number   TEXT NOT NULL UNIQUE,         -- 'CP-67-CR-001234-2024'
    court_system    TEXT NOT NULL,                -- 'cpcms' (Common Pleas), 'mdjs' (Magisterial District)
    case_type       TEXT NOT NULL,                -- 'civil', 'criminal', 'family', 'orphans', 'landlord_tenant'
    case_subtype    TEXT,                         -- 'contract', 'tort', 'real_property', 'mortgage_foreclosure'
    case_status     TEXT,                         -- 'active', 'closed', 'adjudicated', 'inactive'
    filing_date     DATE,
    disposition_date DATE,
    county          TEXT DEFAULT 'York',
    judge           TEXT,
    description     TEXT,                         -- short summary if available
    source_id       UUID REFERENCES data_sources(id),
    raw_data        JSONB,                        -- full docket data as ingested
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_cases_docket ON court_cases (docket_number);
CREATE INDEX idx_cases_type ON court_cases (case_type, case_subtype);
CREATE INDEX idx_cases_filing ON court_cases (filing_date DESC);
CREATE INDEX idx_cases_status ON court_cases (case_status) WHERE case_status = 'active';

-- Parties to court cases
CREATE TABLE case_parties (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id         UUID NOT NULL REFERENCES court_cases(id),
    party_name_raw  TEXT NOT NULL,
    party_role      TEXT NOT NULL,                -- 'plaintiff', 'defendant', 'petitioner', 'respondent'
    party_type      TEXT,                         -- 'individual', 'organization', 'government'
    entity_id       UUID REFERENCES entities(id), -- linked after entity resolution
    attorney_name   TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_case_parties_case ON case_parties (case_id);
CREATE INDEX idx_case_parties_entity ON case_parties (entity_id);
CREATE INDEX idx_case_parties_name ON case_parties USING gin (party_name_raw gin_trgm_ops);

-- =============================================================
-- RECORDED DOCUMENTS (Deeds, Mortgages, Liens, UCCs)
-- =============================================================

CREATE TABLE recorded_documents (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_type    TEXT NOT NULL,             -- 'deed', 'mortgage', 'lien', 'ucc', 'satisfaction',
                                                  -- 'release', 'assignment', 'lis_pendens', 'easement'
    instrument_subtype TEXT,                      -- 'warranty_deed', 'quit_claim', 'sheriffs_deed',
                                                  -- 'mechanics_lien', 'tax_lien', 'judgment_lien'
    recording_date     DATE,
    book               TEXT,
    page               TEXT,
    instrument_number  TEXT,
    consideration      NUMERIC(14,2),             -- dollar amount if applicable
    parcel_id          UUID REFERENCES parcels(id),
    legal_description  TEXT,                      -- raw legal description from document
    source_id          UUID REFERENCES data_sources(id),
    raw_data           JSONB,
    created_at         TIMESTAMPTZ DEFAULT now(),
    updated_at         TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_docs_type ON recorded_documents (instrument_type);
CREATE INDEX idx_docs_parcel ON recorded_documents (parcel_id);
CREATE INDEX idx_docs_recording ON recorded_documents (recording_date DESC);
CREATE INDEX idx_docs_book_page ON recorded_documents (book, page);

-- Parties to recorded documents
CREATE TABLE document_parties (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES recorded_documents(id),
    party_name_raw  TEXT NOT NULL,
    party_role      TEXT NOT NULL,                -- 'grantor', 'grantee', 'mortgagor', 'mortgagee',
                                                  -- 'lienor', 'lienee', 'assignor', 'assignee'
    entity_id       UUID REFERENCES entities(id),
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- BUSINESS ENTITIES (from PA DOS / OpenCorporates)
-- =============================================================

CREATE TABLE business_entities (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id            UUID REFERENCES entities(id),
    state_entity_number  TEXT,                    -- PA DOS entity ID
    business_name        TEXT NOT NULL,
    business_type        TEXT,                    -- 'llc', 'corporation', 'lp', 'nonprofit', 'partnership'
    status               TEXT,                    -- 'active', 'dissolved', 'forfeited', 'suspended'
    formation_date       DATE,
    dissolution_date     DATE,
    registered_address   TEXT,
    registered_agent     TEXT,
    jurisdiction         TEXT DEFAULT 'PA',
    source_id            UUID REFERENCES data_sources(id),
    raw_data             JSONB,
    created_at           TIMESTAMPTZ DEFAULT now(),
    updated_at           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_biz_name ON business_entities USING gin (business_name gin_trgm_ops);
CREATE INDEX idx_biz_entity ON business_entities (entity_id);

-- Officers/principals of business entities
CREATE TABLE business_officers (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_entity_id UUID NOT NULL REFERENCES business_entities(id),
    officer_name_raw   TEXT NOT NULL,
    officer_role       TEXT,                      -- 'member', 'manager', 'president', 'director', 'agent'
    entity_id          UUID REFERENCES entities(id),
    effective_date     DATE,
    end_date           DATE,
    created_at         TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- PERMITS & GOVERNMENT ACTIONS
-- =============================================================

CREATE TABLE permits (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    permit_number       TEXT,
    permit_type         TEXT NOT NULL,            -- 'building', 'demolition', 'electrical', 'plumbing',
                                                  -- 'zoning', 'occupancy', 'grading'
    status              TEXT,                     -- 'applied', 'issued', 'inspection_scheduled', 'final', 'denied'
    parcel_id           UUID REFERENCES parcels(id),
    applicant_raw       TEXT,
    applicant_entity_id UUID REFERENCES entities(id),
    description         TEXT,
    estimated_cost      NUMERIC(14,2),
    applied_date        DATE,
    issued_date         DATE,
    completed_date      DATE,
    municipality_id     UUID REFERENCES municipalities(id),
    source_id           UUID REFERENCES data_sources(id),
    raw_data            JSONB,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE government_actions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_type     TEXT NOT NULL,                -- 'code_violation', 'zoning_variance', 'rezoning',
                                                  -- 'conditional_use', 'subdivision', 'tax_claim',
                                                  -- 'sheriff_sale', 'upset_sale'
    status          TEXT,                         -- 'pending', 'approved', 'denied', 'resolved', 'scheduled'
    parcel_id       UUID REFERENCES parcels(id),
    entity_id       UUID REFERENCES entities(id),
    municipality_id UUID REFERENCES municipalities(id),
    description     TEXT,
    action_date     DATE,
    resolution_date DATE,
    monetary_amount NUMERIC(14,2),                -- tax claim amount, sale price, fine, etc.
    source_id       UUID REFERENCES data_sources(id),
    raw_data        JSONB,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- USER ALERTS & MONITORING (the product layer)
-- =============================================================

CREATE TABLE user_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    alert_name      TEXT NOT NULL,
    alert_type      TEXT NOT NULL,                -- 'entity_activity', 'parcel_change', 'area_filings',
                                                  -- 'new_liens', 'new_sales', 'permit_activity'
    filter_criteria JSONB NOT NULL,
    -- Example: {"entity_ids": ["..."], "watch_types": ["court_filing", "lien"]}
    -- Example: {"zip_codes": ["17404"], "event_types": ["sale", "permit"]}
    -- Example: {"municipality_id": "...", "action_types": ["code_violation"]}
    delivery_method TEXT DEFAULT 'in_app',        -- 'in_app', 'email', 'both'
    is_active       BOOLEAN DEFAULT true,
    last_triggered  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE alert_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id            UUID NOT NULL REFERENCES user_alerts(id),
    event_type          TEXT NOT NULL,
    event_summary       TEXT NOT NULL,
    event_data          JSONB,
    source_record_table TEXT,
    source_record_id    UUID,
    is_read             BOOLEAN DEFAULT false,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- AUDIT & ANTI-MISUSE (expanded from MVP access_log)
-- =============================================================

-- Replaces the MVP access_log with richer auditing
CREATE TABLE access_audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    action_type     TEXT NOT NULL,                -- 'search', 'view_entity', 'view_parcel',
                                                  -- 'view_case', 'view_document',
                                                  -- 'export', 'alert_create', 'query'
    target_type     TEXT,                         -- 'entity', 'parcel', 'court_case', 'document'
    target_id       UUID,
    query_text      TEXT,                         -- what they searched for
    ip_address      INET,
    user_agent      TEXT,
    flagged         BOOLEAN DEFAULT false,        -- anti-misuse flag
    flag_reason     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_audit_user ON access_audit_log (user_id, created_at DESC);
CREATE INDEX idx_audit_target ON access_audit_log (target_type, target_id);
CREATE INDEX idx_audit_flagged ON access_audit_log (created_at DESC) WHERE flagged = true;

-- Misuse detection rules engine
CREATE TABLE misuse_patterns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_name    TEXT NOT NULL,                -- 'single_person_stalking', 'bulk_scraping',
                                                  -- 'excessive_exports', 'entity_profiling'
    description     TEXT,                         -- human-readable explanation of what this detects
    detection_rule  JSONB NOT NULL,
    -- Example: {"type": "entity_lookup_frequency", "threshold": 10,
    --           "window_minutes": 60, "same_target": true}
    -- Example: {"type": "cross_record_profiling", "threshold": 5,
    --           "record_types": ["court_case", "parcel", "business"],
    --           "window_minutes": 30, "same_entity": true}
    -- Example: {"type": "export_volume", "threshold": 1000,
    --           "window_minutes": 1440}
    severity        TEXT DEFAULT 'warning',       -- 'info', 'warning', 'critical'
    action          TEXT DEFAULT 'flag',          -- 'flag', 'rate_limit', 'block', 'notify_admin'
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Log of triggered misuse detections
CREATE TABLE misuse_incidents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_id      UUID NOT NULL REFERENCES misuse_patterns(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    triggered_at    TIMESTAMPTZ DEFAULT now(),
    action_taken    TEXT NOT NULL,                -- what action was taken
    evidence        JSONB,                        -- audit log IDs, query patterns, etc.
    resolved        BOOLEAN DEFAULT false,
    resolved_by     UUID REFERENCES users(id),   -- admin who reviewed
    resolution_note TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Add foreign key constraints to entity_relationships for Phase 2 targets
-- (These were left as untyped UUIDs in Phase 1)
ALTER TABLE entity_relationships
    ADD CONSTRAINT fk_rel_case FOREIGN KEY (related_case_id) REFERENCES court_cases(id),
    ADD CONSTRAINT fk_rel_document FOREIGN KEY (related_document_id) REFERENCES recorded_documents(id),
    ADD CONSTRAINT fk_rel_business FOREIGN KEY (related_business_id) REFERENCES business_entities(id);

CREATE INDEX idx_rel_case ON entity_relationships (related_case_id);
CREATE INDEX idx_rel_document ON entity_relationships (related_document_id);
CREATE INDEX idx_rel_business ON entity_relationships (related_business_id);
```

### Phase 2 Example Queries

```sql
-- "Show me all properties with active liens owned by entities
--  that also have pending civil litigation"
SELECT DISTINCT
    e.canonical_name,
    p.address_full,
    rd.instrument_subtype AS lien_type,
    cc.docket_number,
    cc.case_subtype
FROM entities e
JOIN parcel_ownership po ON po.entity_id = e.id AND po.is_current = true
JOIN parcels p ON p.id = po.parcel_id
JOIN recorded_documents rd ON rd.parcel_id = p.id
    AND rd.instrument_type = 'lien'
JOIN case_parties cp ON cp.entity_id = e.id AND cp.party_role = 'defendant'
JOIN court_cases cc ON cc.id = cp.case_id
    AND cc.case_status = 'active'
    AND cc.case_type = 'civil';

-- "Properties in Spring Garden Twp with new permits in last 90 days
--  where owner has code violations elsewhere"
SELECT p.address_full, pm.permit_type, pm.description,
    ga.action_type, p2.address_full AS violation_address
FROM permits pm
JOIN parcels p ON p.id = pm.parcel_id
JOIN municipalities m ON m.id = p.municipality_id
JOIN parcel_ownership po ON po.parcel_id = p.id AND po.is_current = true
JOIN parcel_ownership po2 ON po2.entity_id = po.entity_id AND po2.is_current = true
JOIN parcels p2 ON p2.id = po2.parcel_id
JOIN government_actions ga ON ga.parcel_id = p2.id
    AND ga.action_type = 'code_violation'
    AND ga.status != 'resolved'
WHERE m.name = 'Spring Garden Township'
    AND pm.issued_date >= CURRENT_DATE - INTERVAL '90 days';

-- "Find the full network of this entity: properties, cases, businesses,
--  and connected people — 2 hops deep"
WITH RECURSIVE network AS (
    -- Direct relationships (hop 1)
    SELECT
        er.entity_id AS from_id,
        er.related_entity_id AS to_entity,
        er.related_parcel_id AS to_parcel,
        er.related_case_id AS to_case,
        er.related_business_id AS to_business,
        er.relationship_type,
        1 AS depth,
        ARRAY[er.entity_id] AS visited
    FROM entity_relationships er
    WHERE er.entity_id = :target_entity_id
        AND er.is_current = true

    UNION ALL

    -- Hop 2: follow entity-to-entity links one more level
    SELECT
        er.entity_id,
        er.related_entity_id,
        er.related_parcel_id,
        er.related_case_id,
        er.related_business_id,
        er.relationship_type,
        n.depth + 1,
        n.visited || er.entity_id
    FROM entity_relationships er
    JOIN network n ON er.entity_id = n.to_entity
    WHERE n.depth < 2
        AND er.is_current = true
        AND er.entity_id != ALL(n.visited)
)
SELECT
    n.depth,
    n.relationship_type,
    -- Entity details
    e.canonical_name AS connected_entity,
    e.entity_type,
    -- Parcel details
    p.address_full AS connected_parcel,
    -- Case details
    cc.docket_number AS connected_case,
    cc.case_type,
    -- Business details
    be.business_name AS connected_business
FROM network n
LEFT JOIN entities e ON e.id = n.to_entity
LEFT JOIN parcels p ON p.id = n.to_parcel
LEFT JOIN court_cases cc ON cc.id = n.to_case
LEFT JOIN business_entities be ON be.id = n.to_business
ORDER BY n.depth, n.relationship_type;
```

---

## Phase 3: Grand Vision — Civic Intelligence Platform

**Goal:** Natural language querying, temporal analysis, predictive models, satellite imagery change detection, real-time feeds, and a full knowledge graph that any user can explore conversationally.

**Infrastructure evolution:** Consider adding Memgraph (open source, containerized) for complex graph algorithms (shortest path, community detection, PageRank-style influence scoring) if recursive CTE performance degrades at scale. Memgraph syncs from the `entity_relationships` table — it's a read-optimized cache, not a source of truth.

**Infrastructure cost:** ~$100-200+/month (RDS scale, S3 imagery storage, optional Memgraph container, ML compute on spot instances)

### New Tables

```sql
-- =============================================================
-- TEMPORAL VERSIONING (tracks all entity state changes over time)
-- =============================================================

CREATE TABLE entity_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     TEXT NOT NULL,                -- 'parcel', 'person', 'organization', 'court_case'
    entity_id       UUID NOT NULL,
    event_type      TEXT NOT NULL,                -- 'ownership_change', 'assessment_change', 'lien_filed',
                                                  -- 'lien_released', 'case_filed', 'case_disposed',
                                                  -- 'permit_issued', 'violation_cited', 'sale_recorded',
                                                  -- 'business_formed', 'business_dissolved'
    event_date      DATE NOT NULL,
    event_data      JSONB NOT NULL,               -- type-specific payload
    derived_from    JSONB,                        -- which source records generated this event
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_events_entity ON entity_events (entity_type, entity_id);
CREATE INDEX idx_events_date ON entity_events (event_date DESC);
CREATE INDEX idx_events_type ON entity_events (event_type);

-- Time-series aggregates for dashboards and trend analysis
CREATE TABLE area_statistics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    area_type       TEXT NOT NULL,                -- 'municipality', 'zip', 'school_district', 'county'
    area_id         UUID NOT NULL,
    period          TEXT NOT NULL,                -- '2024-Q1', '2024-03', '2024-W12'
    metric          TEXT NOT NULL,                -- 'total_sales', 'median_sale_price', 'new_permits',
                                                  -- 'new_liens', 'new_cases', 'code_violations',
                                                  -- 'avg_days_on_market', 'foreclosure_filings'
    value           NUMERIC(14,4),
    record_count    INTEGER,
    computed_at     TIMESTAMPTZ DEFAULT now(),
    UNIQUE(area_type, area_id, period, metric)
);

-- =============================================================
-- NLP & DOCUMENT INTELLIGENCE
-- =============================================================

CREATE TABLE document_extractions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_table     TEXT NOT NULL,               -- 'court_cases', 'government_actions', 'meeting_minutes'
    source_record_id UUID NOT NULL,
    extraction_type  TEXT NOT NULL,               -- 'named_entities', 'monetary_amounts', 'dates',
                                                  -- 'parcel_references', 'legal_citations', 'summary'
    extracted_data   JSONB NOT NULL,
    model_name       TEXT,                        -- which model produced this
    model_version    TEXT,
    confidence       NUMERIC(3,2),
    reviewed         BOOLEAN DEFAULT false,       -- human review flag
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE extracted_mentions (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id      UUID NOT NULL REFERENCES document_extractions(id),
    mention_type       TEXT NOT NULL,             -- 'person', 'organization', 'parcel', 'address', 'amount'
    mention_text       TEXT NOT NULL,             -- the raw text span
    resolved_entity_id UUID REFERENCES entities(id),
    resolved_parcel_id UUID REFERENCES parcels(id),
    char_offset_start  INTEGER,
    char_offset_end    INTEGER,
    confidence         NUMERIC(3,2),
    created_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE meeting_minutes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    municipality_id UUID REFERENCES municipalities(id),
    body            TEXT NOT NULL,                -- 'board_of_supervisors', 'planning_commission',
                                                  -- 'zoning_hearing_board', 'council'
    meeting_date    DATE NOT NULL,
    document_url    TEXT,
    raw_text        TEXT,                         -- extracted text content
    summary         TEXT,                         -- AI-generated summary
    source_id       UUID REFERENCES data_sources(id),
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- SATELLITE & IMAGERY INTELLIGENCE
-- =============================================================

CREATE TABLE imagery_captures (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT NOT NULL,                -- 'sentinel_2', 'planet', 'county_ortho', 'naip'
    capture_date    DATE NOT NULL,
    resolution_m    NUMERIC(6,2),                 -- meters per pixel
    cloud_cover_pct NUMERIC(5,2),
    bbox            GEOMETRY(Polygon, 4326),      -- bounding box of this capture
    tile_path       TEXT,                         -- S3 path to stored tile/COG
    band_info       JSONB,                        -- available spectral bands
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_imagery_bbox ON imagery_captures USING GIST (bbox);
CREATE INDEX idx_imagery_date ON imagery_captures (capture_date DESC);

CREATE TABLE change_detections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id       UUID REFERENCES parcels(id),
    detection_type  TEXT NOT NULL,                -- 'new_structure', 'demolition', 'land_clearing',
                                                  -- 'flooding', 'vegetation_change', 'construction'
    before_image_id UUID REFERENCES imagery_captures(id),
    after_image_id  UUID REFERENCES imagery_captures(id),
    confidence      NUMERIC(3,2),
    geometry        GEOMETRY(Polygon, 4326),      -- area of detected change
    detected_at     TIMESTAMPTZ DEFAULT now(),
    reviewed        BOOLEAN DEFAULT false,
    review_notes    TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- PREDICTIVE MODEL OUTPUTS
-- =============================================================

CREATE TABLE predictions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name      TEXT NOT NULL,                -- 'assessment_divergence', 'foreclosure_risk',
                                                  -- 'development_likelihood', 'price_trend'
    model_version   TEXT NOT NULL,
    entity_type     TEXT NOT NULL,                -- 'parcel', 'area', 'entity'
    entity_id       UUID NOT NULL,
    prediction_date DATE NOT NULL,
    horizon         TEXT,                         -- '30d', '90d', '1y'
    prediction      JSONB NOT NULL,
    -- Example: {"risk_score": 0.82, "factors": ["2_missed_payments", "lien_filed", "case_active"]}
    -- Example: {"predicted_value": 285000, "confidence_interval": [270000, 300000]}
    confidence      NUMERIC(3,2),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_predictions_entity ON predictions (entity_type, entity_id);
CREATE INDEX idx_predictions_model ON predictions (model_name, prediction_date DESC);

-- =============================================================
-- NATURAL LANGUAGE QUERY INTERFACE
-- =============================================================

CREATE TABLE query_log (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES users(id),
    natural_query     TEXT NOT NULL,              -- "show me all properties in 17404 in the flood zone"
    generated_sql     TEXT,                       -- the SQL that was generated
    execution_time_ms INTEGER,
    result_count      INTEGER,
    feedback          TEXT,                       -- 'helpful', 'wrong_results', 'needs_refinement'
    created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE saved_queries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    name            TEXT NOT NULL,
    description     TEXT,
    natural_query   TEXT,
    generated_sql   TEXT NOT NULL,
    parameters      JSONB,                        -- parameterized values user can change
    is_public       BOOLEAN DEFAULT false,        -- shared with other users
    run_count       INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- PHASE 3 ADDITIONS TO entity_relationships
-- =============================================================

-- New target column for meeting minutes references (NLP-extracted)
ALTER TABLE entity_relationships
    ADD COLUMN related_meeting_id UUID REFERENCES meeting_minutes(id);

-- New target column for prediction links
ALTER TABLE entity_relationships
    ADD COLUMN related_prediction_id UUID REFERENCES predictions(id);

CREATE INDEX idx_rel_meeting ON entity_relationships (related_meeting_id);
CREATE INDEX idx_rel_prediction ON entity_relationships (related_prediction_id);

-- Phase 3 relationship types added to entity_relationships:
--   'MENTIONED_IN'       : Entity -> Meeting Minute (NLP-extracted mention)
--   'PREDICTED_RISK'     : Entity/Parcel -> Prediction (link to model output)
--   'HISTORICALLY_LINKED': Entity -> Entity (derived from temporal event analysis)
--   'INFLUENCE_CLUSTER'  : Entity -> Entity (derived from community detection / PageRank)
```

### Phase 3 Relationship Queries: When Recursive CTEs Hit Their Limits

At Phase 3 scale (millions of relationships, 3+ hop traversals, graph algorithms), recursive CTEs remain functional but may become slow for certain query patterns. Below are the key Phase 3 queries shown in both SQL (what works today) and the Memgraph Cypher equivalent (what you'd migrate to if performance demands it).

```sql
-- =============================================================
-- NATURAL LANGUAGE → SQL (the LLM-generated query layer)
-- =============================================================

-- User asks: "Show me all properties in 17404 in the flood zone
--             where the assessed value is above the median for the zip"
-- The NL→SQL layer generates:
WITH zip_median AS (
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY a.assessed_total) AS median_val
    FROM parcels p
    JOIN assessments a ON a.parcel_id = p.id AND a.is_current = true
    WHERE p.address_zip = '17404'
)
SELECT p.parcel_id, p.address_full, a.assessed_total, fz.zone_code,
    a.assessed_total - zm.median_val AS above_median_by
FROM parcels p
JOIN parcel_spatial_overlays pso ON pso.parcel_id = p.id
    AND pso.overlay_type = 'flood_zone'
JOIN flood_zones fz ON fz.id = pso.overlay_id AND fz.is_high_risk = true
JOIN assessments a ON a.parcel_id = p.id AND a.is_current = true
CROSS JOIN zip_median zm
WHERE p.address_zip = '17404'
    AND a.assessed_total > zm.median_val
ORDER BY a.assessed_total DESC;

-- =============================================================
-- TEMPORAL ANALYSIS QUERIES
-- =============================================================

-- "Show me the activity timeline for this parcel over the last 2 years"
SELECT
    ee.event_date,
    ee.event_type,
    ee.event_data,
    CASE ee.event_type
        WHEN 'sale_recorded' THEN 'Sale: $' || (ee.event_data->>'sale_price')
        WHEN 'lien_filed' THEN 'Lien: ' || (ee.event_data->>'instrument_subtype')
        WHEN 'permit_issued' THEN 'Permit: ' || (ee.event_data->>'permit_type')
        WHEN 'case_filed' THEN 'Case: ' || (ee.event_data->>'docket_number')
        WHEN 'assessment_change' THEN 'Assessment: $' || (ee.event_data->>'old_total')
            || ' → $' || (ee.event_data->>'new_total')
        ELSE ee.event_type
    END AS event_summary
FROM entity_events ee
WHERE ee.entity_type = 'parcel'
    AND ee.entity_id = :parcel_uuid
    AND ee.event_date >= CURRENT_DATE - INTERVAL '2 years'
ORDER BY ee.event_date DESC;

-- "Which municipalities have seen the highest increase in foreclosure filings
--  quarter-over-quarter?"
WITH current_q AS (
    SELECT area_id, value FROM area_statistics
    WHERE area_type = 'municipality' AND metric = 'foreclosure_filings'
        AND period = '2026-Q1'
),
previous_q AS (
    SELECT area_id, value FROM area_statistics
    WHERE area_type = 'municipality' AND metric = 'foreclosure_filings'
        AND period = '2025-Q4'
)
SELECT m.name,
    cq.value AS current_filings,
    pq.value AS previous_filings,
    cq.value - pq.value AS change,
    ROUND(((cq.value - pq.value) / NULLIF(pq.value, 0)) * 100, 1) AS pct_change
FROM current_q cq
JOIN previous_q pq ON pq.area_id = cq.area_id
JOIN municipalities m ON m.id = cq.area_id
WHERE cq.value > pq.value
ORDER BY pct_change DESC;

-- =============================================================
-- NLP-POWERED MEETING INTELLIGENCE
-- =============================================================

-- "Find all zoning hearing board mentions of properties in my watchlist"
SELECT
    mm.meeting_date,
    m.name AS municipality,
    mm.body AS board,
    em.mention_text,
    p.address_full,
    mm.summary
FROM extracted_mentions em
JOIN document_extractions de ON de.id = em.extraction_id
    AND de.source_table = 'meeting_minutes'
JOIN meeting_minutes mm ON mm.id = de.source_record_id
    AND mm.body = 'zoning_hearing_board'
JOIN municipalities m ON m.id = mm.municipality_id
JOIN parcels p ON p.id = em.resolved_parcel_id
WHERE em.mention_type = 'parcel'
    AND em.resolved_parcel_id IN (
        -- User's watchlist parcels (from alerts or saved list)
        SELECT (filter_criteria->>'parcel_id')::UUID
        FROM user_alerts
        WHERE user_id = :user_uuid AND alert_type = 'parcel_change'
    )
ORDER BY mm.meeting_date DESC;

-- =============================================================
-- SATELLITE CHANGE DETECTION
-- =============================================================

-- "Show me parcels where new construction was detected but no building permit exists"
SELECT
    p.parcel_id, p.address_full, p.municipality_id,
    cd.detection_type, cd.confidence, cd.detected_at,
    m.name AS municipality
FROM change_detections cd
JOIN parcels p ON p.id = cd.parcel_id
JOIN municipalities m ON m.id = p.municipality_id
WHERE cd.detection_type IN ('new_structure', 'construction')
    AND cd.confidence >= 0.75
    AND cd.detected_at >= CURRENT_DATE - INTERVAL '6 months'
    AND NOT EXISTS (
        SELECT 1 FROM permits pm
        WHERE pm.parcel_id = p.id
            AND pm.permit_type = 'building'
            AND pm.issued_date >= cd.detected_at - INTERVAL '12 months'
    )
ORDER BY cd.confidence DESC;

-- =============================================================
-- PREDICTIVE MODEL QUERIES
-- =============================================================

-- "High-risk foreclosure candidates: parcels with risk score > 0.7
--  cross-referenced with actual current liens and active cases"
SELECT
    p.parcel_id, p.address_full,
    pred.prediction->>'risk_score' AS risk_score,
    pred.prediction->'factors' AS risk_factors,
    COUNT(DISTINCT rd.id) AS active_lien_count,
    COUNT(DISTINCT cc.id) AS active_case_count,
    e.canonical_name AS owner
FROM predictions pred
JOIN parcels p ON p.id = pred.entity_id AND pred.entity_type = 'parcel'
JOIN parcel_ownership po ON po.parcel_id = p.id AND po.is_current = true
JOIN entities e ON e.id = po.entity_id
LEFT JOIN recorded_documents rd ON rd.parcel_id = p.id
    AND rd.instrument_type = 'lien'
    AND NOT EXISTS (
        SELECT 1 FROM recorded_documents sat
        WHERE sat.parcel_id = p.id
            AND sat.instrument_type = 'satisfaction'
            AND sat.recording_date > rd.recording_date
    )
LEFT JOIN case_parties cp ON cp.entity_id = e.id
LEFT JOIN court_cases cc ON cc.id = cp.case_id
    AND cc.case_status = 'active'
    AND cc.case_subtype = 'mortgage_foreclosure'
WHERE pred.model_name = 'foreclosure_risk'
    AND (pred.prediction->>'risk_score')::NUMERIC >= 0.7
    AND pred.prediction_date = (
        SELECT MAX(prediction_date) FROM predictions
        WHERE model_name = 'foreclosure_risk' AND entity_id = pred.entity_id
    )
GROUP BY p.parcel_id, p.address_full, pred.prediction, e.canonical_name
ORDER BY (pred.prediction->>'risk_score')::NUMERIC DESC;

-- =============================================================
-- DEEP GRAPH TRAVERSAL (3+ hops — where you'd consider Memgraph)
-- =============================================================

-- "Find the shortest connection path between Entity A and Entity B
--  through any combination of relationships"
-- NOTE: This is where recursive CTEs get expensive. At Phase 3 scale,
-- if this query takes >5 seconds, it's a signal to add Memgraph.

WITH RECURSIVE paths AS (
    SELECT
        er.entity_id AS current,
        er.related_entity_id AS next_entity,
        er.relationship_type,
        1 AS depth,
        ARRAY[er.entity_id, er.related_entity_id] AS path
    FROM entity_relationships er
    WHERE er.entity_id = :entity_a_uuid
        AND er.related_entity_id IS NOT NULL
        AND er.is_current = true

    UNION ALL

    SELECT
        er.entity_id,
        er.related_entity_id,
        er.relationship_type,
        p.depth + 1,
        p.path || er.related_entity_id
    FROM entity_relationships er
    JOIN paths p ON er.entity_id = p.next_entity
    WHERE p.depth < 4  -- cap at 4 hops to prevent explosion
        AND er.related_entity_id IS NOT NULL
        AND er.is_current = true
        AND er.related_entity_id != ALL(p.path)
)
SELECT
    depth,
    path,
    ARRAY(
        SELECT e.canonical_name FROM unnest(path) AS pid
        JOIN entities e ON e.id = pid
    ) AS entity_names
FROM paths
WHERE next_entity = :entity_b_uuid
ORDER BY depth ASC
LIMIT 5;

-- Memgraph equivalent (if/when added in Phase 3):
-- MATCH path = shortestPath(
--     (a:Entity {id: $entity_a_uuid})-[*..4]-(b:Entity {id: $entity_b_uuid})
-- )
-- RETURN path, length(path) AS hops
```

---

## Schema Evolution Strategy

### MVP → Intermediate Migration Notes

The MVP schema is designed so that **no existing tables are altered** when Phase 2 tables are added. The key connection points are:

1. **`entities` table** — Already exists in MVP with basic person/org types. Phase 2 populates it more aggressively via entity resolution across court records and business filings.
2. **`entity_source_links` table** — The bridge. New source tables (`case_parties`, `document_parties`, `business_officers`) all link back to resolved entities through this table.
3. **`entity_relationships` table** — Already exists in MVP with `OWNS`/`SOLD_TO`/`LIKELY_SAME_AS` types. Phase 2 adds new relationship types (`IS_PARTY_TO`, `GRANTOR_OF`, `OFFICER_OF`, etc.) and adds FK constraints for the new target tables.
4. **`parcels` table** — Unchanged. New tables reference it via foreign key (`recorded_documents.parcel_id`, `permits.parcel_id`, `government_actions.parcel_id`).
5. **`access_log` → `access_audit_log`** — The MVP's lightweight access log is replaced by the richer audit table. Migrate existing records, then drop the old table.

**What changes:** Entity resolution pipeline becomes critical. In MVP, entity resolution is basic (assessment owner names only). In Phase 2, you're resolving across 5+ source systems, so Zingg/Senzing becomes a core pipeline component rather than a nice-to-have.

### Intermediate → Grand Vision Migration Notes

1. **`entity_relationships` expansion** — Two new target columns added (`related_meeting_id`, `related_prediction_id`) via `ALTER TABLE`. New relationship types (`MENTIONED_IN`, `PREDICTED_RISK`, `HISTORICALLY_LINKED`, `INFLUENCE_CLUSTER`) are just new string values in the `relationship_type` column — no schema change needed for these.
2. **`entity_events` table** — Backfill from existing records. Every `INSERT` to `sales`, `recorded_documents`, `court_cases`, `permits`, `government_actions` should also generate an event row. Implement this as a Dagster asset that materializes the event stream from source tables, then transition to trigger-based event generation for new records.
3. **NLP extraction tables** — Purely additive. Run extraction models against `court_cases.raw_data`, `government_actions.raw_data`, and `meeting_minutes.raw_text` to populate `document_extractions` and `extracted_mentions`. Extracted entity mentions feed back into `entity_relationships` as `MENTIONED_IN` edges.
4. **Imagery tables** — Completely independent. They connect to the rest of the model only through `parcel_id` foreign keys on `change_detections`. Imagery files stored in S3 as Cloud-Optimized GeoTIFFs.
5. **`predictions` table** — Additive. Prediction models read from existing tables and write results here. High-confidence predictions generate `PREDICTED_RISK` entries in `entity_relationships` for traversal.
6. **Natural language query layer** — `query_log` and `saved_queries` are purely additive product tables. The NL→SQL pipeline reads your schema metadata to generate queries — it doesn't require schema changes.
7. **Optional graph engine (Memgraph)** — If recursive CTE performance degrades at scale (millions of relationships, 3+ hop queries, shortest-path and community detection algorithms), introduce Memgraph as a read cache synced from `entity_relationships`. The relationship types already map directly to edge labels by design. Sync via a Dagster asset that reads `entity_relationships` and pushes to Memgraph's Bolt protocol. Postgres remains the source of truth; Memgraph is a query accelerator only.

### Key Design Decisions That Survive All Three Phases

| Decision | Rationale |
|---|---|
| UUIDs everywhere | Stable identifiers across merges, imports, and entity resolution |
| `raw_data JSONB` on source tables | Preserves original data even as your parsing improves |
| `source_id` on every record | Full provenance for legal compliance and debugging |
| `created_at`/`updated_at` on everything | Temporal auditing without a separate versioning system |
| Trigram indexes (`gin_trgm_ops`) on name fields | Fuzzy search without a separate search engine |
| `is_current` flags rather than deleting old records | Historical analysis, no data loss |
| `entity_relationships` adjacency list | Graph-like traversal in pure Postgres; maps cleanly to a graph engine later |
| JSONB for flexible/evolving fields | Schema evolution without migrations for type-specific attributes |
| AWS RDS PostgreSQL | Managed database with automated backups; PostGIS + pg_trgm support; same VPC as EC2 |
| Auth (deferred) | No auth for MVP — publicly accessible; Cognito or Clerk for future phases |

---

## Appendix A: Infrastructure by Phase

| Phase | Database | Storage | Compute | Auth | Est. Monthly Cost |
|---|---|---|---|---|---|
| MVP | RDS db.t3.micro (20 GB, free tier Y1) | S3 Free Tier | EC2 t3.micro (Dagster) + Lambda (API) | None (public) | **~$7/month Y1; ~$32–36 Y2+** |
| Intermediate | RDS (storage scaled to 40+ GB) | S3 (~50 GB) | EC2 t3.small + Lambda | Cognito or Clerk | **$40-80** |
| Grand Vision | RDS (100+ GB or Aurora) | S3 (~500 GB incl. imagery) | EC2 + optional ECS for Memgraph | Cognito or Clerk | **$100-200+** |

*ML compute (entity resolution batch jobs, NLP extraction, prediction models) can run on EC2 spot instances as needed — not a constant cost. See `york-county-infrastructure-plan.md` Cost Breakdown section for detailed numbers.*

## Appendix B: Relationship Types Reference

| Relationship Type | Source Entity | Target | Phase | Description |
|---|---|---|---|---|
| `OWNS` | Person/Org | Parcel | 1 | Current property ownership |
| `CO_OWNS` | Person/Org | Parcel | 1 | Joint ownership |
| `PREVIOUSLY_OWNED` | Person/Org | Parcel | 1 | Historical ownership |
| `SOLD_TO` | Person/Org | Person/Org | 1 | Buyer-seller link (via sales) |
| `BOUGHT_FROM` | Person/Org | Person/Org | 1 | Inverse of SOLD_TO |
| `LIKELY_SAME_AS` | Entity | Entity | 1 | Low-confidence entity resolution match |
| `IS_PARTY_TO` | Person/Org | Court Case | 2 | Party in litigation (properties: role) |
| `GRANTOR_OF` | Person/Org | Document | 2 | Grantor on deed/document |
| `GRANTEE_OF` | Person/Org | Document | 2 | Grantee on deed/document |
| `LIENHOLDER_OF` | Person/Org | Document | 2 | Holds a lien/mortgage |
| `OFFICER_OF` | Person | Business Entity | 2 | Officer/director/manager |
| `MEMBER_OF` | Person/Org | Business Entity | 2 | Member of LLC/partnership |
| `AGENT_FOR` | Person/Org | Business Entity | 2 | Registered agent |
| `APPLIED_FOR` | Person/Org | Permit | 2 | Permit applicant |
| `CO_DEFENDANT` | Person/Org | Person/Org | 2 | Derived: co-parties in same case |
| `TRANSACTED_WITH` | Person/Org | Person/Org | 2 | Derived: shared transaction history |
| `SHARES_ADDRESS` | Person/Org | Person/Org | 2 | Derived: same registered/mailing address |
| `BUSINESS_ASSOCIATE` | Person/Org | Person/Org | 2 | Derived: shared business entity |
| `MENTIONED_IN` | Entity | Meeting Minute | 3 | NLP-extracted mention in unstructured text |
| `PREDICTED_RISK` | Parcel/Entity | Prediction | 3 | Link to predictive model output |
| `HISTORICALLY_LINKED` | Entity | Entity | 3 | Derived: temporal event analysis shows recurring co-occurrence |
| `INFLUENCE_CLUSTER` | Entity | Entity | 3 | Derived: community detection / PageRank grouping |
