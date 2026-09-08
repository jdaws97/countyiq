# Municipal PDF input comparison

The [hard-document follow-up](pass0-hard-pdf-canary.md) tests the same reader
on the earlier 71-topic cohort. It finds 67 topics, 65 separately, with persistent
attribution/action errors; the eighteen-topic success below does not generalize.

September 6, 2026. Follow-up to [PDF extraction research](pass0-pdf-extraction.md).

## Result

Sending the PDF directly works on this sample and removes the need for our own
text extraction before the inference call. All three input methods found all
eighteen required subjects separately in both repeats. Native PDF and rendered
images recovered a detail damaged by OCR, but neither improved required-subject
recall over the text baseline. Images alone offered no measured overall advantage.

Native PDF input is therefore a viable, simpler candidate for Pass 0. This is
not a finding that vision solves arbitrary municipal minutes: the trial covers
four previously reviewed documents, including one scan, and does not include the
ambiguous Fairview attachment or the thirty-page Penn meeting compilation.

## Controlled comparison

- Four complete PDFs: Fawn January 6, 2025 (2 pages), West Manchester January 22,
  2026 (6 pages), Penn Planning May 7, 2026 (5 pages), and Dillsburg January 10,
  2023 (5 scanned pages).
- Same model and provider: `openai/gpt-5.6-luna`, OpenAI endpoint, low reasoning,
  8,192 maximum output tokens, no provider fallback and no retries.
- Three inputs: page-separated native/OCR text; every page rendered as a PNG at
  1,600 pixels on the longest side with high image detail; original PDF bytes
  through OpenRouter's explicitly selected `native` PDF engine.
- Two repeats, with input-method order reversed in the second repeat: 24 calls.
- A common prompt and compact schema in every condition: identity, location,
  activity, current state, ordinary-language actions, and physical-page quotes.
  There is no prior inventory. The eighteen-topic source reference is excluded
  from all inference requests.

The native PDF requests contain the original file and shared meeting metadata,
with no locally extracted source text. Image requests contain all rendered pages
and page labels, with no OCR text. PDF requests returned from OpenAI without
parsed-file annotations. The request configuration and response checks establish
the native route; internal provider rendering and tokenization remain opaque.
OpenAI documents PDF processing as supplying text and page images to compatible
models. See [OpenAI file inputs](https://developers.openai.com/api/docs/guides/file-inputs)
and [OpenRouter PDF routing](https://openrouter.ai/docs/guides/overview/multimodal/pdfs).

For the scan's text condition, existing direct RapidOCR output supplies physical
page boundaries. Its source rasters are byte-identical to the image condition.
The earlier utility trial used Docling's combined text. This trial reruns its own
text baseline; it is not an unchanged rerun of the previous schema or OCR output.

## Findings

Counts below combine two repeats of the same eighteen required subjects. They
are not counts of thirty-six independent cases or population accuracy estimates.

| Measure | Text | Page images | Native PDF |
| --- | ---: | ---: | ---: |
| Calls completed | 8 | 8 | 8 |
| Required subjects found separately | 36/36 | 36/36 | 36/36 |
| Identified material proposal/action errors in required records | 0 | 0 | 0 |
| Required records with an identified name error | 0 | 1 | 0 |
| Required records with quotation/page issues | 3 | 10 | 6 |
| Additional optional records | 2 | 2 | 2 |
| Additional records outside the fixed scope | 6 | 5 | 6 |
| Actual provider cost | $0.01965447 | $0.02750373 | $0.02433393 |

Every response's identity, activity, current state and action fields were reviewed
against the complete source and frozen reference. No required property was merged
or silently omitted. The review is model-assisted, not independent human gold.
Zero identified core action errors does not establish full-record perfection;
secondary details and naming/evidence limitations remain.

Concrete findings:

- Both visual conditions recovered the scan's **five-year requested tax period**,
  which was corrupted in direct OCR. The text condition omitted that request
  duration; all methods correctly preserved approval for **2023 only**. One text
  repeat explicitly marked page 4 unreadable while retaining the main facts.
- All methods retained the Bickel property meeting notice, both individual tax
  properties, and the refund identifier and amount.
- All methods distinguished the Penn Planning Commission recommendations from
  governing-body approvals, and preserved no action on the storage proposal.
  Phase 1's 46 lots remained distinct from the overall development's 180 lots.
- All methods preserved West Manchester's security acceptance, contractor
  payment, conditional final plan approval and authorization to prepare a master
  plan. None recast security acceptance as release in the required records.
- One image output shortened **DiBastiani** to **DiBastian** in its label and
  identifier while quoting the correct name. Its address and agreement state
  remained correct.

Quotation issues are counted separately from incorrect underlying facts. Examples
include the correct 118-home sentence cited to Penn page 2 instead of page 1;
a West Manchester sentence spanning two pages but assigned to one; punctuation
changes; paraphrases labeled as quotations; and ellipses inserted into quotations.
A native-PDF quotation absent from OCR was visually verified on the original scan
and excluded from the error count. Failed matching against OCR is not by itself
proof that the model's quote is wrong.

The extra records include recreation-door expenditure, community-room rental
discussion and an emergency road closure. These are source-grounded but outside
the frozen required scope. The Lions sign agreement is optional. One PDF output
also includes an unnamed facility-tour record. Errors in extra records include
misdating the temporal relationship of the road-closure ratification. Several
outputs also describe Form B as the plan type although the source only says the
form was signed. Those limitations are retained in the detailed audit rather than
hidden by the core-required-record metric.

## Interpretation

The evidence supports trying **one native-PDF discovery call** as a replacement
for locally extracted text input. A separate visual reread would be an additional
Pass 0 call; this experiment does not require that two-stage design.

The native PDF route costs about 2.4 cents for these eight calls, versus 2.0 cents
for text and 2.8 cents for images. Caching differs by repeat, and local parsing,
rendering and human review are excluded. These are observed costs, not universal
per-document rates or a controlled latency benchmark.

The improvement over the older structured utility trial cannot be attributed to
vision: the new text-only condition also performs well. This experiment changes
the output contract for all conditions, removing the earlier fine-grained action
and relevance categories and replacing line-anchor selection with page quotations.
It establishes a modality comparison under that contract, not which contract
change caused the improvement.

Before promotion, validate the native-PDF approach on fresh municipalities and
harder scans, ambiguous case boundaries and compiled meetings. Retain the PDF and
page evidence, and verify quotes before treating them as exact citations. This
trial does not measure human time savings or establish unattended reliability.

## Reproduction and cost

Evidence is in `output/pass0-redesign-2026-09-06/pdf-modalities-v105/`: frozen
reference, sources, page images, PDFs, endpoint metadata, protocol, all 24 requests
and responses, and `review-v2.json`. The preparation/runner and audit are adjacent
`pdf_modalities_v105.py` and `audit_modalities_v105.py`.

The audit verifies file hashes, rebuilds every request, validates every response,
checks the PDF route and source mappings, and reproduces the quotation diagnostics
and aggregate results. The initial audit and `review.json` are retained; version 2
fixes JSON integer-key normalization in the replay comparison without changing
results or judgments. Both helpers pass Ruff lint and formatting; the audit
replays successfully. No maintained pipeline implementation changed.

All 24 calls settled for **$0.07149213**, within the conservative $1.87232256
reservation estimate. The shared $8 ledger now records **$5.041348534696** known
spend and **$1.079594964** in three older unresolved reservations, leaving
**$1.879056501304** uncommitted. None of those older reservations was retried or
released.
