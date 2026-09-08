# CountyIQ test and code simplification review — September 8, 2026

CountyIQ has concrete duplication worth removing, but the evidence does not support deleting half the tests. The biggest opportunities are duplicated CI execution, repeated test setup, small tests that divide one contract across many assertions, obsolete UI components, and production functions that combine too many responsibilities. Simplification should reduce the number of places a maintainer must understand and change.

This is a read-only review of application and test code. This report is the only artifact added by the review. Existing staged, unstaged, and untracked work was preserved. Files changed concurrently during the review: pipeline collection grew from 1,877 to 1,909 cases. Counts and line references describe the inspected working tree, not a frozen commit or production deployment.

**Scope and evidence**

Inventoried pipeline, API, frontend, evaluation, script, migration, documentation, and CI files. Read the relevant implementations, callers, assertions, and fixtures behind the findings below. Used Python AST scans for exact function-body clones, test definitions, and large functions; checked unused Python names with Ruff; collected pytest cases; ran the local non-integration suites. This is a repository-wide inventory with targeted semantic review, not a claim that every line or database migration was exhaustively audited.

| Area | Latest observed collected cases | Test files | Approximate test source lines |
| --- | ---: | ---: | ---: |
| Pipelines, including integration | 1,909 | 119 | 25,941 |
| API unit | 129 | 22 | 2,747 |
| API database contracts | 175 | 20 | 4,014 |
| Frontend | 43 | 9 | 983 |
| Total | 2,256 | 170 | 33,685 |

Test-source lines exclude Python conftest files; API conftest alone adds 1,044 lines. Inventories and collection were taken at different moments in the changing worktree. Parameterized cases account for 773 pipeline cases and 129 API cases; these are executions, not separate test functions. Combining functions into parameterized tables often reduces source code without reducing executions.

The runtime inventory is approximately 39,276 lines of pipeline Python, 9,515 lines of API Python, and 15,161 lines of frontend TypeScript/TSX. Separately, evaluation Python adds 8,110 lines, pipeline scripts 2,663, and 70 Alembic files 8,627. Size alone does not establish redundancy.

**Observed verification**

| Check | Result |
| --- | --- |
| Pipeline non-integration suite | **1,752 passed, 1 failed, 126 deselected; 21.05 seconds** |
| API unit suite | **129 passed; 0.53 seconds** |
| Frontend `npm test` | **43 passed; approximately 0.91 seconds** |
| Later pipeline collection, all markers | **1,909 collected**; later additions were not included in the executed baseline |
| API collection | **304 collected**, including 175 database cases; collection did not execute database fixtures |
| Ruff F401/F811/F841 scan of `api` and `pipelines` | **11 diagnostics**: 9 unused imports, 1 unused local, 1 repeated import |

Commands used the project virtual environments. The frontend run used the installed Node 22.14.0 runtime, which was absent from the initial shell PATH. No database integration, deployment, paid inference, real-browser journey, coverage, or mutation-testing run was performed. Runtime savings below are opportunities, not before/after measurements.

**1. Consolidate the duplicate API contract workflow — high confidence, first priority**

[ci.yml:82](/home/jdaws/countyiq/.github/workflows/ci.yml:82) provisions and runs `api/tests` in its database integration job. [api-contract-tests.yml:3](/home/jdaws/countyiq/.github/workflows/api-contract-tests.yml:3) runs the same suite again for pull requests changing API or pipeline paths, including another installation of both Python environments.

Keep the main CI database job and remove the duplicate workflow after checking whether its check name is required by branch protection. Update the testing documentation to describe the single owner. This removes one whole duplicate API contract execution on qualifying PRs without removing any test coverage. Preserve the separate pipeline database instance: the main workflow explicitly separates it because API fixture mutations would contaminate pipeline seed-state contracts.

**2. Fix the existing failing test by consolidating its contract — high confidence**

[test_pass2_review_fixes.py:239](/home/jdaws/countyiq/pipelines/tests/test_pass2_review_fixes.py:239) expects `pass2_signal_validation.py` as a dictionary key. [quality_release.py:149](/home/jdaws/countyiq/pipelines/countyiq/lib/quality_release.py:149) includes that file but intentionally records repository-relative paths to prevent same-basename collisions.

Move this requirement into the parameterized source-change test at [test_quality_release.py:54](/home/jdaws/countyiq/pipelines/tests/test_quality_release.py:54): add the shared Pass 2 question module and prove that changing its bytes invalidates the receipt. Then remove the obsolete membership-only test. The surviving behavior is stronger than merely changing the expected string. Do not revert the production identity fix to satisfy this assertion.

**3. Condense formatter micro-tests — high confidence, substantial test-source reduction**

[test_intelligence_common.py:36](/home/jdaws/countyiq/pipelines/tests/test_intelligence_common.py:36) repeatedly separates output shape, exact keys, individual field values, and empty-list behavior for simple projections. For example, tax-claim formatting has distinct tests at lines 149, 152, 158, and 162 for those pieces of one contract. Similar patterns recur for parcel, entity, portfolio, proceedings, neighbors, and corporate context.

Use one explicit exact-output assertion for each populated formatter example, with named parameter rows for meaningful missing/null/date cases. Exact dictionary equality can replace both the key-set assertion and the individual field assertions; the existing individual assertions alone do not forbid extra keys. Retain relationship decoding, normalization differences, ordering where promised, and multi-record preservation. Avoid a generic test generator that hides the expected output.

Planning estimate: roughly **180–230 lines** and **15–20 separately maintained test definitions** can be consolidated in this file. Some scenarios should remain as parameter rows, so the collected-case count need not fall by the same amount.

**4. Shrink tests of standard hashing mechanics — high confidence**

[test_intelligence_common.py:531](/home/jdaws/countyiq/pipelines/tests/test_intelligence_common.py:531) has seven tests for a two-statement canonical-JSON/SHA-256 wrapper: hex length, determinism, differing inputs, key order, empty input, date serialization, and manual SHA-256 equivalence.

Retain a reproducible known-output example, key-order invariance, and representative serialization/input-sensitivity cases. Fold empty/date inputs into those cases. Length and hex-character checks add little once an exact digest is asserted. Keep source-hash invalidation, evidence changes, and volatile-field exclusion tests elsewhere: those exercise CountyIQ behavior, not SHA-256 itself. Estimated reduction: **20–30 lines**, with approximately three or four maintained tests replacing seven.

**5. Remove selected SQL-text replicas only where execution proves the same contract — high confidence for the named query**

| Candidate | Surviving evidence / required qualification |
| --- | --- |
| [test_intelligence_common.py:24](/home/jdaws/countyiq/pipelines/tests/test_intelligence_common.py:24), municipality-scoped proceeding query text | [test_schema_integration.py:1275](/home/jdaws/countyiq/pipelines/tests/test_schema_integration.py:1275) executes the exact `PROCEEDINGS_FOR_PARCEL_QUERY` and checks matching versus excluded parcels. Keep this database test and remove the five-line textual replica. |
| [test_development_signal_stability.py:20](/home/jdaws/countyiq/pipelines/tests/test_development_signal_stability.py:20), two SQL substrings | Consolidate with the adjacent normalizer assertion and the shared-function checks in [test_development_momentum_v6.py:72](/home/jdaws/countyiq/pipelines/tests/test_development_momentum_v6.py:72). The actual signal query executes in [test_proceeding_attribution_integration.py:95](/home/jdaws/countyiq/pipelines/tests/test_proceeding_attribution_integration.py:95), but its structured-ID scenario alone is not proof of every address-scoping regression. Keep one narrow guard until wrong-municipality behavior is covered at this call site. |
| Literal inventories in [test_development_momentum_v6.py:72](/home/jdaws/countyiq/pipelines/tests/test_development_momentum_v6.py:72) | Remove only assertions whose business behavior is already exercised. Preserve unique rules and performance constraints; string presence cannot establish correct spatial results or index use. |

Do not blanket-delete source inspection. [test_network_authorization.py](/home/jdaws/countyiq/pipelines/tests/test_network_authorization.py) checks a broad ingestion boundary, while [test_architecture_boundaries.py:16](/home/jdaws/countyiq/pipelines/tests/test_architecture_boundaries.py:16) enforces forbidden package imports. Those are legitimate structural contracts until a better oracle replaces them.

**6. Consolidate deployment text assertions with script execution — medium confidence**

[test_architecture_boundaries.py:180](/home/jdaws/countyiq/pipelines/tests/test_architecture_boundaries.py:180) checks restore-script variable names and source ordering. [test_restore_safety.py:11](/home/jdaws/countyiq/pipelines/tests/test_restore_safety.py:11) tests target validation, and [test_restore_drill_script.py:18](/home/jdaws/countyiq/pipelines/tests/test_restore_drill_script.py:18) executes the real script with isolated fake external commands across four outcomes, asserting cleanup ownership.

Move remaining unique guarantees, including validator invocation and forbidden destructive behavior, into the execution fixture before deleting text assertions. Similarly, [test_deploy_recovery.py:76](/home/jdaws/countyiq/pipelines/tests/test_deploy_recovery.py:76) can own backup/migration/start ordering instead of duplicating literal checks at [test_architecture_boundaries.py:88](/home/jdaws/countyiq/pipelines/tests/test_architecture_boundaries.py:88). Existing failure-path tests do not automatically prove the successful sequence. Keep backup integrity and recovery guarantees.

**7. Give model configuration one test owner — high confidence**

[test_intelligence_metadata.py:268](/home/jdaws/countyiq/pipelines/tests/test_intelligence_metadata.py:268) reasserts the Pass 2 default model and effort already covered by [test_strict_schema_harness.py:228](/home/jdaws/countyiq/pipelines/tests/test_strict_schema_harness.py:228) and [test_reasoning_effort_wiring.py:102](/home/jdaws/countyiq/pipelines/tests/test_reasoning_effort_wiring.py:102). Keep a single configuration matrix covering defaults, precedence, invalid values, and values reaching the harness. Remove the duplicate default assertion, not the wiring/precedence behavior. Replace historical model-selection essays in tests with a short reference to the owning decision.

**8. Extract shared test builders; stop importing support from test modules — high confidence**

`append_explanation` is an exact 43-line function-body clone in [test_source_explanations.py:20](/home/jdaws/countyiq/api/tests/test_source_explanations.py:20) and [test_property_explanation_serving.py:12](/home/jdaws/countyiq/api/tests/test_property_explanation_serving.py:12). Move it to a narrowly scoped support module.

API municipal tests import fixtures and builders through other test modules; see [test_source_explanations.py:11](/home/jdaws/countyiq/api/tests/test_source_explanations.py:11) and [test_municipal_evidence_workflow.py:21](/home/jdaws/countyiq/api/tests/test_municipal_evidence_workflow.py:21). Pipeline tests do the same with `consent_fixture`, `simple`, and `payload`; see [test_pass0_experiment.py:20](/home/jdaws/countyiq/pipelines/tests/test_pass0_experiment.py:20) and [test_proceeding_item_review.py:5](/home/jdaws/countyiq/pipelines/tests/test_proceeding_item_review.py:5).

Use feature-specific builders under test support and pytest fixtures in the appropriate conftest scope. Preserve the different end-to-end scenarios. This reduces coupling and setup duplication without deleting useful evidence-validity tests.

The 1,044-line [API conftest](/home/jdaws/countyiq/api/tests/conftest.py) mixes database bootstrapping, role provisioning, broad seed data, and accepted-inference setup. First move fixture construction into named feature builders while preserving its lifecycle. Changing isolation or reseeding frequency is a separate behavioral change; transaction rollback cannot simply replace committed fixtures read through separate API connections.

**9. Share frontend test compilation setup — high confidence**

Most frontend test files repeat temporary-directory creation, TypeScript transpilation, import rewriting, dynamic import, and cleanup. Compare [customer-evidence.test.mjs:9](/home/jdaws/countyiq/frontend/tests/customer-evidence.test.mjs:9), [record-dates.test.mjs:9](/home/jdaws/countyiq/frontend/tests/record-dates.test.mjs:9), and [investigation.test.mjs:9](/home/jdaws/countyiq/frontend/tests/investigation.test.mjs:9).

A small test-support loader using the existing TypeScript compiler can remove approximately **80–120 lines** across the suite. Preserve fresh module instances for watch-sync tests and package resolution for [map-viewport.test.mjs:10](/home/jdaws/countyiq/frontend/tests/map-viewport.test.mjs:10), which deliberately compiles under the frontend directory. This does not require a new testing framework. These tests execute library behavior; they do not substitute for browser journey coverage.

**10. Remove real waiting from readiness tests — measured high-value runtime opportunity**

The eight parameterized cases in [test_public_readiness.py:14](/home/jdaws/countyiq/pipelines/tests/test_public_readiness.py:14) consumed approximately **16.13 of the 21.05 seconds** in the pipeline run. The persistent 503 case took 10.55 seconds and transient 530 recovery took 2.52 seconds. The test exercises production retry sleeps plus local HTTP-server shutdown latency.

Keep real HTTP/script execution and request-count assertions. Override only the shell sleep in the test subprocess, and use a shorter server polling interval. Preserve one focused contract for retry counts and requested delay values; do not change production retry policy merely to accelerate tests. This is a much more defensible speed target than deleting hundreds of fast parser cases.

**11. Remove superseded frontend components — high confidence**

[Nav.tsx:25](/home/jdaws/countyiq/frontend/src/components/Nav.tsx:25), [SearchBar.tsx:4](/home/jdaws/countyiq/frontend/src/components/SearchBar.tsx:4), and [ActivityPreview.tsx:8](/home/jdaws/countyiq/frontend/src/components/ActivityPreview.tsx:8) have no component imports or JSX callers under `frontend/src`. Together they contain **259 lines**. The application uses [WorkspaceShell.tsx:136](/home/jdaws/countyiq/frontend/src/components/WorkspaceShell.tsx:136), including its own search/navigation implementation. Removing the dead components also removes two redundant search-submit implementations.

Do not delete `ActivityPreview.css` wholesale: despite its name, it supplies live `upcoming-dates`, `activity-scope-note`, and `feed-record-search` styling. Relocate those rules to their actual owners, then remove only unused selectors/imports. Similarly, verify selectors in the shared theme before deleting old navigation styles.

[PageShell.tsx:5](/home/jdaws/countyiq/frontend/src/components/PageShell.tsx:5) simply forwards layout props to WorkspaceShell with the same default width. Removing the alias is optional and low value compared with deleting unreachable components; avoid broad call-site churn solely to eliminate 21 lines.

**12. Make the map summary a focused read — high confidence**

[parcels.py:504](/home/jdaws/countyiq/api/routes/parcels.py:504) invokes `_parcel_report(include_soils=False)` and returns six fields. It skips soil coverage, but still reads and assembles discarded zoning, parcel-brief, cross-signal, linked-proceeding, and municipal-evidence content. The map calls this endpoint at [MapView.tsx:603](/home/jdaws/countyiq/frontend/src/pages/MapView.tsx:603).

Separate shared parcel facts from full-report enrichment; let the summary request only its six fields. Keep the current snapshot, permissions, source freshness, and explanation semantics. Source explanations are included in the summary and must remain. Verify summary/detail agreement and the map selection journey; measure query work before claiming a latency improvement.

**13. Reuse request lifecycle code selectively — high confidence for Ops, medium for pagination**

[OpsHealth.tsx:44](/home/jdaws/countyiq/frontend/src/pages/OpsHealth.tsx:44) hand-rolls loading/error/data and fetch handling despite [useFetchJson.ts:19](/home/jdaws/countyiq/frontend/src/lib/useFetchJson.ts:19) already implementing cancellation and stale-response protection. Migrate this straightforward case first while retaining useful error feedback.

[CountyFeed.tsx:135](/home/jdaws/countyiq/frontend/src/pages/CountyFeed.tsx:135) and [DevelopmentRadar.tsx:213](/home/jdaws/countyiq/frontend/src/pages/DevelopmentRadar.tsx:213) repeat pagination generations, cancellation, reset, and append logic. A narrow shared pagination hook is plausible, but keep URL construction, metadata, and result identity local. Verify rapid filter changes and load-more races in a browser. Avoid replacing these with a broad homegrown query framework.

**14. Consolidate the repeated ArcGIS mechanism — high confidence, bounded refactor**

[ag_security.py:147](/home/jdaws/countyiq/pipelines/countyiq/assets/arcgis/ag_security.py:147), [conservation_easements.py:142](/home/jdaws/countyiq/pipelines/countyiq/assets/arcgis/conservation_easements.py:142), and [ecodev_candidates.py:160](/home/jdaws/countyiq/pipelines/countyiq/assets/arcgis/ecodev_candidates.py:160) contain identical geometry-lookup bodies. The first two assets also repeat authorization, fetch, archive, SCD2 write, and metadata assembly.

Extract the shared geometry mechanism first. There is already a small helper approach in [site_readiness.py:25](/home/jdaws/countyiq/pipelines/countyiq/assets/arcgis/site_readiness.py:25). Preserve source-specific keys, URL policy, empty-result handling, and asset registration. Do not turn distinct parsers into a configurable ingestion framework, and do not reactivate paused assets as a side effect. Verify SCD2 behavior and definitions loading for any subsequent asset refactor.

**15. Separate experiments and historical replay from the current validator — high confidence about callers; retirement is conditional**

The inspected non-test callers of `pass0_facts`, `pass0_locator`, and `pass0_packet_facts` are evaluation/discovery code, notably [pass0_experiment.py:22](/home/jdaws/countyiq/pipelines/eval/pass0_experiment.py:22). They currently live in `countyiq/lib` alongside the active production implementation. Keep useful experiments and their tests, but give them an explicit experimental package and documented promotion/retirement status. Moving them reduces production navigation burden; it does not itself reduce executable code or justify excluding their tests from CI.

The `legacy_evaluation=True` branch in [proceeding_claims.py:182](/home/jdaws/countyiq/pipelines/countyiq/lib/proceeding_claims.py:182) has no repository caller outside [test_proceeding_item_review.py:176](/home/jdaws/countyiq/pipelines/tests/test_proceeding_item_review.py:176). It spreads schema selection and conditional validation across a 447-line function and its caller. Retire it if historical replay is no longer required; otherwise isolate it behind a replay adapter. The separate `narrative_evaluation` option does have an evaluator caller, so it cannot be grouped into a blanket dead-code deletion.

Do not mistake [pass2_signal_validation.py](/home/jdaws/countyiq/pipelines/countyiq/lib/pass2_signal_validation.py) for a dead per-signal engine: the batched parser actively imports and calls its parser. Its old A/B description in the batched module is misleading documentation, not evidence the implementation is unused.

**16. Decide whether the unserved Pass 4 feature deserves continued maintenance — conditional, potentially substantial**

[parcels.py:711](/home/jdaws/countyiq/api/routes/parcels.py:711) deliberately sets `related_narratives = []` because the feature lacks the required serving freshness contract. Yet the repository maintains an approximately 887-line narrative asset, 710-line narrative library, 518-line test file with 50 collected cases, a registered manual job, and frontend rendering for these narratives.

If there is no near-term customer requirement, retire the runtime job/UI path and archive the implementation as an experiment. If the feature remains planned, retain it with an explicit owner and completion criterion. This is product-scope reduction, not redundant-test removal. Preserve persisted history and migration compatibility; do not drop tables or historical migrations as cleanup.

**17. Break large functions at actual responsibility boundaries — medium confidence, not a file-size quota**

| Function | Observed span | Useful boundary |
| --- | ---: | --- |
| [public_proceedings_scrape](/home/jdaws/countyiq/pipelines/countyiq/assets/scrapers/public_proceedings.py:442) | 712 lines | Listing acquisition, document handling, persistence/reporting; retain per-origin authorization before network calls. |
| [entity_verification](/home/jdaws/countyiq/pipelines/countyiq/assets/enrichment/entity_verification.py:141) | 610 lines | Candidate preparation, validated trial collection, accepted-result persistence. Preserve voting and transaction semantics. |
| [signal_validation_batched](/home/jdaws/countyiq/pipelines/countyiq/assets/enrichment/signal_validation_batched.py:308) | 555 lines | Work preparation versus validation execution versus projection. Preserve budget and concurrency boundaries. |
| [_parcel_report](/home/jdaws/countyiq/api/routes/parcels.py:524) | 664 lines | Shared facts, report-only reads, response assembly; start with the summary endpoint finding. |

Keep each refactor local and driven by a specific maintenance problem. A generic pass runner, repository layer, or inheritance hierarchy could add more indirection than it removes. Large prompt constants, signal catalogs, and source configuration are not inherently defects.

**18. Remove small unused residue and replace narration with intent — high confidence, low priority**

The focused Ruff scan found only 11 unused/repeated-name diagnostics, including unused extraction-template imports, urgency constants, and `policies_by_key` at [audit_municipal_sources.py:263](/home/jdaws/countyiq/pipelines/scripts/audit_municipal_sources.py:263). Inspect import side effects and the unused assignment's right-hand side before removal. CI currently formats Python but does not run this lint selection.

Recurring low-value prose includes comments restating a function signature, `Args`/`Returns` blocks for tiny obvious helpers, and historical model-selection narration in tests. Preserve explanations of why a source gate, transaction, normalization, or retry exists. Remove prose that merely translates the next statement into English. These are maintainability observations; code inspection cannot establish whether a human or AI authored them.

**Recommended execution order and acceptance**

1. Establish a frozen baseline for cleanup. Consolidate the stale receipt assertion, duplicate CI run, exact fixture clone, formatter/hash tests, and frontend test loader. Run the affected suites; maintain a named surviving assertion for each deleted behavior. Expect roughly **300–500 lines of test-source reduction** from the evidenced opportunities, not a guaranteed reduction of hundreds of cases.
2. Remove the three unreachable components and relocate live CSS correctly. Run frontend typecheck, lint, build, tests, and verify affected navigation/feed/date presentation in a real browser. The 259 component lines are a separate source reduction from test consolidation.
3. Remove readiness-test delays, then implement focused summary reads and the straightforward Ops fetch cleanup. Compare runtime/query work and preserve endpoint behavior.
4. Refactor ArcGIS repetition and one oversized function at a time. Keep tests focused on observable source, identity, projection, and failure outcomes rather than the new helper layout.
5. Make explicit decisions on Pass 4 and experimental/replay variants. Only those decisions justify larger feature and test deletions.

Do not set a target such as “under 1,000 tests.” Track duplicate setup removed, files that must change for one feature, deterministic runtime, and whether a realistic regression still fails a surviving test. Keep parser edge cases, alphanumeric PIDN attribution, source revocation, stale-evidence rejection, budget enforcement, append-only history, restore safety, and workspace account/race isolation. Repeated coverage at a pure-function and an integration boundary may be intentional because each catches a different class of failure.

The desired maintenance rule is straightforward: one obvious owner for each contract, shared setup where it is actually shared, few supported runtime modes, and no new abstraction without concrete repeated callers.
