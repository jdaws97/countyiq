# Privacy and Access Control

## Current State

CountyIQ is a public, read-only application with no accounts. It collects
government-published property, planning, licensing, infrastructure, and
business-registration sources. It does not ingest court, inmate, crime, credit,
or privately purchased person data.

Public availability of each source does not eliminate aggregation risk.
CountyIQ makes ownership portfolios, delinquency, distress rankings, entity
relationships, and historical changes easier to discover than the source
systems do. Those derived surfaces require an explicit distribution decision
before the product is promoted broadly.

## Current Controls

- The application does not accept edits or user-submitted personal data.
- Watchlists stay in the user's browser; there is no server-side watch profile.
- Natural-language search has per-client rate limits and a daily LLM-call
  budget.
- Browser CORS access is limited to explicit origins; wildcard origins are
  rejected.
- Source and model archives are operational artifacts, not API responses.
- Raw-source proxy APIs, reconstructive bulk exports, and raw data resale are
  outside the product boundary.
- Tax-claim rows are unavailable to natural-language row queries and
  claimant-name fuzzy search is removed. Municipality-level aggregates remain.
- Distress, delinquent-owner, and assemblage route groups are not mounted unless
  `COUNTYIQ_ENABLE_RESTRICTED_DISTRESS=true`; the corresponding frontend pages
  also require `VITE_ENABLE_RESTRICTED_DISTRESS=true` at build time. Both
  default to false and are deployment gates, not legal conclusions.
- Ordinary parcel tax status omits claimant names and source-listed addresses;
  owner-profile delinquency detail follows the same restricted gate.
- Score APIs recursively remove prior-owner/applicant/claimant identity and
  free-form validation prose from signal JSON whenever person-level display is
  disabled. Numeric weights, safe physical/policy facts, and deterministic
  reason labels remain available.

## Pre-Launch Access Gate

Before broader customer distribution:

1. Obtain an approved distribution/access decision before enabling the
   default-off person-linked distress routes; do not use the flag as a
   substitute for that decision.
2. Define export limits separately from ordinary page/API access.
3. Configure and verify the final frontend origin if production is not
   same-origin.
4. Apply rate limits to person- and owner-centric endpoints, not only LLM
   search.
5. Review the final fields and derived rankings with qualified privacy and data
   counsel; public-record status alone is not the review standard.
6. Define correction and source-attribution handling for challenged records.

Authentication technology and paid tiers are intentionally undecided until
customer use establishes which workflows need protection. The codebase should
not pre-commit to a vendor or fictional user roles.

## LLM and Archive Handling

Offline intelligence passes send source excerpts and structured property
context through OpenRouter. Production can require zero-data-retention routing
with `COUNTYIQ_ZDR=true`. LLM request/response archives may contain owner names,
addresses, and source excerpts; they must be stored outside the public web
root, access-controlled operationally, and covered by the still-open retention
policy in `docs/open-items.md`.

Interactive search sends the user's query to a dedicated low-cost model pool
only when deterministic search cannot handle it. The current implementation
restricts generated plans to allowlisted tables and fields, uses a read-only
transaction, and enforces a statement timeout. Tax claims are aggregate-only
in that typed plan and cannot be filtered by claimant name.

## Data Minimization Rules

- Keep only fields needed for an investor or developer job.
- Do not add sensitive source classes merely because they are obtainable.
- Prefer parcel- and project-level presentation over unnecessary person-level
  dossiers.
- Preserve source links and observed dates so derived claims can be audited.
- Keep raw archives private and serve only normalized or derived product data.
