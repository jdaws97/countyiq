# Municipal LLM v3: capped accuracy and cost evaluation

**Decision: do not bulk-backfill yet.** The product direction remains useful: customers can understand a property matter, distinguish a scheduled hearing from a decision, see conditions and next dates, and inspect the source. This run improves extraction yield and reduces successful-call cost. It still loses too many useful records and allows several misleading classifications.

Completed September 4, 2026, America/New_York (raw timestamps use September 5 UTC). Evaluation only; no extraction, project alias, customer feed event, or quality-release receipt was published by this work.

## Scope and results

The user approved sending the exact 40 municipal documents, including names and property addresses, to OpenRouter using openai/gpt-5.6-luna, with a **$1 total ceiling**. All 40 compatible requests succeeded, one attempt each and zero retries. OpenRouter reported OpenAI as provider and the requested model for every successful call.

The original 30 and comparison 10 have identical source text to v2. The ten were originally held out but have since been used in debugging; they are **not an unseen test set**. All 40 sources and outputs received qualitative Codex review. These are deliberately enriched samples, not independent human gold labels, formal precision/recall estimates, or a countywide coverage forecast.

| Measure | Previous v2, after date-parser replay | Current v3 |
|---|---:|---:|
| Source documents | 40 | 40 |
| Generated matters | 144 | 136 |
| Documents passing runtime gate | 6 | 16 |
| Passing documents with matters | 2 | 9 |
| Passing empty documents | 4 | 7 |
| Matters surviving document gate | 5 | 38 |
| Successful-call provider cost | $0.14069727 | $0.12126218 |

Gate success is **not** an accuracy score. Only 13 surviving matters are eligible for default discovery, and that set still contains relevance errors. Seven empty outputs include a missed roof-bidding item.

A diagnostic replay validates each item separately: **81 of 136** pass individually. The whole-document gate discards **43 individually valid items** because another item fails. Those are hypothetical recoveries, not approved records: individual validation also misses semantic mistakes.

All 40 responses satisfy the JSON schema. All **64 evidence spans in the 38 surviving records** exactly match their source offsets. Membership does not prove that a summary, classification, or decision is supported.

## What customers would find useful

- Scheduled versus completed actions improved. York's May planning agenda (5145) stays scheduled, and the hearing-script document (10274) does not invent a vote.
- Lower Windsor (6302) retains two cases, multiple parcel references and each case's August 24 decision deadline, independently of the July 16 meeting date.
- Bond reductions, withdrawals and removals have distinct states. Green Lane's bond action and Baker's removal (3178) no longer imply project approval or another continuance.
- Actual text contains meaningful signals: Prosper's roughly 73 homes, Carvana, Goodwill's proposed remodel, data-center rules, solar matters and road projects. The main issue is reliable extraction and presentation.
- The five documents the prefilter would skip all had reasonably empty outputs here. Retain the prefilter, while continuing to test its recall.

## Required fixes

### 1. Citation handling and independent item quarantine

**24 of 40 documents fail the gate.** First failures per item include 16 milestone-literal mismatches, 10 entity-literal mismatches, 10 authority citation failures and eight event-date citation failures. An item may have more errors after its first failure.

The model paraphrases a milestone accurately but the contract requires literal text. It also writes a full governing-body name while citing a paragraph that only says “Board,” or cites an item without the date header.

Separate display labels from evidence. Request literal date/milestone substrings, resolve header authority/date explicitly, and preserve original identifiers alongside normalized representations. Keep unknown passage IDs and unsupported claims rejected. After validating the document hash and boundaries, consider quarantining faulty items independently so unrelated valid matters survive. Do not publish the diagnostic 81-item set automatically.

### 2. Decision semantics and validator false positives

- **5145:** “preliminary plan be submitted and approved before a final plan” is a prerequisite. The validator treats it as completed approval and rejects a correctly scheduled item.
- **4645:** the source says the board “moved to grant” a garage variance without recording a vote result. The model labels it approved, and that item passes individual validation. Another item blocks the document.
- **2225:** approved edits to a draft data-center ordinance and referral for review are labeled an approved ordinance. They do not establish adoption.
- **296:** a paving grant listed on an agenda becomes a completed-sounding engineer-report update.

Distinguish proposed motion, carried motion, draft amendment, procedural referral and final adoption. Preserve modification/waiver scope instead of implying approval of the entire development.

### 3. Relevance at the specific matter

**10481 exposes a code bug:** the BESS ordinance and sidewalk/ADA improvements are suppressed because their 1,200-character cited passage also contains an unrelated item's “compliance rate.” Apply negative relevance checks to the claim or item boundaries, not neighboring sentences.

Homeowner pools, garages, carports and minor lot changes sometimes become development opportunities. In a document that passes today (10281), a split involving existing communication towers becomes “new lots” development; a parcel's Agricultural Security Area designation becomes general land-use policy.

Define the customer boundary: commercial construction, substantial residential supply, substantive zoning changes and named capital works versus ordinary homeowner relief, administrative parcel changes and routine supply purchases. Preserve minor matters in searchable case history.

### 4. Targeted recall and project identity

- **7600:** misses “Historical Roof – Public Bid,” under business for action.
- **1174:** invents a filed CUH case from the “Next Conditional Use Case #” footer. The validator blocks it but also loses two legitimate extension matters.
- **2225 / 9042:** omit the Casella office addition / named Cuff's Run litigation update.
- **6472:** omits a named park project's voted pavement/sign work and planned equipment installation. Adjudicate whether smaller capital milestones belong in the product.
- Generic references such as “Agricultural Security Area” and “Shrewsbury Township Grant Project” are unsafe project keys. Use typed identifiers and municipality/property context. Distinguish real identity conflicts from ordinary spelling variants.

Named early proposals often remain context-only because the agenda lacks construction detail. Keep these in history/search and enrich across proceedings before deciding opportunity eligibility.

## Cost and savings

Successful calls cost **$0.12126218**, **13.81% less** than v2: about **$0.00303 per source** in this sample, not an end-to-end backfill quote.

Three earlier requests returned HTTP 400 without usage.cost; their charges are unknown. The durable budget retained **$0.08020906** for them. Successful usage plus full debits is **$0.20147124**, below $1. Before restart, retained debits plus the new batch caps totaled **$0.99020906**. No reservation remains open.

| Tokens | v2 | v3 |
|---|---:|---:|
| Prompt | 204,015 | 253,487 |
| Completion, including reported reasoning | 101,241 | 82,789 |
| Reported reasoning subset | 27,229 | 26,442 |
| Cached prompt | 138,216 | 180,219 |

Completion cost was **$0.09934680**, about 82% of successful spend; prompt cost was $0.02191538. Longer indexed prompts were offset by shorter completions and caching. This run does not isolate their causal contributions.

Prioritize deterministic fixes, caching unchanged sources, and avoiding repeated whole-document calls. Retain the prefilter while testing recall. Shorten repetitive output only after preserving customer facts and evidence. Evaluate targeted repair or selective escalation after measuring a corrected baseline; changing models now would obscure code and contract defects.

This run does not price downstream entity resolution, parcel matching, project deduplication, briefs, production retries or infrastructure.

## Changes and verification

The diagnostic provider error identified unsupported uniqueItems in the strict schema. This evaluation removed that provider-schema keyword while retaining local duplicate-ID rejection. It also fixed HTTP error-body capture so an exception's attached response is preserved. Unsupported strict-schema constraints are consistent with the supported subset in [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

No semantic prompt, relevance, decision or publication-gate changes were made during the compatible batches. Both frozen release identities match each other and the current workspace's model, prompt, source hashes, fixtures and settings.

Fresh checks: **119 tests passed** across strict-schema harness, proceeding claims, source passages and evaluation protocol. Narrow tracked-file whitespace checks passed. Artifact checks confirm 40 unique sources, complete review coverage, source equivalence with v2, ledger reconciliation, no open reservations, matching identities and exact surviving evidence offsets.

**Keep release blocked.** Fix the four groups, replay frozen outputs to distinguish validator improvements from model mistakes, then run a newly selected capped sample with independent adjudication of high-risk decisions and relevance. Acceptance must include zero unsupported completed approvals, no footer-generated projects, reliable citation coverage and agreed recall/relevance on named leads. Schema validity or a high gate percentage cannot substitute for customer accuracy.

## Artifacts

- [Machine-readable results](municipal-llm-v3-results-2026-09-04.json)
- [All 40 source-review notes](../../output/municipal-v3-evaluation-2026-09-04/semantic-review.json)
- [Original 30 responses](../../output/municipal-v3-evaluation-2026-09-04/original30-compatible/results.json)
- [Comparison 10 responses](../../output/municipal-v3-evaluation-2026-09-04/heldout10-compatible/results.json)
- [Transfer review](../../output/municipal-v3-evaluation-2026-09-04/transfer-review.md)
- [Read-only summary/reconciliation](../../output/municipal-v3-evaluation-2026-09-04/summarize.py)
- [Per-item diagnostic replay](../../output/municipal-v3-evaluation-2026-09-04/inspect_outputs.py)

The output directory retains source snapshots, request/response transcripts, manifests, protocol identities, logs and spending ledgers. Real municipal evaluation data remains separate from synthetic test data.
