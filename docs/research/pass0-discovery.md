# Pass 0 discovery: current design and evidence

Pass 0 should find useful municipal activity consistently, preserve its evidence,
and support selective later enrichment. Luna is the leading model from the
completed comparisons. The prototype is not yet qualified for unattended full
backfill, and no production extraction or backfill has been written.

The subsequent [municipal PDF research](pass0-pdf-extraction.md) isolates page
geometry, an additional attribution reader, scanned-page conversion and compiled
meeting documents. Those experiments do not yet establish a reliable replacement.

## Record boundaries

Extract observations about individual matters, including their source identities,
participants, requested activity and actual recorded actions. A recommendation,
procedural motion, plan approval and historical decision remain distinct. A
carried motion to deny is a denial; approving an application for funding is not
a funding award. Allegations and proposed conditions keep their qualifications.

Preserve original PDF bytes and content hashes, versioned derived text, page
offsets, selected source passages, and model/prompt/schema versions. A URL may
serve several document versions. Record collection failure separately from a
successful collection with no new documents. Physical PDF pages and printed page
labels should remain separate when a reader supplies both.

Missing information must distinguish at least:

- The field was not attempted and is deferred for enrichment.
- The source does not state a value.
- The value or its attribution is ambiguous.
- The field does not apply.

The discovery prototype explicitly marks conditions and milestones deferred.
It does not yet implement this complete missing-value model for every field.
Source-selected excerpts and original documents remain available for enrichment.

Cross-document case linking and timelines belong downstream of Pass 0. Case
numbers need jurisdiction context, and a shared property address is insufficient
to merge applications. Keep each observation's evidence so a later revision can
change a derived current status without erasing earlier events. In CountyIQ,
parcel resolution should ultimately use PIDN rather than introduce a competing
parcel identity. Significance and alert prioritization remain separate from
recorded facts.

## Maintained implementation

| Component | Responsibility |
| --- | --- |
| `countyiq/lib/pass0_documents.py` and `pipelines/ocr/` | Native PDF text and bounded isolated OCR/layout preparation, with source hashes and page offsets. Not wired into the production extraction asset yet. |
| `countyiq/lib/pass0_source.py` | Original numbered text, exact offsets and literal-source resolution. |
| `countyiq/lib/pass0_locator.py` | Independent navigation inventory. Its names and ranges are suggestions requiring interpretation. |
| `countyiq/lib/pass0_facts.py` | Full fact contract and structural/source checks, retained as the richer comparison. |
| `countyiq/lib/pass0_packet_facts.py` | Explicit inventory dispositions with full-document context and bounded fact citations. |
| `eval/pass0_discovery.py` | Lean discovery with deferred enrichment and separate source-only revisit candidates. |
| `eval/pass0_experiment.py` | Frozen requests, source/code fingerprints, bounded paid dispatch and a persistent spending ledger. |

The evaluation runner supports `discovery` (default), `locations`, `packet_facts`
and `facts`. Only Luna remains in its model selection. Preparation takes
source rows, source-only references and explicit source IDs. References are
archived for evaluation and excluded from inference requests. Inventory-based
preparation accepts one complete frozen inventory per selected source; optional
per-matter/overlap grouping controls batching while preserving full source context.

The older classifier, claim-verifier, local Qwen/NuExtract, GLiNER encoder,
field-projection and isolated-context experiment paths have been retired. Their
code and results are archived instead of maintained as compatibility modes.

## What the broader comparison establishes

Nine fully processed documents have 51 source-reviewed reference topics:

| Measure | Fuller locator plus reader | Lean document reader |
| --- | ---: | ---: |
| Calls | 70 | 9 |
| Actual provider cost | $0.39026335 | $0.03117379 |
| Topics mentioned in raw output | 50 | 50 |
| Topics mentioned after structural validation | 49 after local status fix | 45 |

These are topic mentions, not correct-record accuracy. The fuller reader merges
two properties; the lean reader combines seven compliance/enforcement subjects
into one record. Only 38 of 51 topics are separately represented and structurally
retained by the lean reader. A Willis record also attaches facts from a
questionable neighboring source section without flagging the ambiguity.

Across all twelve lean documents, 64 of 71 reference topics appear in raw output;
57 have separate records. After citation validation, 58 topics remain mentioned
and 51 separately represented. All twelve calls together cost $0.03918772. Ten
use an 8,192-token output ceiling and two previously undispatched short sources
use 4,096. No favorable response selection or generation retries were used.
Effort, examples, batching and schema differ between approaches, so the cost
change cannot be attributed solely to deferring conditions and milestones.

A local replay keeps six invalid excerpt selections as explicit source-only
revisit candidates. It preserves valid cited lines and original errors without
promoting rejected decisions or statuses. Broader cited lines may include other
subjects; these candidates still require interpretation. The independent locator
already names five of the seven topics wholly omitted by the lean reader, but
misses two and sometimes combines unrelated evidence. This supports further
testing of selective revisits; it does not establish a reliable automatic hybrid.

All references are model-assisted source reviews, not independent human gold.
These native-document results do not establish scanned-page quality, population
accuracy or repeatability. Successful JSON, matching quotations, model agreement
and page coverage cannot by themselves establish semantic correctness.

## Next evaluation

Retain explicit inventory and property separation while simplifying fact
interpretation. Compare the same sources, model effort and output scope, then
repeat preselected difficult documents and test fresh native/scanned examples.
Measure distinct-topic recall, identity/action errors, evidence attribution,
revisit workload, cost and latency separately. Secondary omissions are enrichment
opportunities, not an all-or-nothing completeness gate.

Prioritize revisits for unmatched inventory entries, failed citations, uncertain
case attachment and conflicting identities or outcomes. Add a small independent
source audit to measure silent misses. Assigning every page or block a category
is useful bookkeeping, but one block may contain several unresolved cases.
Detailed conditions and deadlines can be enriched when a matter becomes useful
to intelligence work. A review interface may help adjudication; building one
for every document is not a prerequisite for this Pass 0 iteration.

Selective cost is `initial cost + revisit fraction × average revisit cost`.
Using the matched nine-document means as arithmetic illustrations, a lean pass
plus fuller revisits for 10% or 25% of documents would average about $0.00780 or
$0.01430 per document. These are not measured hybrid costs: extra coverage checks,
OCR, cache changes and the actual revisit rate remain to be measured.

Use the existing object-storage, PostgreSQL and Dagster boundaries. Parser choice
remains an empirical decision; neither the proposed tool list nor a two-stage
diagram resolves attribution and omission errors automatically.

## Evidence and cleanup

Current source inputs, frozen comparisons, audits and the spending ledger remain
under `output/pass0-redesign-2026-09-06/`. The reproducible source audit is
`audit_discovery_v98.py`, with results in `discovery-review-v98/`.

Superseded experiments and both earlier chronological research reports are in
`output/pass0-archive-2026-09-06-v99/evidence-and-code.tar.gz`. Its manifest records
every archived file's hash and the hashes of discarded, downloadable model
weights. Every archived file was verified before its working copy was removed.
The archive is about 72 MB and preserves 7,926 files. The cleanup removed 314
superseded top-level experiment items, the encoder runtime project, fourteen
obsolete Python modules/tests, six stopped Pass 0 containers and their unused
llama.cpp image. Original model-download metadata is retained for reproduction.
Current PDF preparation and unrelated worktree changes are preserved.

At cleanup, known spending was $4.901380834696, with $1.079594964 reserved for
three unresolved earlier calls. Cleanup and local replay made no paid model calls.
The user subsequently added $2 for PDF research; its twenty calls bring known
spending to $4.944267994696. The older reservations remain unchanged, and the
approved $8 cap has $1.976137041304 uncommitted. See the PDF research report for
the new comparisons and their limitations.

After cleanup, the pipeline suite passes **1,609 tests**, with 124 integration
tests deselected. Retired-mode tests were removed with their implementations;
the remaining focused discovery/runner/inventory checks pass 43 cases. An offline
replay of all twelve lean documents reproduces all 65 retained records and six
source-only candidates exactly. The spending ledger is unchanged. Ruff lint and
format checks pass for the maintained Pass 0 files, and the diff whitespace check
passes. These checks validate the cleanup and local behavior, not model accuracy.
