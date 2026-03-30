# Open Items

## Open Items

| Item | Status | Notes |
|---|---|---|
| Docker Postgres PostGIS extension | Pending | Verify `CREATE EXTENSION IF NOT EXISTS postgis;` in `init.sql` runs on container startup |
| R2 bucket + rclone config | Pending | Create R2 bucket in Cloudflare dashboard; configure rclone with R2 API credentials for pipeline uploads |
| Cloudflare Pages project setup | Pending | Connect GitHub repo to Cloudflare Pages; configure build command (`cd frontend && npm run build`) and output directory |
| Docker Compose production config | Pending | Dockerfiles for api + dagster services; production `docker-compose.yml` on VPS |
| Watchtower GHCR auth | Pending | Configure Watchtower with GHCR token so it can pull private container images |
| Verify `inmatelocator.yorkcountypa.gov` | Pending | DNS failed during testing — check from local browser. Marked ❌ in daily schedule table. |
| Verify sheriff sales URLs | Pending | County website reorganized, old URLs redirect incorrectly. Marked ⚠️ in daily schedule table. |
| Live-test PennDOT Open Data (#5) | Pending | Same ArcGIS REST API pattern as GIS Portal (#1) but not live-tested. Marked ⚠️ in weekly schedule table. Should work — verify during Phase 3 Step 3.2 (source #6 in build order). |
| Schema migrations strategy | **Decided: Alembic** | Versioned migrations, local Docker Postgres for testing, LLM-generated migration files |
| Pipeline code repository structure | **Decided: Monorepo, assets by source type** | See Pipeline Code Structure section |
| Frontend | **Decided: React + MapLibre + Deck.gl, Cloudflare Pages, FastAPI** | See Frontend Architecture section |
| Entity resolution approach | **Decided: Deterministic PostgreSQL (pg_trgm)** | Tiered matching, source-agnostic schema, Zingg upgrade path documented |
| Deployment pipeline (CI/CD) | **Decided: GitHub Actions + GHCR** | Path-filtered workflows; Watchtower pulls new images from GHCR; see CI/CD section |
| Neon account | Not needed | Was considered early on; Docker Postgres on VPS is the production database |

## Build-Time Decisions (resolve during implementation, not planning)

These items are intentionally deferred — they require hands-on-keyboard work to resolve correctly.

| Item | Phase | Notes |
|---|---|---|
| Staging table DDLs | Phase 2–3 | Exact columns depend on what each source API returns. Write Alembic migrations as each pipeline is built. The SCD2 pattern (`valid_from`/`valid_to`) is defined in `docs/schema/strategy.md`. |
| `scd2_upsert()` implementation | Phase 3 | Shared lib function. Needs: (1) expire changed records via `UPDATE SET valid_to = NOW()`, (2) insert new/changed records with `valid_from = NOW()`, (3) skip unchanged records (compare non-key columns), (4) detect deletes (record in DB not in source). Write during framework setup (Step 3.1). |
| API response schemas (Pydantic) | Phase 4 | Define as you build each route. Key decisions: pagination for `/api/parcels/bbox` (cursor or offset?), error format (`{"error": "...", "status": 404}`), search ranking weights. |
| Enrichment sensor | Phase 3 | Dagster `multi_asset_sensor` watching weekly source assets. Fires when all MVP deps have fresh materializations. Write alongside `enrichment/owners.py`. |
| `dagster.yaml` + `workspace.yaml` | Phase 3 | Generated during Dagster init. Standard config pointing at Postgres for storage, `pipelines/` as code location. |
| `init.sql` consolidation | Phase 1 | Combine schema creation (`CREATE SCHEMA staging/public/meta`), PostGIS extension, `pg_trgm` extension, and meta DDL from `docs/schema/meta.md` into one script. |
| CORS lockdown | Phase 5 | Replace `allow_origins=["*"]` with `countyiq.com` domain. Track in go-live checklist. |
| `meta.query_audit_log` DDL | Phase 2 | Define when auth gate is implemented. Not needed for MVP. |
| Staging table partial indexes | Phase 3 | Add `CREATE INDEX ... WHERE valid_to IS NULL` on each staging table after initial data load confirms query patterns. |
