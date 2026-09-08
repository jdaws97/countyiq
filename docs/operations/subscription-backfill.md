# Subscription-authored record backfill

The operator can use a signed-in Codex CLI to produce actual Pass 0 source
selections and Pass 3 explanations. This consumes the ChatGPT subscription's
Codex allowance. It makes no OpenRouter or separately billed OpenAI API calls,
does not redeem reset credits, and stops if the subscription cannot continue.
The CLI supports saved authentication and structured output in
[non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).

This workflow runs on the operator machine. It does not install account login
credentials on the VPS. Each model task receives bounded source inputs in a
temporary read-only workspace, with shell tools disabled and application/API
credentials removed from its environment. Responses are source data, never
commands. The ordinary source binding, reference attribution, explanation
validation, and contradiction gate decide what can be retained.

## Local batch

From `pipelines/`, with the intended database connection environment:

```bash
DATABASE_PORT=5433 .venv/bin/python scripts/subscription_backfill.py read \
  --directory ../output/subscription-backfill \
  --limit 16 --batch-size 8

DATABASE_PORT=5433 .venv/bin/python scripts/subscription_backfill.py municipal \
  --directory ../output/subscription-backfill \
  --limit 32 --batch-size 8

DATABASE_PORT=5433 .venv/bin/python scripts/subscription_backfill.py property \
  --directory ../output/subscription-backfill \
  --limit 16 --batch-size 8
```

`--ids` pins proceeding IDs, `--subjects` pins municipal explanation keys, and
`--pidns` pins properties. Without selectors, the read stage covers every
currently eligible proceeding; municipal explanations cover all current cards;
property explanations use the existing ranked and municipal-linked property
limits. Each stage requires an explicit positive work-item limit. Batches keep
whole sources together and bound combined input size. Property contexts are
prepared incrementally.

`--workers 1` is the default. Operators may select up to four concurrent authoring
batches per stage. Database writes and source-freshness checks remain sequential;
each worker keeps separate receipts and caches its finished batch on early exit.
This changes throughput, not the selected model or source-validation contract.

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
checkout or a commit that differs from the deployed Dagster image. It obtains
the existing pipeline database credentials into process memory, opens a
temporary loopback SSH tunnel to the private database container, and runs the
same local authoring script. It closes the tunnel when the batch ends.

```bash
.venv/bin/python scripts/subscription_backfill_remote.py \
  --ssh-target ubuntu@YOUR_HOST \
  --identity-file /absolute/path/to/ssh-key -- \
  read --directory /absolute/path/to/subscription-artifacts --limit 16
```

Reuse the same artifact directory for identical previously authored local
sources. The production database validates its own current source records;
never restore the local application database over an existing production
database to transfer these outputs.

After reads, rebuild `municipal_evidence_linking`, then finish municipal and
property explanations and the ordinary deterministic serving projections.
Verify full unfiltered coverage and resolve every in-scope error, stale source,
or contradiction before customer access. Keep the app private during backfill.
The record-product scope does not silently authorize a separate county-wide
legacy owner-alias or signal-voting backfill, nor any paid API expansion.

## Deployment operations

`docker/install-operation-units.sh` renders backup and storage-guard units for
the exact release checkout. `docker/deploy.sh` installs them after readiness,
restores the prior units on a failed release promotion, and prepares the durable
backfill state and archive directories as container UID/GID 10001. LLM archives
use `${COUNTYIQ_ARCHIVE_HOST_DIR:-/var/lib/countyiq/archives}`, independent of the
checkout. The previously active September 7 release's archive
directory and the legacy archive directory were both empty when this path was
introduced; no existing transcripts needed migration. The standard image includes
maintained scripts and evaluation fixtures. Scan OCR uses the separately locked
operator runtime described in `pipelines/ocr/README.md`; missing preparation
remains pending rather than becoming an empty read.

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
