# Municipal PDF extraction research

Updated September 6, 2026. This research evaluates PDF preparation and source
interpretation within Pass 0. It does not qualify a production backfill. The
existing discovery design is in [pass0-discovery.md](pass0-discovery.md).

## Current conclusion

**Follow-up:** The subsequent [text/image/native-PDF comparison](pass0-pdf-modalities.md)
demonstrates that direct PDF input is viable on the four-document sample. It
recovers an OCR-damaged detail, while all three input methods retain all required
subjects under a new common output contract. That comparison supersedes any
inference below that local text/OCR preparation is necessary. It does not qualify
unattended extraction or resolve the earlier ambiguous-source failures.

The evidence does not support replacing the reader with one universally better
parser or adding an unconditional second LLM call. Native text, OCR, meeting
boundaries and case attribution are distinct problems. Preserve their evidence
and measure them independently.

The baseline supported by the experiments in this report is native text extraction where available, OCR for
scanned pages, and discovery records that retain their original source passages.
The fixed four-municipality trial below yields a source-backed packet for 17 of
18 required subjects in each repeat, but only 11 per repeat need no identified
core action/date or discovery-category correction. This supports reviewed
discovery; it does not qualify unattended structured intelligence or prove a
human time saving. Do not add another global interpretation pass: the tested
second reader still fails source attribution.

DOCX is an optional source adapter where a municipality publishes it. It is not
the general solution: the actual Fairview, Shrewsbury, York, Fawn, West Manchester
and Penn documents collected here are PDFs. No inference about county-wide DOCX
availability follows from Dillsburg's recent publications.

## Fixed utility evaluation across municipalities

The existing discovery prompt, schema and Luna low-effort settings were frozen
before dispatch. Four complete PDFs from four municipalities were each run twice:
Fawn January 2025, West Manchester January 2026, Penn Planning May 2026 and the
five-page Dillsburg January 2023 scan. Eighteen required subjects and their core
expectations were recorded from the sources before viewing model responses.
Three inputs use native text; Dillsburg uses the existing Docling/RapidOCR output.
No reference answer was supplied to inference and no prompt was tuned on results.

| Measure | Repeat 1 | Repeat 2 |
| --- | ---: | ---: |
| Required subjects | 18 | 18 |
| Accepted records with supporting source passages | 17 | 17 |
| Core records needing no identified correction | 11 | 11 |
| Accepted records needing a core correction | 6 | 6 |
| Rejected source selection, retained as a flagged candidate | 1 | 0 |
| Silently omitted subjects | 0 | 1 |
| Additional optional records | 1 | 1 |
| Additional records outside the fixed scope | 2 | 3 |
| Provider cost | $0.01428563 | $0.01130278 |

The denominator is the same eighteen source-reviewed subjects in both repeats.
The correction count includes incorrect action/date fields and discovery
classifications, even when the accompanying source excerpt is correct. It does
not penalize omission of deferred conditions or milestones. These are explicit
model-assisted judgments on a small selected sample, not independent human gold
or a population accuracy estimate. The 17/18 packet count is not an accuracy score.

Useful results include the following, in both repeats:

- Fawn: Smucker's 138 Gamble Road plan was tabled; the Craig land addition carries
  no building rights; the DiBastiani agreement still awaits Township signatures.
- Penn: Water Street Four concerns 118 homes and a preliminary recommendation;
  9 Industrial Drive proposes a 5,000-square-foot building plus outdoor storage
  and received no action; Breezewood Phase 1 concerns 46 building lots, with a
  conditional favorable recommendation rather than governing-body approval.
- West Manchester: Wexcon received approval of a $59,878.69 payment application;
  HRG was authorized to develop a conservation-area master plan for $8,500 plus
  deliverables. Neither becomes a new construction approval in the output.

The failures are concrete and separable:

- West Manchester's first BAE record has a nonliteral excerpt endpoint. It is
  rejected and retained only as a source-selection candidate. The second run
  produces an accepted record after an existing deterministic endpoint repair.
  This is a validation loss, not failure to discover the subject.
- Both runs wrongly label acceptance of each York Garber project's
  decommissioning security as `security_release`. Correct quotations do not fix
  that machine-readable claim. The two projects remain separate despite sharing
  1750 Taxville Road.
- Both Penn runs label 540 Westminster `subdivision_only` although its excerpt
  explicitly describes three proposed residential building lots. Its recommendation
  and proposal remain correctly preserved, but the relevance classification needs
  correction before downstream filtering.
- Both Dillsburg runs keep the two tax properties separate and preserve approval
  for 2023 only. They nevertheless use the covered tax year as a decision date and
  misclassify the action as a property transaction or a land-use/procedural waiver.
  The second run also labels the $15.61 tax refund a property transaction.
- The Bickel property meeting notice is present in the first Dillsburg output, but
  its subdivision/plan classification is unsupported. The second output silently
  omits the notice. The source text is readable in both inputs.

There are nine record-level action/date corrections and three discovery-category
corrections across the two repeats. The source-backed packets still make their
supporting text available. They are suitable for inspection, not automatic
promotion. Extra road-closure, snow-emergency and broad tax-administration records
are source-grounded but outside this evaluation's precommitted scope; they are
not hallucinated events. The Lions sign agreement is optional in both runs.

Penn's packets retain nearly entire case sections. That is useful indexing and
evidence preservation, but it does not demonstrate reduced reading time. No
human review-time experiment was performed. One attempted Monaghan download
returned HTTP 404 and is recorded as a collection failure, not an empty meeting.
Penn's thirty-page annual compilation is a separate segmentation challenge and
was not substituted into this monthly-document evaluation.

## Matched native-PDF experiment

The original Fairview 2015-11-04, Shrewsbury 2011-09-14 and York 2025-04-14 PDFs
reproduce the stored native text byte for byte. Every nonempty numbered source
unit maps back to measured page coordinates. The geometry variant adds page,
indentation, vertical position, gap and bold-character fraction; source words,
line numbers, locator prompt, schema, model and settings remain fixed.

Twelve Luna low-effort calls cover three sources, two conditions and two repeats.
Their total provider cost is **$0.01879164**, below the frozen $0.226039384 ceiling.

| Measure across both repeats | Plain numbered text | Text plus geometry |
| --- | ---: | ---: |
| Required topic mentions | 50/50 | 50/50 |
| Topics represented separately | 46/50 | 48/50 |
| Unsupported extra records under the review scope | 10 | 7 |
| Provider cost | $0.00713466 | $0.01165698 |

This small coverage difference is inconsistent. Both plain-text runs and one
geometry run merge 40 and 44 East Tolna Road. Every Fairview output attaches
unlabeled lines 113–185 to Willis Road Estates. One geometry run also supplies
the enforcement motion as evidence for other compliant properties and a removed
wall. The locator emits no decisions, so that last finding is overbroad evidence,
not a demonstrated false decision. All seven York cases remain separate.

Visual inspection of Fairview physical pages 4 and 6 confirms large blank gaps,
a restarted unlabeled list and a duplicated fragment in the original PDF. Their
presence is not an OCR error. A gap alone does not prove another case's identity.

## Additional interpretation pass

A separate eight-call experiment reads the frozen plain-text inventory and the
complete source, with and without geometry. Its alternative contract separates
subjects from observations, permits shared observations, and provides an explicit
unresolved-attribution state with no subject target. It can split, reject and add
inventory candidates. References are excluded from inference.

This is **an additional LLM interpretation call within Pass 0**, after inventory.
It is not parcel/entity resolution or cross-document case linking. The added calls
cost **$0.02409552**, excluding the preceding inventory.

The reader separates all fourteen Shrewsbury subjects in three of four runs, but
records the shared enforcement action for both intended targets in only two.
Two runs omit that action for 133 South Main. None applies enforcement to the
compliant properties or the removed wall. All four Fairview runs fail to identify
the required unresolved attachment. One output excludes the ambiguous lines from
its citations while importing their details into the Willis summary.

Successful citation lookup and an available uncertainty field therefore do not
establish correct attribution. Do not promote this reader based on these results.

## Scanned PDFs and broader source formats

The newly collected Dillsburg January 2023 minutes contain five raster-only pages.
All five pages were visually reviewed against two local outputs:

| Reader | Observed elapsed time | Findings |
| --- | ---: | --- |
| Existing Docling/RapidOCR preparation | 19.38 seconds | Preserves key property mentions, refund ID/amount, both property addresses and requested/granted tax periods; corrupts a room-use sentence and a trash-rate continuation. |
| Direct RapidOCR on 1600-pixel page renders | 8.73 seconds | Preserves the property mentions and granted period; reads the two passages above, but corrupts two police-report lines and the requested tax-exoneration duration. |

Rendering and segmentation differ, so these are diagnostic timings, not a
controlled speed benchmark. Both return text for every page despite localized
loss. Direct OCR confidence is low for the three corrupted passages in this
sample; that is a candidate routing signal, not a qualified universal threshold.

The October 2024 Dillsburg download is byte-identical to the existing scanned
fixture and is not counted as new evidence. The July 2026 DOCX demonstrates
native paragraph access only; no general DOCX ingestion implementation was added.

Additional collected PDFs include Fawn January 2025 (two native pages), West
Manchester January 2026 (six native pages), and Penn's 2025 Planning Commission
compilation (thirty native pages). The first two subsequently entered the fixed
utility trial above, alongside a separate five-page Penn May 2026 PDF.
Penn's compilation contains eleven distinct meeting headers and dates. Its
physical page 4 starts February's minutes while the printed
page number restarts at 1, confirmed visually. A PDF cannot always be treated as
one meeting. Candidate boundaries are saved; automatic splitting is not yet
implemented or validated. See the official [Penn compilation](https://penntwp.com/wp-content/uploads/2026/04/Planning_Minutes_2025.pdf).

## What current research contributes

Docling exposes page and document conversion-confidence grades, including layout,
OCR and native parsing signals. Those measure conversion quality rather than
municipal case attribution; its documented table score remains unimplemented.
These signals merit testing for selective page repair. See [Docling confidence](https://docling-project.github.io/docling/concepts/confidence_scores/).

Marker can return a hierarchy of blocks with polygons and offers selective OCR
repair; MinerU offers native-text, OCR and hybrid conversion paths. These are
reasonable parser candidates for a future matched corpus trial, not established
winners for these minutes. See [Marker](https://github.com/datalab-to/marker) and
[MinerU](https://github.com/opendatalab/MinerU).

A study of Portuguese administrative PDFs found that splitting and metadata
choices mattered substantially to downstream question answering. A separate
scanned-financial-document study found benefits from separating page retrieval
and multimodal reasoning. Neither result establishes exhaustive municipal-topic
recall or correct motion attribution. Use them to motivate comparisons rather
than transfer headline accuracy figures. See [administrative-document study](https://arxiv.org/abs/2604.04948)
and [scanned-document study](https://arxiv.org/abs/2604.26462).

## Recommended direction and remaining qualification

Use source-preserving discovery as the research baseline. Native-text conversion
is sufficient to expose the useful passages in these native PDFs; switching
parsers cannot repair an LLM's incorrect action label when the source text is
already correct. Keep OCR quality checks and meeting-boundary detection in
document preparation. Preserve the failed-selection queue separately from
accepted facts. Avoid using unreviewed action and relevance labels to silently
discard subjects or drive downstream assertions.

The fixed trial establishes some useful output across municipalities, but the
decision about deployment still requires a measured review workflow. Compare
reading original minutes with reviewing extracted records on fresh sources,
including finding silent omissions. If correcting and checking output approaches
the work of reading the minutes, the intended time-saving value is unproven.
Further technical qualification should target the identified failure classes:

1. Compare selective re-reading of damaged OCR regions on genuine scans from
   additional municipalities, preserving original images, boxes and alternative
   readings. Evaluate case identifiers, addresses, negation, amounts and dates.
2. Test meeting segmentation on compiled PDFs while preserving physical pages,
   printed labels, document versions and source offsets. Do not merge recurring
   applications across meetings during document preparation.
3. Test attribution independently of a fallible prior inventory and retain
   ambiguous source fragments. Measure silent errors as well as model-reported
   uncertainty before making selective interpretation automatic.

PDF preparation is a local parsing/OCR stage. Subject discovery is an inference
stage. Detailed interpretation or a targeted visual revisit adds another inference
call when used. Cross-document entity/case linking stays downstream. A language
or runtime rewrite is not supported by the current failure evidence.

## Evidence, cost and limits

Evidence lives under `output/pass0-redesign-2026-09-06/`: `pdf-diagnostic-v100`,
`pdf-geometry-v101`, `pdf-attribution-v102`, `pdf-reader-v103` and `utility-v104`.
Frozen inputs, requests, responses, provenance and source-reviewed findings are retained.
The paired experiments use model-assisted development references, two repeats
and no independent human gold. The scan audit is one new document. None of these
results estimates population accuracy.

The user explicitly added $2 for PDF research to the existing $6 ledger. The new
twenty-eight calls cost **$0.06847557**, including **$0.02558841** for the fixed
utility trial. Cumulative known spend is $4.969856404696; the three older
reservations still total $1.079594964. The $8 cap has
$1.950548631304 uncommitted. No uncertain reservation was released or retried.

The eight new helpers pass Ruff lint and formatting; all three model-result audits
replay source-range receipts successfully, including the fixed trial's explicit
rejection. All eight utility requests completed and settled; the runner reports
`completed_with_errors` because one generated record failed citation validation.
No maintained pipeline implementation was changed in this research cycle, so
the prior 1,609-test cleanup result was not
rerun. Successful structural checks do not override the semantic failures above.
