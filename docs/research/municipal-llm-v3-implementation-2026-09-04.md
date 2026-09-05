# Municipal LLM priorities — implementation and verification

Implemented September 4, 2026. This is an implementation report, not approval of model quality or a backfill.

## Customer-facing changes

- A decision carries its scope and authority. Bond releases, contract awards and naming votes cannot present as generic development approvals. Withdrawals and removals have their own states. Project summaries compare decisions within scope and authority.
- Hearing, decision-deadline, bid-advertising, bid-opening, construction-start and completion milestones remain separate. Dates are derived from the cited source wording. Ambiguous years and reported source-date conflicts remain unresolved.
- Project conditions and milestones open their assigned evidence receipt, including when the event card starts collapsed. Internal contract versions, passage IDs and source hashes stay out of the customer display.
- Default discovery suppresses minor, unknown-scope and context-only matters, bond/naming/procedural actions, and explicit withdrawals/removals. The feed exposes a matter-scope filter, and explicit property/project/entity history retains these records. Municipal radar signals obey the same discovery eligibility.
- Generic descriptions, streets alone and suspicious or conflicting identifiers do not establish project identity. Existing conflicting aliases require review instead of silently merging projects.

## Extraction and cost changes

Production Pass 0 and both evaluation entry points now use the same source-bound cited-claim contract. The model selects numbered passages. The server constructs exact quotations, field-to-receipt assignments and normalized dates. Unknown, missing, duplicated or wrong-source passage IDs fail validation; a literal identity cannot be fabricated by joining disjoint passages.

Raw model claims and their hydrated projection remain available for audit. Existing v2 fixtures and paid responses are unchanged. Native persistence and explicit contradiction-resolution projection preserve the new metadata. The new JSON Schema validator is an explicit runtime dependency.

All 40 archived evaluation sources were indexed without truncation; the largest is 26,887 characters. No model calls were made. Passage membership does not prove semantic entailment, and conservative identity rules may reduce project recall.

Cost reduction is not yet demonstrated. Copied quotes, redundant field lists and model-generated ISO dates are removed from generated output, but the static system prompt increased from 14,064 to 16,766 characters. Passage wrappers also add input overhead. Measure total provider-reported cost per correctly extracted matter, including failures and retries, before claiming savings.

## Database and verification

The dedicated countyiq_test database was migrated through revision 064. Revision 063, added by concurrent work, permits the scoped/procedural event types; revision 064 also permits source-backed updates. Neither migration rewrites existing events. A downgrade refuses incompatible rows rather than silently relabeling them. No real-data migration or publication was performed by this implementation work.

Fresh checks:

| Check | Result |
| --- | --- |
| Pipeline non-integration suite | 1,142 passed |
| API unit suite | 116 passed |
| API contracts, directories, scoped visibility, source policy and entity identity | 37 passed |
| Proceeding attribution/persistence integration suite | 15 passed |
| Final focused event-type, persistence and narrative-context database checks | 9 passed |
| TypeScript build check and ESLint | Passed |
| Dagster definitions validation | Passed |
| Git whitespace check | Passed |
| Browser: scoped status, separate milestones, exact receipt navigation and matter filter | Passed at desktop and mobile sizes |

The broader schema/attribution run had 43 passes and one failure in the existing source-governance seed-count audit. The API fixture leaves test_township_planning_commission in the shared test database, producing 105 conditional policies where the clean migration registry expects 104; it also remaps Hanover into the fixture jurisdiction. This is test-fixture isolation, not a scoped-event persistence failure. The new event types and both projection paths passed independently. The real database was not used for synthetic tests.

Browser verification used http://app.localhost:5175 with explicitly labeled, session-only synthetic responses. Underlying API database behavior was tested separately against countyiq_test. No synthetic browser responses were inserted into real records.

## Release position

Ready for a small capped validation evaluation; bulk backfill remains gated. No current Pass 0 quality receipt was issued.

Evaluate the original 30 documents and the 10 held-out documents against the existing criteria: source-supported matters, correct stage and scope, exact recovered quotations, property identity, product relevance, distinct-matter recall, duplicate-project risk, prefilter false negatives and actual provider cost. Empty output is format-valid but does not count as successful recall. Review every serious false approval, wrong identity, wrong deadline and missed substantive project before release.

The synthetic fixture proves plumbing and deterministic guardrails, not model accuracy. Require a fresh model/prompt/source-bound quality review before publishing any extraction or starting a bulk backfill.

## Artifacts

- [Offline indexing and current release identity](../../output/municipal-v3-implementation/offline-source-readiness.json)
- [Verification logs and live plan](../../output/municipal-v3-implementation/plan.md)
- [Desktop feed](../../output/playwright/municipal-v3-feed-desktop.png)
- [Mobile project page](../../output/playwright/municipal-v3-project-mobile.png)
- [Frozen synthetic contract fixture](../../pipelines/eval/fixtures/p0_claims_contract.json)
