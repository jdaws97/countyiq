# Real Estate Intelligence (Product Direction)

This is the active product lane for CountyIQ. It names the buyer, the jobs the product does, what we will and won't build, and how existing assets map to revenue.

## Lane

CountyIQ is a **county-grade real-estate intelligence platform for private-market investors and developers operating in South-Central PA**, starting in York County and expanding to adjacent counties (Lancaster, Cumberland, Adams, Dauphin) after product-market fit is established in York.

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
3. **Synthesizes cross-parcel narratives** — corridor scans, distress clusters, portfolio trajectories.
4. **Fires alerts on change** — the investor's retention loop. "A parcel on your watchlist had a zoning hearing filed yesterday."

None of this is easy to replicate at the county level. Everyone has the parcels. Nobody has the synthesis.

## Surfaces (What The Product Is, Concretely)

Each surface maps to one or more of the five pipeline outputs. The roadmap below is how these surfaces get built over the next 90 days.

| Surface | Pipeline source | Status |
|---|---|---|
| Property page (`/property/:pidn`) | parcels, tax_claims, flood, structures, Pass 2 evidence, Pass 3 brief, Pass 4 narratives | **Live.** Adding cross-signal insight + linked proceedings. |
| Owner page (`/owner/:id`) | owner resolution + licenses + delinquency | Live. Redirects to entity profile once live. |
| Entity profile (`/entity/:id`) | Pass 1 `public.entity_graph` | **Designed, not built.** The moat. Shows canonical name, linked names, portfolio, relationships. |
| Development radar (`/radar`) | `public.development_momentum` | Live. |
| Distressed parcels (`/distressed`) | tax claims + sheriff sales composite | Live. |
| County feed (`/feed`) | Pass 4 `public.county_narratives` | **Net-new.** The weekly digest, in-app. |
| Watchlist + alerts (`/watch`) | event log over parcel / proceeding / evidence changes | **Designed, blocked on Clerk auth.** |
| Weekly email | County feed + per-user alerts | Blocked on Clerk + SMTP. |

## Monetization (Directional, Not Committed)

The product must validate desire before pricing. Current hypothesis:

- **Free tier:** search, property pages, county feed, up to 5 watchlist items (when auth lands).
- **Investor ($79/mo):** 100 watchlist items, instant alerts, entity-profile full portfolio, weekly email digest.
- **Pro ($249/mo):** team seats, CSV export, API access, saved searches, corridor-scan subscriptions.

Price discovery happens via manual outreach to ~10 local investors before any paywall ships. We are not putting paywalls on the site until we have conversations.

## Non-Goals For The Next 90 Days

- Multi-county expansion code paths beyond what `county_config.py` already supports. No county #2 work until York is monetizing.
- Mobile app.
- Native map drawing tools beyond what MapLibre provides.
- MLS integration.
- Integrations with CRMs (Salesforce, HubSpot, etc.).
- AI chatbot / "ask a question" interface. Pass 4 narratives are the synthesis surface; chat is not.

## Roadmap (Next 90 Days)

### Phase A — Finish extracting latent value (weeks 1–2)
Everything below is built or designed; the value is mostly in wiring and UI. No new pipelines.

- Surface **cross-signal insight** (from `meta.intelligence_passes.cross_signal_insight`) on property page. **Built in this pass.**
- Surface **linked proceedings** (zoning hearings, subdivision applications) on property page. **Built in this pass.**
- **County feed page** (`/feed`) rendering Pass 4 narratives. **Built in this pass.**
- Build **entity profile page** (`/entity/:id`) over `public.entity_graph`. **Designed; next work.**

### Phase B — Retention loop (weeks 3–6)
Requires Clerk auth (was already gated behind Phase 2 in the privacy doc). This is the single biggest conversion lever.

- Clerk auth, role = `investor` / `developer` / `admin`.
- `public.watchlists` + `public.watchlist_items` (parcel, entity, municipality, corridor).
- Event log (`public.watchlist_events`) — Dagster sensor fires one row per change that matters to anyone's watchlist.
- Watchlist UI at `/watch`.
- Weekly email digest (Mailgun or SES — decide on cost-vs-ops grounds).

### Phase C — Distribution and price discovery (weeks 7–12)
- 10 investor interviews (target list: York Builders Association, PA REIA chapter).
- One-page landing at the root with "what you get" + form.
- Paid pilot with 3 investors at $79/mo; no billing infra, invoice by hand.
- Instrument usage: which pages viewed, which briefs read, which watchlist items fire.
- Decide Phase D on revenue signal.

## Open Strategic Questions

Worth naming so we don't rediscover them in 60 days.

1. **Assessment data:** the scraper is built but not wired because commercial-use terms are ambiguous. If the product needs historical assessment values (probable for "undervalued property" queries), we need a legal read or a licensed data swap.
2. **Multi-seat pricing:** developers want team access; investors want cheap. Two SKUs or one?
3. **Data-broker exposure:** selling investor-targeted signals against public data on people (tax delinquency at a known address) has reputational risk. The Phase 2 auth gate + audit log in `docs/privacy.md` is the mitigating control. Not sufficient for a "find distressed owners" mailing-list product — which we're not building.
4. **County #2 threshold:** at what ARR do we start investing in Lancaster or Cumberland? Default: $10K MRR in York first.

## Working Principles

- **No feature ships without a mapped buyer job.** Every surface answers a specific question P1 or P2 asks. If it doesn't, it's a portfolio project, not this product.
- **Retention first, acquisition second.** The alert loop is worth more than the landing page.
- **Synthesis-forward UI.** Pass 3 briefs and Pass 4 narratives are the differentiator; lead with them, not with a data table.
- **Evidence, not magic.** Every claim in a brief or narrative cites its source. If users can't click through, they won't trust it.
