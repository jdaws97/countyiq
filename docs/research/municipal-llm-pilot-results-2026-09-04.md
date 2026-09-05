# Municipal LLM pilot — September 4, 2026

**Keep the project and municipal-policy features. Do not start the full LLM backfill yet.**
The 30-document pilot cost **$0.06920453** and surfaced **35 distinct development-lead groups across 10 municipalities** after qualitative review and obvious duplicate consolidation. These are leads to investigate, including pending and denied proposals, not 35 verified active construction opportunities. The data is useful; evidence formatting, project identity, parcel attribution, and procedural dates need correction before publication.

## What ran

The frozen [pilot manifest](municipal-source-pilot-2026-09-04.json) selected 24 likely property/policy documents and six documents the existing prefilter would skip. All 30 remained eligible and matched their source-text hashes at dispatch.

- Existing model: openai/gpt-5.6-luna, text-only Pass 0, current system prompt and strict schema.
- 30 calls, no semantic retries, $2 authorized cap, durable reservations and provider-cost reconciliation.
- Actual provider: OpenAI for all calls. Full prompts, source text, raw responses, parsed results, and costs are archived.
- Evaluation output limit: 8,192 tokens. Unoverridden runtime default is 4,096. The longest completion was 3,779 tokens; this still is not an exact-settings production release evaluation.
- Codex source-by-source qualitative review, **not independent human adjudication or a formal field-level precision/recall benchmark**.
- No extraction was published. The real database still contains zero proceeding extractions and 175,928 current parcels. Synthetic fixtures were not added to real data.

## Measured results

| Measure | Result |
|---|---:|
| Successful calls / valid JSON-schema documents | 30 / 30 |
| Documents passing the existing evidence gate | 13 / 30 |
| Nonempty documents passing that gate | 9 / 26 |
| Raw extracted matters | 108 |
| Individual matters with passing supporting quotes | 69 / 108 |
| Matters surviving the all-or-nothing document gate | 32 / 108 |
| Provider-reported cost | $0.06920453 |
| Average cost per document | $0.00231 |
| Pipeline tests | 1,011 passed; 71 integration tests deselected |

The 108 outputs are not 108 useful projects:

| Qualitative product category | Output records |
|---|---:|
| Explicit development leads | 39 (35 distinct reviewed groups) |
| Property follow-up, scope still unclear | 18 |
| Minor property / lot-adjustment matters | 20 |
| Land-use policy | 14 |
| Public or utility projects | 6 |
| Background, maintenance, or compliance | 9 |
| Adjacent commercial licensing | 1 |
| False project inferred from boilerplate | 1 |

The sample was deliberately enriched. These counts establish that useful material exists; they do not predict countywide prevalence or completeness.

## What customers would find useful

- **Prosper Development, Conewago:** approximately 73 multifamily dwellings, appearing before both Planning Commission and Zoning Hearing Board. A pending application, not an approval.
- **Estates at Honey Run, West Manchester:** 35 residential lots in Phase 1, with a Planning Commission recommendation and substantial remaining conditions.
- **Raising Cane's, West Manchester:** demolition/redevelopment of the Lyndon Diner site for a 3,432-square-foot restaurant; tabled for further review.
- **The Learning Experience, West Manchester:** proposed 10,000-square-foot daycare and 6,000-square-foot office building.
- **Messiah Homes, Fairview:** courtyard-home phase of a continuing-care community; the board denied the requested separation variances. Useful risk/context, not permission to build.
- **Hanover:** Walmart expansion, Fairfield Inn revisions, a potential motel, and a dispensary application.
- **Municipal policy:** data-center rules, solar overlays, and special-event/winery zoning amendments are useful watch topics without pretending each is a parcel development.

A searchable project directory and signed-in watch experience are justified. Default discovery should emphasize substantive development. Minor pool/chicken/driveway cases belong in property history or optional filters; public works and municipal policy deserve separate filters. Include source links, exact evidence, procedural status, last-confirmed dates, and location confidence.

## Fix before backfill

### 1. Reliable evidence quoting

**17 documents failed the evidence gate; 39 individual quotes failed.** Many responses join nonadjacent passages using ellipses or remove intervening agenda lines, despite claiming to provide one exact quote. One bad quote currently rejects every extraction in that document.

Use independently verifiable evidence spans, or require a single contiguous excerpt if retaining the current schema. Decision, condition, date, and property claims need supporting spans. Do not accept fuzzy text or merely remove ellipses: that would not establish support for the whole claim.

Retain rejected responses and measure corrected output against the same documents and a held-out set. Consider item-level quarantine only with complete accounting of missing/rejected matters, so partial output cannot masquerade as a complete document.

### 2. Boilerplate and procedural stage

- **1174, extraction 2:** “Next Conditional Use Case # CUH 2026-10” is a generic footer reserving the next case number, not a filed project. The model created a high-confidence case and it passed the quotation gate.
- **1171, extractions 3–4:** real cases CUH 2026-8/9 incorrectly received the generic August 3 submission deadline from the footer.
- **5153:** decisions correctly remain null, but “considered” describes agenda items as completed deliberations. Use “listed for review”; unselected approve/deny templates prove no vote.
- Standing committee goals, routine compliance reviews, unlocated permit administration, and ordinary repairs should not become new development alerts.
- Several outputs tag routine discussion as a hearing. Separate scheduled items from completed events.
- **2225:** the source itself disagrees on a November 2025/2026 letter date. Preserve and flag the conflict rather than silently choosing a corrected date.

### 3. Parcel attribution

A read-only replay of current matching SQL found matches for **29 of 108 outputs**; nine belonged to documents passing the evidence gate. These are matches, not verified parcel attribution.

**Four street-only references** matched assessment rows: Steamboat Boulevard, Game Club Road, Meadow Street, and Orwig Road. Orwig Road attached six unnumbered parcels to the SolAmerica mention; Meadow Street attached ten to a drainage contract. The source does not identify those parcels.

Require a supported full parcel ID or sufficiently specific address, municipality consistency, and explicit ambiguity handling. Street/intersection-only references remain project-level locations. Even numbered addresses can map to multiple parcels: 127 N. West Street returned two.

Conversely, multi-parcel references are currently treated as one string and fail. Isolating explicitly printed full IDs recovered six existing parcel matches across the Cardinal Lane, Long Level Road, and East Manchester overlay records. Keep each reference separately; do not invent missing IDs or use a broad street match to fill gaps. Address-plus-tax-map strings and city/state suffixes also need structured parsing.

### 4. Stable projects and actual event dates

Six of eight manually reviewed related-matter groups generated different runtime project keys. Examples include Prosper across boards, Sprich across months, and the same East Market redevelopment across procedural stages. Hashing LLM-written names and free-text locations splits watch history when wording changes.

Prefer municipality plus explicit application/plan identifiers, with deterministic reviewed relationships between applications belonging to one project. Store multiple applications and events under that project. Do not merge unrelated projects merely because they share a parcel.

Keep meeting date, event date, and future deadline separate:
- Hanover's August 5 agenda reports July 20 decisions.
- Warrington's July 15 minutes report the March 11 moratorium.
- Jacobus's July 1 minutes report a June 29 zoning approval.

The current event builder uses the containing meeting date, making historical actions look newer. Expired next dates must not appear as current upcoming decisions.

### 5. Customer-specific recall and prefilter coverage

Four controls returned empty results. The other two contained a site-specific restaurant liquor-license transfer and park work; neither supports treating every prefilter-negative document as irrelevant. The fill-permit item is too vague for a standalone project.

The model also omitted relevant items in processed documents: a conditional-use fee amendment in Dillsburg, a proposed $350,000 fire-company social-hall remodel in Jacobus, and public-works bidding in East Manchester/East Hopewell. Public-works extraction is inconsistent.

Align liquor licensing with the existing licensing feature and make public works an explicit category if included. Add these controls and omissions to regression cases. Do not claim a measured recall percentage from this small enriched sample.

## Costs and reductions

The measured cost is already small: about **$0.00198 per distinct reviewed development-lead group**, allocating the entire pilot cost to those groups. This is an acquisition-cost diagnostic, not the cost of a production-approved project.

At the same mix and lengths, scaling the all-document average to 494 documents is about **$1.14**. Scaling the 24 prefilter-positive average to 476 positive candidates is about **$1.31**. These are rough Pass 0 projections, not spending authorizations or bounds. They exclude retries, later LLM passes, PDFs/OCR fallback, infrastructure, review, and price changes.

Measured usage: 115,824 input tokens, 45,389 completion tokens, 11,001 reasoning tokens, and 61,799 cached input tokens. The provider used reasoning despite the local thinking=False setting because reasoning effort was left unspecified. Benchmark explicit no-reasoning against these difficult cases before changing production; do not assume the boolean disables provider-default reasoning.

The provider snapshot lists a cache-write price above its normal prompt price. Keep actual returned cost authoritative and account for cache writes when maintaining price/reservation ceilings.

Prioritize:
1. Cache accepted extraction by source/prompt/settings identity and build multiple customer views from it.
2. Fix avoidable quote failures and suppress unchanged boilerplate before paying for retries.
3. Keep text-first input and the reused system prefix; this run obtained substantial input-cache reuse.
4. Benchmark explicit reasoning effort and shorter grounded evidence output after correctness is stable.
5. Run later expensive interpretation only when a customer-facing result needs it.

A cheaper-model migration is not the immediate priority. Seven cents exposed defects that matter much more to customers than another small token-price reduction.

## Acceptance for the next run

Do not approve the production release receipt or launch the full backfill from this pilot.

Before a corrected bounded rerun:
- Freeze the revised prompt/schema and exact production settings.
- Add the demonstrated boilerplate, agenda/decision, history-date, multi-parcel, street-only, and duplicate cases.
- Require zero known false-project, false-approval, or unsupported parcel/owner associations on those cases.
- Verify published claims have valid evidence spans and partial/rejected extraction states are visible.
- Verify watch identity holds across the reviewed cross-board/month cases.
- Review relevance and missed-matter counts against source-level expectations, then validate on a held-out sample.
- Follow the existing [LLM product release process](../operations/llm-product-release.md) for human-reviewed quality approval.

## Reproducibility

Code: pipelines/eval/municipal_pilot.py. Tests: pipelines/tests/test_municipal_pilot.py. Preparation is the default; paid calls require --run, an explicit manifest, a new output directory, and a cap no higher than $2.

Artifacts are local and gitignored under output/municipal-pilot-2026-09-04/:
- protocol.json, manifest.json, sources.json: frozen inputs and settings.
- transcripts/, results.json: original paid responses and usage.
- spend-authorization.json: durable budget accounting.
- semantic-review.json: item-level qualitative review and related-matter groups.
- linkage-review.json: read-only runtime-match replay and diagnostic full-ID lookup.
- provider-model-snapshot.json: provider metadata captured before calls.

The companion [machine-readable summary](municipal-llm-pilot-results-2026-09-04.json) is tracked. Original model output and production prompts were not rewritten to make the baseline pass.
