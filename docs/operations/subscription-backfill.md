# Subscription-authored record backfill

The maintained Dagster assets can use either the normal OpenRouter backend or
the native `codex_subscription` backend, selected globally with
`COUNTYIQ_LLM_BACKEND` or per pass with `COUNTYIQ_PASS{N}_BACKEND`. Native mode
uses the ChatGPT subscription's Codex allowance, defaults to the separate
`gpt-6-astra` model setting, and stops without a paid fallback if the
subscription cannot continue. Every run still has finite per-pass item and
native call caps per asset invocation, including backfills. It requires current
quality receipts and explicit enable gates, and retains source bindings and
authorship provenance. Maintenance skips unchanged accepted sources, but its
usage depends on document arrivals and changes to complete matter bundles.

Native mode is implemented in the maintained `proceeding_extraction`,
`municipal_matter_explanations`, and `property_record_explanations` assets and
keeps LLM jobs manual. All pipeline and native authoring execution now belongs
on the operator PC. Use the PC's signed-in Codex CLI and keep its authentication
private. The new release does not install an account login or run Codex inside
a VPS container. Production source-refresh sessions force inference passes off;
the native authoring workflow below uses the wrapper's explicit script modes.

The operator can use a signed-in Codex CLI to produce actual Pass 0 source
selections and Pass 3 explanations. This local workflow consumes the ChatGPT
subscription's Codex allowance. It makes no OpenRouter or separately billed
OpenAI API calls, does not redeem reset credits, and stops if the subscription
cannot continue. The CLI supports saved authentication and structured output in
[non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).

This workflow runs on the operator machine. It does not install account login
credentials on the VPS. Each model task receives bounded source inputs in a
temporary read-only workspace, with shell tools disabled and application/API
credentials removed from its environment. Responses are source data, never
commands. The ordinary source binding, reference attribution, explanation
validation, and contradiction gate decide what can be retained.

## Local batch

For a development database, run from `pipelines/` with explicit local
`DATABASE_*` settings. The common wrapper supplies durable local state:

```bash
DATABASE_PORT=5433 .venv/bin/python scripts/run_pipeline.py \
  --local --script subscription-backfill -- read \
  --directory ../output/subscription-backfill \
  --limit 16 --batch-size 8

DATABASE_PORT=5433 .venv/bin/python scripts/run_pipeline.py \
  --local --script subscription-backfill -- municipal \
  --directory ../output/subscription-backfill \
  --limit 32 --batch-size 8

DATABASE_PORT=5433 .venv/bin/python scripts/run_pipeline.py \
  --local --script subscription-backfill -- property \
  --directory ../output/subscription-backfill \
  --limit 16 --batch-size 8
```

For customer activity, author complete municipal matter accounts after the
source selections and verified evidence links are current (schema 075):

```bash
DATABASE_PORT=5433 .venv/bin/python scripts/run_pipeline.py \
  --local --script subscription-backfill -- matter \
  --directory ../output/subscription-matters \
  --limit 16 --batch-size 2 --workers 1
```

Use `--subjects municipal-bundle:...` to pin complete candidate bundles from
`public.current_municipal_matter_sources`. A bundle is retrieval scope, not an
assertion that its records are one case. Pass 3 must partition every record exactly
once, cite each linked record, preserve local source history and abstain on sparse
or mixed subjects. Inputs above the complete-context limit fail for review.

`municipal_matter_explanations` is included in `record_intelligence_refresh` and
the full pipeline. Materialize `intelligence_events` after authoring to publish
accepted accounts. The source-hash guard withdraws stale accounts before a
rebuild. Stable record aliases prevent silently splitting or merging previously
followed matters; those changes need identity review. The older `municipal`
mode still authors individual source cards for property evidence.

`--ids` pins proceeding IDs, `--subjects` pins municipal explanation keys, and
`--pidns` pins properties. Without selectors, the read stage covers every
currently eligible proceeding; municipal explanations cover all current cards;
property explanations use the existing ranked and municipal-linked property
limits. Each stage requires an explicit positive work-item limit. Batches keep
whole sources together and bound combined input size. Property contexts are
prepared incrementally.

`--workers 1` is the default. Operators may select up to eight concurrent authoring
batches per stage. Database writes and source-freshness checks remain sequential;
each worker keeps separate receipts and caches its finished batch on early exit.
This changes throughput, not the selected model or source-validation contract.
Completed batches are consumed as they become ready, so an earlier slow response
does not leave other workers idle. A batch containing one uncached source also
runs in its worker. Source preparation and all database operations remain on the
operator thread.

`--author-timeout` bounds each native request in seconds (default 600, maximum
3600). For long complete-source batches, operators can allow more time, for
example `--author-timeout 1800`. A timeout preserves the partial CLI diagnostic
in the artifact directory and leaves the source unaccepted. The final status
includes `stop_detail` so a timeout can be distinguished from a login or usage
failure. Completed cached responses remain reusable on the next run.

Matter persistence verifies an isolated, single-record selection directly against
the current governed evidence. It checks that the record still has no case
reference, address title, or unique parcel that would place it in a broader
bundle. All other scopes retain complete candidate resolution. This avoids a
county-wide source rebuild per isolated record while retaining the source check
inside the alias transaction. The operator does not repeat that same check
before calling matter persistence.

Pinned municipal record checks also filter by the proceeding ID encoded in the
record key, while still matching the complete key and current governed source.
Unrecognized legacy key formats keep the unrestricted lookup, and an unknown or
stale requested key still fails. This avoids reading the entire county's evidence
to verify one record explanation.

Explanations include a language review for each textual source. Non-English
passages receive separate English translations; exact original spans and date
quotes remain in the stored source. Customer presenters withhold raw excerpts
until that language contract is satisfied. English source passages remain exact.
Spanish named dates are supported; ambiguous non-English numeric dates must remain
unresolved rather than being silently interpreted in US month/day order.

The accepted-history check skips current outputs. An immutable response cache
also avoids regenerating an output after interruption or during a transfer to
production. Requests, schemas, source text, responses, response hashes, and CLI
events remain in the artifact directory; keep that directory outside Git and
back it up. Database payload provenance identifies the subscription model and
artifact hashes. AI outputs and AI contradiction reviews are not labeled as
human decisions or gold-standard truth.

The script rechecks source eligibility and freshness after authoring. Changed
sources fail; conflicting selections remain quarantined. Exit status 2 means
partial coverage, including an item cap, unavailable subscription, error, or
quarantine. The status JSON records the remaining scope. A completed batch
with explicit selectors says nothing about coverage outside those selectors.
The normal paid pipeline recognizes accepted subscription outputs under the
current prompt/source contract, so changing the transport does not spend again
on unchanged work.

## Existing production database

Deploy the reviewed commit first. The remote wrapper refuses a dirty local
checkout or a commit that differs from the active release. It obtains
allowlisted pipeline settings and writer credentials into process memory,
opens a temporary loopback SSH tunnel, and runs the same local authoring script.
The VPS session holds the deployment lock and enables writer `LOGIN` only
during the command. Cleanup closes the tunnel, restores `NOLOGIN`, terminates
writer connections, and releases the lock. See
[Local pipeline commands](local-pipelines.md) for the shared state and session
contract.

```bash
.venv/bin/python scripts/run_pipeline.py \
  --ssh-target ubuntu@YOUR_HOST \
  --identity-file /absolute/path/to/ssh-key \
  --script subscription-backfill -- \
  read --directory /absolute/path/to/subscription-artifacts --limit 16
```

Reuse the same artifact directory for identical previously authored local
sources. The production database validates its own current source records;
never restore the local application database over an existing production
database to transfer these outputs.

After reads, rebuild `municipal_evidence_linking`, then finish municipal and
property explanations and the ordinary deterministic serving projections using
`run_pipeline.py --job deterministic_enrichment_refresh` with the same SSH
options. Native scripts retain their own authoring receipts; the Dagster job
publishes the corresponding run and source-health outcomes synchronously.
Verify full unfiltered coverage and resolve every in-scope error, stale source,
or contradiction before customer access. Keep the app private during backfill.
The record-product scope does not silently authorize a separate county-wide
legacy owner-alias or signal-voting backfill, nor any paid API expansion.

## Deployment operations

`docker/install-operation-units.sh` renders backup and storage-guard units for
the exact release checkout. `docker/deploy.sh` installs them after readiness,
and restores the prior units on a failed release promotion. The daily backup
contains the primary application database. The PC's run history, model archives,
backfill state, and explicitly selected authoring artifacts require separate
preservation. The local wrapper defaults to
`~/.local/state/countyiq/pipeline`; there is no pipeline container archive mount
in the new release. Scan OCR uses the separately locked operator runtime
described in `pipelines/ocr/README.md`; missing preparation remains pending
rather than becoming an empty read.

## Compare subscription models for Passes 1 and 2

Run `eval.subscription_challenger` from `pipelines/` to evaluate native models
without database writes or an API fallback. It uses the production prompts,
schemas, parsers, attribution checks and frozen scorers. For example:

```bash
.venv/bin/python -m eval.subscription_challenger --pass-number 1 \
  --model gpt-5.6-terra --effort medium --output ../output/native-pass1-terra

.venv/bin/python -m eval.subscription_challenger --pass-number 2 --expanded \
  --model gpt-5.6-sol --effort medium --output ../output/native-pass2-sol
```

Pass 1 includes eight frozen cases. Pass 2 includes ten original cases;
`--expanded` adds twenty stability cases and four municipal feature cases.
Keep the same effort and `--trial` value across models. Increment `--trial` for
an independent request rather than reusing its immutable cached response.
Reports preserve raw outputs, scores, context hashes and subscription provenance.
A malformed batch falls back to individual requests for the complete sources.

These scores are diagnostic, not automatic quality approval. Some original
labels predate current identity-abstention and missing-footprint rules. Review
the full sources, current prompt and each failed expectation before attributing
a failure to the model; preserve the original score when recording that review.
No model or prompt change should be approved from structural acceptance alone.

## Retry a joint source line

When two separately identified cases share one printed line and exhaust the
normal attribution correction, an operator may add finer selection boundaries.
Use `read --ids ... --unit-breaks PATH` with a JSON object keyed by proceeding ID.
Each value contains `source_text_sha256` and `offsets`, a list of character
positions into the exact retained source. This changes only numbered selection
units. It preserves all original text and rejects changed source hashes or any
change to the accounting exclusion policy. The model rereads the complete source;
the usual span binding, separate-case validation and contradiction gates still
apply. Keep the specification alongside the immutable request/response receipts.
Review both case-specific passages and their shared outcome before accepting
the repair. Status reports retain failed subject keys and validation errors for
explicit retries.

## Replay accepted receipts after a binding repair

`scripts/rebind_subscription_reads.py` replays the final raw response referenced
by each accepted read's provenance. It makes no model calls or source downloads.
It requires current governed eligibility, unchanged retained source text, an
unmodified receipt and the current prompt contract. A missing receipt or source
fails instead of generating a replacement. Refined selection units are currently
unsupported; their different prompt is rejected for separate review.

```bash
DATABASE_PORT=5433 .venv/bin/python scripts/run_pipeline.py \
  --local --script rebind-subscription -- \
  --ids 161 713 --directory ../output/subscription-backfill \
  --report ../output/source-binding-review.json
```

The default is read-only. Inspect the complete before/after report, then use
`--apply` to propose the changed bindings through the ordinary integrity gate.
Unchanged cards are skipped. Changed cards remain quarantined for contradiction
review; this command never resolves them or labels its mechanical work as human
adjudication. Exit status 2 reports errors or unresolved proposals.

For production, replace `--local` with the SSH connection options and use
`--script rebind-subscription --` before the same receipt-replay arguments.
The wrapper requires a clean checkout matching the active release and keeps
database credentials in process memory.

## Review an existing matter partition

Ordinary authorship still rejects splits and merges of established matter
identities. After reviewing the complete original sources and both accounts,
an operator can pass an `identity_review` packet to `persist_matters`. It must
contain `source_hash`, `expected_prior_inference_id`, `expected_aliases`,
`proposed_aliases`, `reviewer`, `rationale`, and `decision_origin`.

The packet maps every record in the current bundle. Each proposed matter retains
an identity already associated with one of its members, or uses the ordinary
key derived from its smallest record key. The packet must match the current
accepted inference and unchanged source. Records outside the bundle and project
watches block this workflow; migrating followed identities requires separate
work. The ordinary integrity gate records the proposal as quarantined and leaves
aliases unchanged.

Resolve the resulting contradiction through `resolve_contradiction`. Accepting
the challenger rechecks aliases and watches under transaction locks, then appends
the resolution and applies the reviewed aliases atomically. Accepting the prior
account preserves its aliases. Use `decision_origin="auto_resolution"` and an
explicit AI reviewer when AI performs the source review. Record-account
`discard_both` is unsupported until a serving tombstone can prevent older
accounts from reappearing. Refresh intelligence events after resolution so they
reference the newly accepted account.
