# Emerging intelligence and opportunities

Status: bounded local implementation, September 8, 2026. The product owner has
explicitly expanded CountyIQ beyond monitoring documented activity. The accepted
objective is to connect evidence, form and revise hypotheses about emerging
projects, and explain useful investor and service-business actions.

## Initial hypotheses

| Family                | Customer question                                                             | Commercial value to test                                               |
| --------------------- | ----------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Business expansion    | Is a business preparing a larger or different operation?                      | Early contractor, equipment, brokerage and acquisition research.       |
| Land assembly         | Are connected transactions and land-use actions forming a development site?   | Identify an assembled site, pivotal parcel or development participant. |
| Construction timing   | Is an identified project moving toward work that remains contestable?         | Better timing for a specific service or bid qualification.             |
| Infrastructure unlock | Could a specific infrastructure change remove a constraint for these parcels? | Focus land diligence and infrastructure-related service research.      |
| Use transition        | Is a property preparing for a different use or operator?                      | Reuse diligence and work associated with a documented transition.      |
| Project stall         | Is a project facing a material delay or change in direction?                  | Avoid wasted effort and recognize a changed commercial situation.      |

These are product hypotheses about customer value, not validated demand. Data
centers, manufacturing, logistics, housing and retail are potential project uses
within these families. Do not label an intensive use as a data center without
distinguishing evidence, or attribute a company from similar names alone.

## Customer journey

**My work criteria → relevant cases → evidence, interpretation and commercial
relevance in one case → pursue/follow/dismiss → return through My work.**

The first preview duplicated research actions in Opportunities. Customer review
identified that as a weak product boundary. The revised queue admits only
qualify/act possibilities with source-backed commercial need, timing and a
qualification route. Generic research stays inside the case. Customer pursuit
does not promote a research hypothesis into a qualified opportunity.

Activity continues to describe what the record establishes. Emerging intelligence
describes what connected facts may mean. Opportunities describe a possible
commercial action for an investor or service business. An inferred project and
an open procurement are different conclusions. Qualification of an acquisition
requires additional economics and site-control evidence.

Every hypothesis presents its supporting facts, contrary evidence, alternative
explanations, unknowns and next discriminating checks. Show evidence strength
separately from opportunity action readiness. No numerical probability, return,
seller motivation, construction date or contact detail is manufactured.

## Implementation contract

The frontend contract lives in `frontend/src/types/emerging.ts`.

- `GET /api/intelligence` lists current cases, with optional `family`,
  `municipality`, `audience`, `service`, `q`, `pidn`, `case_key`,
  `opportunities_only`, `project_type`, `readiness`, `exclude_case_key`, `limit`,
  and `offset` filters. List-valued parameters may repeat. All selection and
  exclusion occurs before paging. Service selection applies to service-business
  possibilities; a retained service selection cannot hide investor cases.
- `GET /api/intelligence/{case_key}` returns one current case or 404 when it
  does not exist or its supporting source scope is no longer current.
- Customer copy is English and citations use the existing source viewer.
- Source facts and input membership are checked again when serving; an older
  interpretation cannot survive changed/revoked evidence as if still current.
- The same seed scope and family retain a stable case key across revisions.
- Profile and case workflow are private workspace state; they are not evidence
  and cannot alter the underlying hypothesis. Saved stale case keys may remain,
  but stale source-derived titles and prose must not be retained as notifications.
- Reading pages does not make model calls. Generation is bounded and opt-in;
  existing source policies and inference provenance remain in force.

## Evidence scope and evaluation

Start from current source-backed municipal retrieval scopes and collect linked
parcel context plus bounded adjoining parcels and their records. Retrieval
relationships do not assert project membership, common beneficial ownership or
causation. Preserve explicit scope limits and unavailable source families.

Tests must cover wrong-site borrowing, common-name ambiguity, duplicate records,
future-information exclusion, incomplete inputs, unsupported company attribution,
stale/withdrawn evidence, and already-awarded or completed work. Historical replay
distinguishes record-date reconstruction from information actually available at
the cutoff; the former does not establish real-world early-warning lead time.

Validate initial cases on real local records and keep negative cases. Browser
acceptance requires desktop and 390px phone journeys: choose a hypothesis, read
why/alternatives, open a source, inspect a related property, choose a relevant
commercial action, save a case, and return with the correct status. No customer
interviews, successful investments or won contracts are claimed by technical tests.

## Initial delivery and operating path

The local implementation adds Emerging intelligence to the shared workspace
navigation, with Opportunities as a view inside it and My work as the private
return destination. Overview includes reviewed cases and saved case work. Case
pages expose source receipts, stage, alternatives, counter-evidence, unknowns,
next checks and audience-specific commercial actions. Profile criteria and paging
are encoded in URLs; filtering occurs on the server before pagination. Guest work
is exportable; signed-in work uses the existing account isolation and conflict
checks. A saved case retains its key, personal status/note and last-seen revision,
so a withdrawn case cannot leave stale source-derived copy in the workspace.

The initial preview contains four AI-reviewed, source-backed examples:

| Case                                                   | Interpretation to investigate                                                                  | Immediate customer value                                                                                   |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Carvana, 115 Industrial Road, Conewago Township        | A new car-auction building may add or reorganize operating capacity.                           | Qualify civil, construction, sitework and equipment needs after verifying the plan and contracting status. |
| 110 Yoe Drive, York Township                           | Connected rezoning and subdivision agenda items suggest a residential or mixed-use transition. | Investigate entitlements and any unassigned design/sitework scope.                                         |
| Musser Farm, 4390 Board Road, East Manchester Township | Proposed industrial and apartment/office district allocations may change development options.  | Screen the affected portions separately and check the application outcome.                                 |
| Dalfen Industrial Warehouse, Shrewsbury Borough        | A reverse-subdivision item may indicate site consolidation.                                    | Obtain the plan to distinguish substantive development preparation from administrative boundary work.      |

All commercial implications in these examples have **research** readiness. They
now remain inside their intelligence cases and produce **zero qualified
opportunities**. The five former opportunity entries are early implications.
No site
availability, unassigned contract, rental demand, construction start or return is
asserted. Nine additional reviews deliberately abstain: seven general data-center
ordinance scopes, a Carvana sewer-module title without a site link, and the Eagle
Rock water-extension bond-reduction action. A bond release is not an open project.
These are selected review examples, not an independently measured precision score.

### Generation and publication

The current generation schema requires project-type labels (empty when unknown)
and a nullable `commercial_basis` for each commercial possibility. Qualify/act
requires exact retained claims for need, timing and qualification route. Multiple
distinct possibilities may share an audience, up to eight per hypothesis.
Source-meaning review remains essential: matching a literal quote does not prove
that the inference correctly interprets it. Legacy analyses remain readable, but
missing commercial qualification cannot be supplied by the presenter. Legacy
project types remain unknown until reassessed. No stored analyses were silently
rewritten to populate the new queue.

Migration `081` adds source-current serving views and an immutable publication
review ledger. The manual `emerging_intelligence_refresh` Dagster job accepts at
most ten explicit bundle keys and generates drafts through the existing Pass 4
backend, item limits and spend controls. It has no schedule. Empty scope makes no
model calls. A changed hypothesis on unchanged evidence is quarantined, including
changes to its prose or commercial action; the initial publication command cannot
release a quarantined challenger. This conservative rule can also hold wording
corrections for further operator review.

From `pipelines/`, the `scripts/emerging_intelligence.py` CLI supports:

1. `list --limit 20` to inspect candidate scope keys.
2. `export --bundle KEY --output PACKET.json` for one canonical source packet.
3. `generate --packet PACKET.json --output ANALYSIS.json` for a configured model
   draft, or an independently authored analysis using the same schema.
4. `import --packet PACKET.json --analysis ANALYSIS.json --author LABEL` to
   validate and retain it. This does not publish.
5. `review --inference-id ID --action publish --reviewer LABEL --rationale TEXT`
   only after checking source meaning, alternatives and commercial qualifiers.
   `--action withdraw` immediately retracts the reviewed interpretation.

Set the standard `DATABASE_*` variables for CLI/asset execution. Alembic instead
uses an explicit `DATABASE_URL`; setting only `DATABASE_PORT` does not redirect a
migration. The example database and browser preview are local and isolated from
production. No provider-paid generation, source backfill, deployment or outreach
was performed for this delivery.

Every source bundle is rechecked at publication and serving. The API reuses a
bounded snapshot only while a transactional revision of **all** source, context,
rights and publication dependencies and the policy date still match. Changed
source membership, geometry/context, rights or publication invalidate the cached
result. On the local full-data copy, the first four-case/13-scope check took about
10 seconds; a subsequent filtered read took about 4 milliseconds. Cold checks
need further optimization before a much larger pilot corpus.

## Data gaps and next priorities

| Gap                                        | Current handling                                                                                                          | Next useful addition                                                                                   |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Specific utility service/capacity          | Adjacency is context; no inferred connection or capacity.                                                                 | Source-specific service commitments, interconnection requests and named project utility plans.         |
| Corporate control and related acquisitions | Exact recorded names and geometric adjacency remain labeled retrieval relationships.                                      | Verified entity/transaction chains, with cited links to the actual site and time-bounded ownership.    |
| Approvals versus starts                    | Procedural stage, missing decisions and next checks are explicit.                                                         | Complete permit, inspection, start and completion histories.                                           |
| Contestable commercial work                | Research/qualification includes blockers and disqualifiers.                                                               | Current bid notices, awards, appointed contractors and remaining packages.                             |
| Historical availability                    | Cutoffs require both record date and original observation time; current GIS and neighboring-scope discovery are excluded. | Frozen contemporaneous packets and later outcomes for prospective lead-time evaluation.                |
| Source selection completeness              | Coverage exposes assessed scopes and missing source families.                                                             | A repeatable county-wide selection/reassessment queue after generation quality and cost are evaluated. |

The packet currently combines source-backed municipal scopes, current parcel/GIS
facts and bounded adjoining-parcel records. It does not yet traverse every
corporate graph edge or reconstruct a complete deed history. More speculative
company-intention or data-center predictions require the discriminating evidence
above. This boundary preserves useful early hypotheses without laundering
proximity, a name match or a policy discussion into a factual project claim.
