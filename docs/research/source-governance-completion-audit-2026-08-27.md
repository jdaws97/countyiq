# CountyIQ Source-Governance Completion Audit

**Audit date:** 2026-08-27
**Scope:** York County and reusable Pennsylvania source research, Dagster
collection, database policy, API serving, scoring replacements, and municipal
proceedings

This is an engineering and product-risk record, not legal advice. A qualified
attorney must make the final launch decision for unresolved contractual,
privacy, FCRA, and public-record distribution questions.

## Outcome

The repository now fails closed at the boundaries CountyIQ controls. Public
reachability alone no longer authorizes acquisition, retention, derived use,
person display, export, redirects, or vendor-origin access. Paused sources are
absent from schedules/configuration and remain visible in policy tables. The
open-data replacements preserve property and site-selection signal without
recreating prohibited person-level products.

This makes continued development and controlled internal evaluation materially
safer. It does **not** by itself authorize a paid public launch: the external
approvals and operational controls listed below remain launch gates.

## Requirement matrix

| Requirement | Repository/database evidence | Result |
|---|---|---|
| Exhaustive York/PA source inventory | 126 unique records in `york-pa-dataset-register-2026-08-27.csv`; 59 York `OPEN_DATA` services; York, PA, and federal scope; value, disposition, legal basis, county commonality, and product recommendation fields | Complete for the recorded review date; periodic discovery still required |
| Pennsylvania county commonality | The landscape and register distinguish statewide common sources, common-but-county-published families, PASDA mirrors, and York-only sources | Recorded, including non-common sources rather than forcing equivalence |
| Top-level source policy | `meta.source_rights` has 11 reviewed sources: four green, four conditional, and three paused; append-only decisions are recorded in `meta.source_rights_audit` | Enforced |
| Municipal policy | `meta.municipality_source_rights` has 122 body-level policies across all 72 municipalities: 110 conditional and 12 paused | Enforced |
| Pre-network authorization | Governed assets call `authorize_source` and, for proceedings, exact body/URL/type authorization before requests | Enforced and statically tested |
| Downstream-use separation | Derived product, raw retention, natural-person display, and raw export are independent permissions; ingestion and API paths check the applicable use; independent signal and score rebuilds reauthorize every source that actually contributes | Enforced |
| Redirect/vendor containment | Migrations 033–034 add `allowed_origins`; HTTP redirects are approved before destination access; browser document/XHR/fetch requests cannot cross to an unreviewed origin; mixed pages retain approved first-party records while reporting, rather than fetching or treating as run failures, unreviewed document links | Enforced |
| Robots and client identity | Listing, redirect, document, Drive, and browser data requests use the honest CountyIQ user agent and fail closed on missing/failed/disallowing robots decisions | Enforced |
| Paused scheduling | YCPC project ecodev, CDBG housing, and County Scout are absent from schedules; municipal paused bodies are absent from collection configuration | Enforced and tested |
| Customer serving | Governed API routes require derived permission; restricted distress/person routes are default-off; tax claimant/address and natural-person owner disclosures are suppressed; signal JSON removes prior-owner identity and free-form LLM prose when person display is disabled; raw/source-equivalent export is not offered | Enforced for current routes |
| Replacement signal | York open zoning overlays, business/industrial parks, soils, and local traffic power site readiness; municipality delinquency aggregates, boolean parcel state, organization intelligence, and generic events preserve non-person targeting value. Radar serving checks only policies for sources that feed the requested score; site readiness remains available without the conditional tax-claim source. | Implemented and tested; local replacement tables still need a live backfill |
| Municipal evidence | The retained JSON audit contains every policy row, authorization run ID, rights state, robots/HTTP/browser outcome, allowed origins, discovered links, collectable document count, and blocked document-origin counts without retaining page bodies | Complete for the audit run |

## Municipal disposition

The 12 paused body policies are not deleted:

- Cross Roads Borough and Railroad Borough: no confirmed official web source;
- Shrewsbury Township main body: eCode360 commercial-use restriction;
- Dover Township BOS and ZHB: Rep'd delivery terms limit site/content use to
  personal, non-commercial use;
- West York Borough: Google Drive delivery origin lacks separate commercial
  approval;
- West Manheim BOS, PC, and ZHB: explicit live robots disallows; and
- Franklintown Borough, Newberry Township, and Washington Township: useful
  documents are GoDaddy-CDN-only and current vendor terms restrict crawler
  download/third-party resale.

The live review also found active-but-unhealthy sources (403/404, robots
uncertainty, or no supported documents). They remain conditional because the
policy is not an affirmative prohibition, but every failed run remains blocked
and visible; the system does not infer “no municipal activity.”

## Why backend-only use is not a blanket exemption

Keeping source material on the backend reduces redistribution, user-interface,
privacy, and source-substitution risk. It is an important distinction and is
the reason CountyIQ can retain narrowly approved private evidence while serving
short factual derivations.

It does not erase restrictions that attach earlier in the lifecycle. Accessing
a site, following a vendor API/iframe, automated downloading, copying into
storage, and creating a commercial derivative can each be governed by terms,
robots policy, copyright in expressive packets, database/access rules, privacy
law, or an agency's bulk-access conditions. “Publicly viewable” often means
citizens may inspect a record; it does not always mean every delivery platform
grants automated commercial use.

## Commercially viable product boundary

CountyIQ can preserve strong real-data signal by making openly licensed or
expressly unrestricted government data the scoring backbone, using conditional
official records for narrow factual verification, and selling the analysis,
normalization, entity resolution, prioritization, and workflow—not a copy of a
publisher's database or document library.

The safe current boundary is:

- derive site, parcel, infrastructure, change, and organization intelligence
  from green/open sources;
- use conditional proceedings/distress records only through the recorded
  acquisition and use permissions;
- keep raw evidence private and access-controlled when retention is allowed;
- do not expose source-equivalent downloads, claimant lists, people-search, or
  eligibility/credit/tenant/employment decisions; and
- attribute sources, preserve dates/provenance, show uncertainty, and maintain
  correction/suppression paths.

## Verification receipt

Fresh verification on 2026-08-27 produced these results:

- 667 pipeline unit tests passed (18 integration tests deselected by the
  unit-test command);
- six migrated-schema/source-governance integration tests passed against
  `postgres-test`;
- 49 API contract and unit tests passed;
- the Dagster definitions graph resolved 43 assets;
- frontend TypeScript, ESLint, and the production Vite build passed under the
  repository's required Node 22 runtime; and
- a disposable database completed the entire Alembic chain from revision 001
  through head 035, producing four green, four conditional, and three paused
  top-level policies plus 110 conditional and 12 paused municipal policies.

The migrated local database is at revision 035. Its approved replacement
tables remain empty because production R2 credentials and a live backfill were
not supplied; this is recorded as an operational launch gate rather than being
misreported as completed data coverage.

## External and operational launch gates

The following cannot be completed by repository code alone:

1. Obtain counsel's written launch review, including contract formation,
   Pennsylvania public-record reuse, privacy, and FCRA/product-purpose analysis.
2. Obtain written publisher/vendor permission for any paused source CountyIQ
   wants to restore; record it in a new migration rather than changing runtime
   flags.
3. Capture dated terms/license evidence snapshots and hashes at each policy
   review. Review dates already fail closed, but evidence-change monitoring is
   not automated.
4. Implement production authentication/authorization, customer-purpose and
   prohibited-use controls, per-user audit logs, export limits, and a documented
   correction/suppression workflow before broader customer access.
5. Configure production R2 and its retention/access policy, then backfill the
   approved replacement assets. The local test database is structurally current
   but does not contain a live replacement-data backfill.
6. Re-review municipal and conditional policies by 2026-11-27 and green/open
   policies by 2027-02-27, or collection will fail closed.

## Reproducible municipal audit

From `pipelines/`, with database variables pointing at a migrated CountyIQ
database:

```bash
.venv/bin/python scripts/audit_municipal_sources.py --with-browser
```

The command writes
`docs/research/york-pa-municipal-source-static-audit-2026-08-27.json`. It
retains operational metadata only; it does not retain listing HTML or document
bodies.
