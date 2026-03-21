# Expansion Roadmap

Everything below is modular. Tackle in any order, whenever you're ready. The MVP is fully functional without any of these.

---

## Expansion A: Phase 2 Data Sources

### Adding a New Source — Standard Checklist

Every new source follows the same pattern established in Phase 3. Use this checklist:

```
□ 1. Review the source in the Data Source Feasibility Report
       - Verify URL is still accessible
       - Confirm access method and any changes since testing

□ 2. Create Alembic migration for new staging table(s)
       - Include valid_from/valid_to if change-tracked
       - Test locally with Docker Postgres
       - Apply to RDS via SSM tunnel

□ 3. Write the parser
       - pipelines/lib/parsers/<source>.py
       - Handle nulls, encoding, edge cases

□ 4. Save a test fixture
       - pipelines/tests/fixtures/<source>_sample.json (or .html, .csv)
       - Small sample from real API/page response

□ 5. Write schema validation test
       - pipelines/tests/test_<source>_parser.py
       - Verify required fields present, types correct

□ 6. Write the Dagster asset
       - pipelines/assets/<type>/<source>.py
       - Include backfill config (full_history flag)
       - Apply default retry policy

□ 7. Write asset checks
       - Record count > 0
       - Required fields not null
       - Count within expected range

□ 8. Add the schedule
       - Reference Data Refresh Schedules section for cron expression

□ 9. Update entity resolution
       - If source contains owner/business names, add it as a new source_type
       - Update owner_source_links mapping

□ 10. Run locally against live API/site
        - dagster asset materialize -a <asset_name>
        - Verify data in local Postgres

□ 11. Push and deploy
        - PR → CI passes → merge → auto-deploy

□ 12. Run backfill in production
        - Trigger from Dagster UI with full_history: true
        - Monitor in Slack

□ 13. Verify in /ops/health
        - New source appears with green status
```

### Phase 2 Source Priority Order

Recommended order based on value-add and difficulty. Tackle the highest-value, easiest sources first.

| Priority | Source | # | Method | Difficulty | Value-Add |
|---|---|---|---|---|---|
| 1 | PA DOS Business Entities | 8 | data.pa.gov API | Easy | Links businesses to owners via entity resolution |
| 2 | PLCB Liquor Licenses | 22 | CSV download | Easy | Already have CSV pattern from MVP; adds license data layer |
| — | **🔒 AUTH & GOVERNANCE GATE** | — | — | Medium | **Before adding person-level or sensitive data (sources 3–5, 13–15 below), implement: Cognito/Clerk auth, role-based tiers, query audit logging (`meta.query_audit_log` — new table, add DDL during this phase), rate-limited person lookups. See Infra Plan: Privacy & Access Control section.** |
| 3 | CRIMEWATCH (Police Blotters) | 19 | Playwright + pagination | Medium | High-demand data; incident mapping on frontend |
| 4 | Sheriff Sales / Tax Claim | 9 | Scraper + PDF | Medium | Financial distress indicators; property investment intel |
| 5 | Tax Claim Bureau | 14 | HTML + PDF | Medium | Delinquent property identification |
| 6 | County Bids | 12 | BeautifulSoup | Easy | Government spending visibility |
| 7 | York City RFPs | 18 | BeautifulSoup | Easy | City-level procurement |
| 8 | Commissioners Meetings | 15 | HTML + PDF | Medium | Government decision tracking |
| 9 | YCPC Subdivision Activity | 16 | HTML + PDF | Medium | Development pipeline intel |
| 10 | Conservation District (YCCD) | 11 | PDF download | Medium | Environmental planning data |
| 11 | PA DEP eFACTS | 17 | Playwright (ASP.NET) | Hard | Environmental compliance; complex scraper |
| 12 | PALS Professional Licenses | 21 | Playwright (AngularJS) | Hard | Professional license data; complex SPA scraping |
| 13 | UJS Portal (Court Records) | 6 | AOPC request + Playwright | Hard | Requires formal application; high value once obtained |
| 14 | Recorder of Deeds | 7 | RTK request | N/A | Depends on RTK response format/timeline |
| 15 | Inmate Records | 20 | TBD | TBD | Pending URL verification |

> **🔒 HARD STOP: Do not proceed past Priority 2 without implementing authentication.** Sources 3–5 expose person-level data (crime incidents, financial distress, tax delinquency). Deploying these without auth creates privacy liability. Implement Cognito/Clerk auth, role-based tiers, `meta.query_audit_log`, and rate-limited person lookups before building any source marked with 🔒 above. See `docs/privacy.md` for the full requirements.

### Source-Specific Notes

**Source 8 — PA DOS Business Entities:**
- Two access paths: data.pa.gov SODA API (easier) and file.dos.pa.gov (behind Cloudflare)
- Start with data.pa.gov; fall back to file.dos.pa.gov if data.pa.gov doesn't have York County-specific data
- Entity resolution: match business officer names to parcel owners

**Source 19 — CRIMEWATCH:**
- Playwright required — JavaScript-rendered pagination
- Paginate through all available pages on backfill
- Geolocation: incidents have addresses that need geocoding to map coordinates
- Frontend: add a "Recent Incidents" layer to the map with clustering

**Sources 9 + 14 — Sheriff Sales + Tax Claim:**
- These are related — tax delinquency → tax claim → sheriff sale
- Build together; they share a frontend view ("Properties in Financial Distress")
- Sheriff sales URL needs verification (county site reorganized)
- PDF parsing needed for some sale documents

**Source 17 — PA DEP eFACTS:**
- ASP.NET application with session state — Playwright required
- Search by county = "York" to get all records
- Paginate through results
- Links to parcels via facility address

**Source 21 — PALS Professional Licenses:**
- AngularJS SPA — Playwright required, wait for Angular to load
- Search by county/profession
- Large dataset — will need pagination and throttling

**Sources 6 + 7 — UJS Court Records + Recorder of Deeds:**
- Both require formal applications (AOPC and RTK respectively)
- Start the application process early — they take weeks/months
- Build the pipeline infrastructure in parallel while waiting for access
- Court records are the highest-value Phase 2 source for entity resolution

**Source 20 — Inmate Records:**
- `inmatelocator.yorkcountypa.gov` had DNS failure during feasibility testing
- First step: verify URL from a local browser
- If unreachable, check if the county moved it to a different domain

---

## Expansion B: Phase 3 Data Sources

### Source 10 — Municipal Meeting Minutes (72 Municipalities)

This is the highest-effort data source in the entire platform. York County has 72 municipalities, each with their own website (if they have one at all).

**Approach:**

1. **Inventory phase** — Catalog all 72 municipality websites. Identify which ones post meeting minutes online, in what format (PDF, HTML, embedded doc), and at what URL pattern. This is a manual research task — expect 2-3 hours.

2. **Template scrapers** — Group municipalities by website platform:
   - Many small townships use the same CMS (e.g., Civic Plus, WordPress)
   - Write one scraper template per CMS, parameterized by URL
   - Custom scrapers only for unique sites

3. **PDF extraction** — Most meeting minutes are PDFs. Use pdfplumber to extract text. NLP processing to identify:
   - Zoning decisions (approvals, denials, variances)
   - Development plan approvals
   - Utility projects
   - Budget items

4. **Phased rollout** — Don't try to do all 72 at once:
   - Start with the 10 largest municipalities (York City, Spring Garden, West Manchester, etc.)
   - Add 10-15 per sprint
   - Some tiny townships don't have websites — skip them

5. **Entity resolution** — Link meeting content to parcels/owners when addresses or names are mentioned.

**Estimated effort:** 2-4 weeks for the first 10 municipalities. 1-2 months for comprehensive coverage.

---

## Expansion C: Platform Upgrades

These are infrastructure improvements, not data sources. Tackle when the trigger condition is met.

| Upgrade | Trigger | Effort | Infra Plan Reference |
|---|---|---|---|
| Automated Cost Kill Switch | After free tier expires, if costs become unpredictable | 2-3 hours | Future Enhancements → #1 |
| NAIP Imagery Pipeline | When aerial imagery analysis becomes a priority | 1-2 days | Future Enhancements → #2 |
| Upgrade to t3.small | CloudWatch shows memory > 80% consistently | 30 min (Terraform variable change) | Future Enhancements → #3 |
| Private VPC + NAT Gateway | Security audit requires no public IP on EC2 | 2-3 hours | Future Enhancements → #4 |
| Dagster Cloud Hybrid | Multiple users need Dagster UI access | 1-2 days | Future Enhancements → #5 |
| ALB + Cognito for Dagster UI | Browser-based multi-user Dagster access | 1 day | Future Enhancements → #6 |
| Custom domain | When you want `countyiq.com` instead of CloudFront URL | 1-2 hours | Frontend Architecture → Custom Domain |
| Authentication on frontend | When you want to restrict access or add user accounts | 1-2 days | Not yet designed — consider Cognito or Clerk |
| Zingg entity resolution | pg_trgm matching produces too many false positives/negatives | 2-3 days | Entity Resolution → Zingg Upgrade Path |
| Multi-county expansion | When you want to add Lancaster, Adams, or other counties | 1-2 weeks | Entity Resolution → Why It Scales |

### Multi-County Expansion Notes

The entity resolution schema was designed to be source-agnostic (see Infrastructure Plan, Entity Resolution section). Expanding to another county means:

1. Create a new RDS database (or schema per county within the same instance)
2. Copy the Dagster asset templates — most sources (ArcGIS, PA state portals) work the same way across counties
3. Update ArcGIS endpoints for the new county's GIS portal
4. The county-specific scrapers (assessment, sheriff sales) need new implementations per county
5. Entity resolution runs per-county initially; cross-county matching is a future capability

The hardest part isn't the code — it's finding and verifying each county's data source URLs and access methods. Budget 1-2 weeks per new county for the research + implementation.

---
