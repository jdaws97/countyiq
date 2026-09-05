# Research Artifacts

These files preserve source discovery, rights evidence, and product-risk
analysis. They inform source selection and configuration, but CountyIQ does
not load them into PostgreSQL, send them wholesale to an LLM, or treat them as
customer-facing product data.

| Artifact | Role |
|---|---|
| [Municipal source cleanup, 2026-09-04](municipal-source-cleanup-2026-09-04.md) | Applied local source quarantine, metadata repair, evidence preservation, and pilot readiness |
| [Cleanup audit data](municipal-source-cleanup-2026-09-04.json) | Source identity comparisons, replacement listing checks, corpus counts, and verification |
| [Prepared extraction pilot](municipal-source-pilot-2026-09-04.json) | 30 real documents; prepared only, no paid calls |
| `york-pa-public-data-landscape-2026-08-27.md` | Current human-readable source and commercial-use assessment |
| `york-pa-dataset-register-2026-08-27.csv` | Machine-readable evidence register supporting that assessment |
| `york-pa-municipal-board-source-survey-2026-04-09.json` | Historical Playwright survey of planning-commission and zoning-hearing-board pages; useful for coverage gaps and source maintenance |
| `york-pa-municipal-proceedings-review-2026-08-27.md` | Current 72-municipality coverage, reachability audit, gaps, legal disposition, and implemented enforcement |
| `york-pa-municipal-source-static-audit-2026-08-27.json` | Reproducible row-level policy, robots, HTTP, browser, origin, and collectable-document evidence; no page/document bodies retained |
| `source-governance-completion-audit-2026-08-27.md` | Requirement-by-requirement implementation status, product boundary, and external launch gates |
| `pass2-rubric-review-2026-09-03.md` | Case-by-case review of the 20-case Pass 2 stability subset, the three generator rules it corrected, and the AI-reviewer disclosure behind the first-run receipt |
| `pass2-rubric-review-2026-09-04.md` | Current-evidence Pass 2 corpus audit, 20-case release review, corrected rubric/prompt contract, and minimal-spend validation |

Runtime source configuration belongs in
`pipelines/countyiq/lib/county_config.py`. When research changes an ingestion
decision, update that configuration or the active decision log explicitly;
placing another file here does not change application behavior.

- [2026-09-04 comprehensive production-readiness review](production-readiness-review-2026-09-04.md): customer value, UI/UX, infrastructure, verified fixes, tests and launch gates.
- [Municipal LLM v3 implementation](municipal-llm-v3-implementation-2026-09-04.md): cited claims, decision scope, separate milestones, conservative discovery and verified release limits.
