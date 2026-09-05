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
- Owner/entity portfolio routes have a separate per-client anti-scraping
  throttle. It limits bulk access but does not create an authorization policy.
- Browser CORS access is limited to explicit origins; wildcard origins are
  rejected.
- Source and model archives are operational artifacts, not API responses.
- Raw-source proxy APIs, reconstructive bulk exports, and raw data resale are
  outside the product boundary.
- Owner names, prior owners, assessment mailing addresses, proceeding
  applicants, and verified source excerpts are ordinary derived-product fields.
  Migration 054 removes the former person-display switch; source distribution
  still requires `derived_product_allowed`.
- Exact tax-claim balances, years, claimant/source addresses, and owner-level
  delinquency detail remain behind `COUNTYIQ_ENABLE_RESTRICTED_DISTRESS=true`.
  They are debt detail, not identity. Natural-language search cannot issue
  tax-claim row queries or claimant-name fuzzy searches.
- Public parcel and feed surfaces may show the presence or direction of a
  delinquency change, but not exact balances or reconstructive counts. Routine
  balance movement is suppressed unless it crosses the materiality threshold.
- Legacy standalone distress pages are not product routes; their bookmarks
  redirect to the evidence-backed Feed or Radar.

## Pre-Launch Access Gate

Before broader customer distribution:

1. Keep exact debt detail default-off unless a separate distribution/access
   decision approves it; public-record identity does not approve debt detail.
2. Define export limits separately from ordinary page/API access.
3. Configure and verify the final frontend origin if production is not
   same-origin.
4. Review final fields and derived rankings with qualified privacy and data
   counsel; public-record status alone is not the review standard.
5. Define correction and source-attribution handling for challenged records.

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
- Use person identity only where the ownership/contact job requires it; do not
  turn public records into unrelated person dossiers.
- Preserve source links and observed dates so derived claims can be audited.
- Keep raw archives private and serve only normalized or derived product data.
