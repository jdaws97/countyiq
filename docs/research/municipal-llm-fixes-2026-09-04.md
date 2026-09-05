# Municipal extraction corrections — September 4, 2026

Implementation and isolated verification are complete. The user subsequently
approved the migration and evaluations; both are now complete. See the
[revised evaluation results](municipal-llm-v2-results-2026-09-04.md): $0.14069727 spent,
no publication, and backfill remains unapproved. The execution plan below records
the original approval boundary and is retained as history.

## Customer changes

- Each consequential extraction field has independently checkable, contiguous source
  passages. Storage, explicit inference resolution and the event renderer retain those
  passages; joining unrelated quotes no longer satisfies the evidence contract.
- Scheduled matters, recommendations, decisions and updates have separate states.
  A recommendation cannot become an approval. Actual event dates, containing meeting
  dates and future deadlines are separate, with missing dates shown as unverified.
- Generic next-case footers and submission calendars are rejected as case evidence.
  The prompt distinguishes development, minor property matters, land-use policy and
  public works, and includes substantive capital projects and bidding. Liquor-license
  transfers alone are outside this development pass.
- One shared SQL resolver handles explicit parcel IDs and unique numbered addresses
  inside the source municipality. Street-only references, intersections, ranges and
  duplicate addresses remain unresolved. Multiple source-printed IDs are supported.
  Feed generation, parcel context, signals, validation and county narrative context
  use this resolver.
- Project histories use source application identifiers and source-named plans.
  Persistent aliases preserve established keys when a display title changes.
  Conflicting identities abstain from automatic merging. A shared parcel or company
  name alone cannot combine unrelated applications.
- Event cards expose stage, category and unresolved location. The project-directory
  API accepts a category filter. Records without a supported project identity can
  remain events without becoming a watchable project.

These deterministic checks do not establish that model prose accurately entails
all source facts. Exact quotes can still be misinterpreted. Conservative identity
matching can split related matters when explicit source identifiers differ; that
requires review rather than fuzzy automatic merging.

## Cost and release controls

The same model and single extraction pass remain in use. Project grouping,
chronology, browsing and watch matching need no additional model calls. Pass 0's
default output cap is aligned to the existing evaluation cap of 8,192 tokens.
The evaluation input-price ceiling includes the cache-write tier observed in the
baseline. Neither adjustment is a claim of measured savings.

Quality approval now binds the new contract, prompt/schema, persistence source,
migration and frozen pilot regressions. No new approval receipt was issued.
The unchanged [baseline](municipal-llm-pilot-results-2026-09-04.md) cost $0.06920453;
no revised model calls were made during this implementation.

## Verification

| Check | Actual result |
| --- | --- |
| Pipeline non-integration suite | 1,032 passed; 91 deselected |
| API unit suite | 110 passed |
| API integration suite | 92 passed |
| Dedicated attribution and persistence integration tests | 13 passed |
| Final focused contract / release checks | 20 passed |
| TypeScript build check and ESLint | Passed |
| Dagster Definitions.validate_loadable | Passed |
| git diff --check | Passed |
| Firefox desktop and 390px mobile event-card checks | No console errors or horizontal overflow |

The attribution tests cover the native and explicit-resolution writers and the
persisted event date. Migration 061 was exercised against countyiq_test only.
Test records remain in the dedicated test database or browser-only fixtures.
Browser verification used localhost:5175 (redirecting to app.localhost:5175) and
the isolated API at localhost:8002. The mock browser session is now closed.
These results do not establish that the normal real-data API at localhost:8000
has the new schema or that production has been deployed.

Logs: output/municipal-fixes-2026-09-04/.
Browser artifacts: output/playwright/municipal-v2-desktop.png and
output/playwright/municipal-v2-mobile.png. Those images are layout checks using
clearly synthetic data, not reviewed model output.

## Exact remaining execution scope

1. Upgrade the local real countyiq database at localhost:5433 through revision 061,
   including pending additive predecessors 059/060. Revision 061 adds extraction
   details, project aliases and the shared matching function. It does not rewrite
   source documents or publish extractions. Deploy matching code with the schema.
2. Rerun the original [30-document manifest](municipal-source-pilot-2026-09-04.json)
   with the revised contract, capped at $1.
3. Run the [10-document held-out manifest](municipal-heldout-pilot-2026-09-04.json),
   capped at $1. It excludes the original IDs and uses a deterministic sample of
   five planning/zoning and five other municipal bodies. Only metadata and source
   hashes have been prepared; its raw text has not been copied or sent.
4. Both evaluations read the public municipal meeting texts from the local database
   and send them, with the extraction prompt, to OpenRouter using
   openai/gpt-5.6-luna. The prior pilot reported OpenAI as provider; record and inspect
   the actual provider for each new response. Archive full requests/responses locally.
   Combined spend must stay within $2, with no semantic retries and no publication.
5. Review every returned matter against its source. Compare the original failures,
   unsupported decisions/dates/property links, consequential omissions, minor-case
   noise, stable project groups, prefilter misses and cost per accepted useful matter.
   Passing schema/quote validation alone cannot approve the run. Any material invented
   project, decision, deadline or wrong parcel blocks release. Report residual identity
   splits and incomplete coverage explicitly before recommending a bounded backfill.

Reviewable commands after that approval, from pipelines/, with DATABASE_URL set
privately to the approved local database:

    .venv/bin/alembic upgrade 061
    .venv/bin/python -m eval.municipal_pilot --manifest ../docs/research/municipal-source-pilot-2026-09-04.json --output-dir ../output/municipal-pilot-v2-2026-09-04 --max-cost-usd 1 --run
    .venv/bin/python -m eval.municipal_pilot --manifest ../docs/research/municipal-heldout-pilot-2026-09-04.json --output-dir ../output/municipal-heldout-v2-2026-09-04 --max-cost-usd 1 --run

Automatic approval review rejected the non-test schema mutation and transfer/copy
of municipal source text because it requires explicit approval of the database,
payload and destination. These actions were not retried through an alternate path.
