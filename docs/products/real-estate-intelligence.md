# CountyIQ product direction

Updated September 5, 2026. This is the launch hypothesis, not evidence of
customer demand or willingness to pay.

## The first customer and job

Start with small land developers and acquisition teams working in York County,
Pennsylvania. They need to follow proposals and municipal decisions across
separate websites, understand which property a record concerns, and return when
something changes. Local investors and brokers can use the same workflow;
they do not need separate products or pricing tiers at launch.

**Promise:** Follow local development. See the evidence.

The customer should be able to answer: What is happening here, what record
supports it, and what should I keep watching? A search, an owner profile, a map,
and an interpreted brief support that job. None is a separate product.

## The complete customer path

1. The public landing page explains the York County scope and offers a pilot
   inquiry. Invited customers sign in at `app.countyiq.net`.
2. Start with a known address or municipality. A new workspace offers search
   immediately; returning customers see saved work and recent investigations.
3. Open a property. Lead with meaningful development signals, then assessment,
   recorded transfers, ownership links and source evidence. Assessed value is
   labeled explicitly; a recorded sale amount is not a market valuation.
4. Use the map to understand the property and its surroundings. Fit the full
   selected parcel, show a clear legend, and load optional reference layers on
   demand. Missing footprints are a vacancy screen, not verified current use.
5. Read the original record. Distinguish applications, recommendations,
   procedural changes and completed decisions. Proximity does not prove that
   a proposal includes a parcel; shared names do not prove common ownership.
6. Watch the property, project, organization or municipality. Verified accounts
   save work across devices. Newly matched events appear in the persistent
   inbox after source refresh. Browser alerts require opt-in and an open app;
   background push and email alerts are not offered.

An empty activity feed must explain publication/coverage limits and offer a
useful next step. It must not imply that no development occurred in the county.
A customer must still find value through property search, source records and
the deterministic radar while municipal publication is limited.

## What the scores and briefs mean

Radar ranks a shortlist using documented signals. It does not establish that a
property is available, that an owner wants to sell, or that development is
permitted. Opportunity, momentum and site scores remain distinct and their
supporting facts stay accessible.

Briefs give one of three actions: investigate a specific documented activity,
watch a change that lacks corroborating project activity, or identify
insufficient evidence for a development lead. Generic advice to look up deeds
or zoning is not enough to recommend investigation. Briefs do not infer urgency;
source-backed dates are displayed separately.

Generated interpretation is optional to the customer workflow. Reading the
product makes no model calls. Pass 4 county narratives, unrestricted AI search,
judges and escalation stay disabled until there is a demonstrated need and a
separate evaluation.

## Pilot and sale

Offer one guided York County pilot. Ask each tester to bring a real property or
municipality they currently research. Help them reach the original evidence
and save their first watch in that session. Review the next source refresh with
them to learn whether the saved work brings them back.

The first price hypothesis is **$79 per month per customer**, including the
existing York County workspace. Do not publish a price, build billing, or
invent feature tiers before actual pilot conversations establish value. No
interviews, paying customers or revenue are claimed by this plan.

Acceptance for a useful pilot:

- The tester finds a relevant record and understands its property relationship.
- They can distinguish a recorded fact from an interpretation and open its source.
- They save an investigation and can find it again after signing in elsewhere.
- A later matching change is useful enough to bring them back.
- They can explain what CountyIQ replaces in their current workflow and whether
  they would pay for it.

Use direct, individually authorized conversations with local builders,
land-development professionals and brokers. Prepare outreach and a short demo;
do not send messages or represent fabricated customer results. Measure observed
behavior and interview notes before adding analytics infrastructure.

`hello@countyiq.net` is the intended pilot contact. Publish it only after the
mailbox is configured and delivery is verified. Cloudflare domain registration
alone does not create that mailbox.

## Scope discipline

Ship one county and one investigation workflow. Team administration, CRM
integrations, public API plans, mobile apps, MLS listings, national expansion,
lead lists and beneficial-owner identification are outside this launch.
Use the existing workspace, watches, comparison and source receipts. Add a
feature only when an observed customer task cannot be completed with those.

## Release evidence

Implementation and production readiness are tracked separately in
[the launch record](../operations/production-launch-2026-09-05.md).
The [LLM release gate](../operations/llm-product-release.md) and
[canary runbook](../operations/intelligence-rollout.md) govern publication.
The user must approve the full backfill after the final reviewed canaries;
this product direction does not authorize it.

## Municipal discovery scope

A specifically identified land development plan is useful even when an agenda
omits the proposed use or building size. Classify it as `plan_review` and preserve
that uncertainty; do not infer construction, units or an approval. Generic plan
headings, bond-only history, extensions and minor property adjustments remain
context. Identified capital upgrades and their bidding stages are discoverable
with the actual procedural scope visible. These are source-backed reasons to
investigate, not forecasts. This replaces the earlier requirement that every
discoverable plan state a physical construction scope. The JSON evidence contract
adds one relevance scope; no table migration is needed. Existing outputs retain
their original release identity and are not silently republished.
