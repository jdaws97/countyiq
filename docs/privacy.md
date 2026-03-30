# Privacy & Access Control

## Privacy & Access Control

### Current State: No Auth for MVP

All data ingested in the MVP phase is **already publicly available** — GIS portal data, FEMA flood maps, PennDOT road data, PA Open Data Portal datasets, and assessment records are all published by government agencies for public consumption. CountyIQ aggregates and cross-references this data but does not create new privacy exposure because anyone can already access every individual record through the source agencies' own websites.

There is no authentication layer in the MVP. The frontend is publicly accessible via Cloudflare Pages, and the API serves data without requiring login.

### When Access Controls Become Necessary

Access controls should be introduced **before or alongside Phase 2 sources** that involve sensitive aggregated data:

| Phase 2 Source | Privacy Concern | Mitigation |
|---|---|---|
| Inmate Records (#20) | Aggregated booking/release history creates a de facto criminal record tracker | Require login; rate-limit queries; no bulk export |
| UJS Court Records (#6) | Case filings linked to property ownership and addresses | Same as above; consider excluding from public search, limit to authenticated civic/professional users |
| Sheriff Sales (#9) + Tax Claim (#14) | Financial distress signals tied to property addresses and owner names | Less sensitive individually (already posted publicly) but aggregated timeline creates risk |
| CRIMEWATCH (#19) | Incident data geolocated to neighborhoods; combined with property data creates crime overlay | Standard public safety data, but aggregation with ownership data warrants review |

### Recommended Phased Approach

**Phase 1 (MVP):** No auth. All data is public-record. Ship fast.

**Phase 2 (when court/inmate data arrives):**

- Add Clerk authentication
- Implement role-based tiers: `citizen` (default, rate-limited), `professional` (real estate, legal), `government` (municipal staff)
- Add query auditing: log all API requests with user identity, query parameters, and timestamp to `meta.query_audit_log`

*Note: `meta.query_audit_log` does not exist at MVP. It will be added as part of the Phase 2 auth gate implementation. The DDL will be defined when Clerk integration is built.*

- Rate-limit person-specific lookups (e.g., owner name search limited to 50/hour for citizen tier)

**Phase 3 (72 municipalities, full entity graph):**

- Formal data governance review before launch
- Consider FOIA/RTK compliance implications of aggregated entity graphs
- Monitor PA HB 1822 (Public Servant Data Privacy Act) — if enacted, may require redacting home addresses of law enforcement, judges, and other covered officials from public-facing views

### PA HB 1822 Awareness

The feasibility report (`docs/data-source-feasibility.md`, Privacy & Legal Considerations section) flags HB 1822, which would restrict public disclosure of home addresses for certain public servants. While not yet enacted as of this writing, the schema design accommodates this: the `staging.parcels` table stores owner data with SCD Type 2 history, making it possible to implement redaction filters as a PostgreSQL VIEW layer (e.g., `public.properties_public` that excludes covered individuals) without modifying underlying data.

### Infrastructure Implications

Adding authentication does not require architectural changes — it's an additive layer:

- **API:** FastAPI middleware for JWT verification (Clerk tokens)
- **Frontend:** React auth wrapper (redirect to login for protected routes)
- **Cloudflare:** No change needed (auth happens at API layer, not CDN)
- **Cost:** Clerk free tier covers 10,000 MAU (sufficient for initial launch)

The API's flat package structure (`api/routes/`, `api/lib/`) makes it straightforward to add auth middleware without restructuring.

---
