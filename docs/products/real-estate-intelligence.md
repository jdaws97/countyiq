# Real Estate Intelligence (Product Direction)

This is the active product lane for CountyIQ. It names the buyer, the jobs the product does, what we will and won't build, and how existing assets map to revenue.

## Lane

CountyIQ is a **county-grade real-estate intelligence platform for private-market investors and developers operating in South-Central PA**, starting in York County. The code and deployment contract are county-configurable now; an adjacent county is activated only after its source rights, coverage, and a real user need are verified.

We are **not** building:
- a consumer real-estate search portal (Zillow / Redfin),
- a national parcel-data reseller (ATTOM / CoreLogic / Regrid),
- a civic-journalism platform,
- a government/planning-department licensed tool,
- a title or legal workflow product.

Those are adjacent and tempting. They are not this product. Adjacent opportunities surface in the roadmap only after the core lane is validated.

## Target Buyers

Two primary personas, one secondary.

### P1 — Active local investor (primary)
Buy-and-hold, flip, and small-portfolio landlords working within 60 miles of York. Typical profile: 5–200 parcels under management; spends an hour a day scanning tax-sale lists, Facebook investor groups, MLS alerts. Wants to be the first to know when a target property goes distressed, changes hands, or comes up for a zoning hearing.

**Willingness to pay:** $50–$150 / month for the signal. Much higher if it closes one deal.

**Jobs to be done:**
- "Tell me when a parcel I care about changes — sale, delinquency, zoning, proceeding."
- "Who really owns this LLC, and what else do they own in the county?"
- "Find me off-market distressed property matching these criteria."
- "Is this municipality trending toward or away from development approvals?"

### P2 — Small-to-mid local developer (primary)
Builders, land developers, site-selection consultants doing 3–30 projects a year. Wants to track corridor activity, pending subdivisions, and zoning hearings across municipalities.

**Willingness to pay:** $200–$500 / month for multi-seat team access.

**Jobs to be done:**
- "What's moving through the planning pipeline in Municipality X this quarter?"
- "Show me every parcel in this growth corridor with an active plan, sale, or hearing."
- "Who is the competing developer in this area — what's their portfolio?"

### P3 — Commercial broker / analyst (secondary)
Sourcing deals and pitches. Wants portfolio views of owners and corridor narratives for client memos. Secondary because they close fewer deals and price-compare against free/cheap national data.

## The Product Thesis

**The moat is not data — it's synthesis.** Parcels, assessments, tax claims, licenses, sheriff sales, deeds, and incorporations are all public. Regrid and ATTOM already sell the raw layers nationally. CountyIQ's defensible position is that it:

1. **Links entities across sources** — the same LLC in PA DOS, the same person as grantee on a deed and applicant in a variance hearing.
2. **Extracts structured records from unstructured PDFs** — every ZHB, Planning Commission, and Board of Supervisors meeting minute in every York County municipality, converted into queryable proceeding records.
3. **Builds evidence-backed case files** — changes, parcels, projects, entities, relationships, and a grounded next step in one investigation path.
4. **Surfaces changes on watched records** — the investor's retention loop.
   "A parcel on your watchlist changed in the latest weekly refresh."

None of this is easy to replicate at the county level. Everyone has the parcels. Nobody has the synthesis.

## Surfaces (What The Product Is, Concretely)

Each surface maps to one or more pipeline outputs. These statuses describe the
local alpha codebase; they do not imply that CountyIQ is deployed.

| Surface | Pipeline source | Status |
|---|---|---|
| Property page (`/property/:pidn`) | parcels, tax_claims, flood, structures, Pass 2 evidence, Pass 3 brief | Implemented locally, including cross-signal insight and linked proceedings. |
| Owner page (`/owner/:id`) | stable `public.owners` identity + licenses + portfolio | Compatibility route; uses the same identity contract as entity case files. |
| Entity case file (`/entity/:id`) | stable `public.owners` identity with Pass 1 aliases, relationships, verification, events, portfolio, and cached brief | Implemented. |
| Project case file (`/project/:key`) | source-backed event timeline with connected entities, parcels, municipalities, and local watch action | Implemented alpha; notifications and server persistence remain later work. |
| Development radar (`/radar`) | `public.development_momentum` | Implemented locally. |
| Distressed parcels (`/distressed`) | tax claims + sheriff sales composite | Implemented behind the restricted-distress feature gate. |
| Intelligence feed (`/feed`) | deterministic parcel/tax events + cached Pass 0 development extraction | Unified event cards with evidence, relationships, event tags, and next actions are implemented. |
| Watchlist (`/watch`) | browser-local entity, project, and parcel watches + `/api/feed` filters | MVP live; server-side persistence and notifications are not built. |

## Entity Profile Contract

The entity case file uses `public.owners` as the single stable identity space.
Pass 1's `public.entity_graph` output is folded into these rows by owner
resolution rather than exposed as a competing ID system:

- `GET /api/entities/:id` and `GET /api/owners/:id` resolve the same stable ID.
- `/entity/:id` presents verification context, resolvable relationships, linked
  intelligence, cached portfolio synthesis, and parcel portfolio.
- Feed cards link recognized names to the case file; unresolved names remain
  explicitly labeled instead of being force-merged.

## Monetization (Directional, Not Committed)

The product must validate desire before pricing. Current hypothesis:

- **Free tier:** search, property pages, county feed, and a small local watchlist.
- **Investor ($79/mo):** server-backed watchlists, refresh-to-refresh change
  flags, and full entity portfolios.
- **Pro ($249/mo):** team seats, CSV export, API access, saved searches, corridor-scan subscriptions.

Price discovery happens via manual outreach to ~10 local investors before any paywall ships. We are not putting paywalls on the site until we have conversations.

## Current Non-Goals

- Simultaneously loading multiple counties into the current county-local schema.
  County manifests and one-stack-per-county deployment are supported; see
  `docs/operations/county-onboarding.md`.
- Mobile app.
- Native map drawing tools beyond what MapLibre provides.
- MLS integration.
- Integrations with CRMs (Salesforce, HubSpot, etc.).
- AI chatbot / unrestricted "ask a question" interface. Case files are the synthesis surface; chat is not.

## Immediate Delivery Sequence

This is ordered by what can produce a trustworthy product trial now, not by a
calendar estimate.

- Surface **cross-signal insight** (from `meta.intelligence_passes.cross_signal_insight`) on property page. **Built in this pass.**
- Surface **linked proceedings** (zoning hearings, subdivision applications) on property page. **Built in this pass.**
- Build the **unified intelligence feed** over deterministic parcel/tax changes
  and cached Pass 0 municipal extraction. **Implemented; live migration,
  backfill, and product QA remain.**
- Let users **watch projects and parcels** directly from evidence-backed event
  cards. **Browser-local MVP implemented.**
- Build the **entity case file** (`/entity/:id`) on the stable owner identity,
  link it from events, and support entity watches. **Implemented and browser-tested.**

### After observed user demand

Build these only after product trials show that users return to watched records.

- Clerk auth, role = `investor` / `developer` / `admin`.
- `public.watchlists` + `public.watchlist_items` (parcel, entity, municipality, corridor).
- Event log (`public.watchlist_events`) — Dagster sensor fires one row per change that matters to anyone's watchlist.
- Upgrade the existing `/watch` UI to server persistence.

### Distribution and price discovery
- 10 investor interviews (target list: York Builders Association, PA REIA chapter).
- One-page landing at the root with "what you get" + form.
- Paid pilot with 3 investors at $79/mo; no billing infra, invoice by hand.
- Instrument usage: which pages viewed, which briefs read, which watchlist items fire.
- Decide Phase D on revenue signal.

## Open Strategic Questions

Worth naming so we don't rediscover them in 60 days.

1. **Assessment data:** the scraper is live on the weekly schedule even though
   commercial-use terms remain ambiguous. Decide whether to accept that risk,
   disable it, or replace it with licensed data.
2. **Multi-seat pricing:** developers want team access; investors want cheap. Two SKUs or one?
3. **Data-broker exposure:** selling investor-targeted signals against public data on people (tax delinquency at a known address) has reputational risk. The Phase 2 auth gate + audit log in `docs/privacy.md` is the mitigating control. Not sufficient for a "find distressed owners" mailing-list product — which we're not building.
4. **County #2 selection:** which adjacent county has both observed user demand
   and a source/rights profile that clears the onboarding gates?

## Working Principles

- **No feature ships without a mapped buyer job.** Every surface answers a specific question P1 or P2 asks. If it doesn't, it's a portfolio project, not this product.
- **Retention first, acquisition second.** The alert loop is worth more than the landing page.
- **Evidence-backed case UI.** Lead with current changes, connected subjects,
  and the original record. Cached Pass 3 synthesis supports the case; Pass 4 is
  off by default.
- **Evidence, not magic.** Every claim in a brief or narrative cites its source. If users can't click through, they won't trust it.
