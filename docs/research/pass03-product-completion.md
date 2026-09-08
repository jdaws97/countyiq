# Municipal intelligence: implementation and product review

September 7, 2026. Implements the work identified in
[the gap review](pass03-intelligence-gap-review.md). Results describe the working
tree and local review database, not a production deployment.

## Product judgment

The records approach now completes a useful investigation loop: find a municipal
passage, open the matched property, verify the original document, and watch the
property or its existing owner. Connecting those steps adds more product value
than generating more prose from disconnected inputs.

It supports source-backed leads and monitoring within its observed coverage. It
is not an exhaustive development inventory. Empty views explicitly do not mean
nothing happened; the product shows how many known records were actually checked.

## Implemented behavior

- Accepted municipal selections now produce property associations,
  `municipal_record` signals, feed events and private watch notifications.
  Explicit PIDNs and unique full street addresses must match the municipality.
  Matching handles wrapped addresses and a missing separator before a spelled-out
  direction. Quoted text is unchanged. Ambiguous addresses, ranges and unit
  references remain at municipality level.
- Agenda proposals remain proposals. A mention does not become an approval,
  completed project, inferred owner relationship or active-plan flag. Municipal
  mentions contribute zero opportunity, momentum and site-screening points.
- Live views retract stale sources and associations when text, metadata,
  permissions or the property match changes. Events with outdated owner links
  also disappear. Identical rereads and rebuilds do not duplicate notifications.
- Property summaries include municipal passages alongside available constraints.
  Property and municipality pages show reviewed, awaiting-read, source-review,
  unavailable and future-record counts, reading failures and source/review dates.
  Counts cover the municipality's known records, not only the current property.
  The property header now says “Latest evidence observed.”
- Pass 1 prioritizes acquisition-active organization groups and watched owners,
  including purchases under abbreviated names within an organization candidate
  group. Whole groups proceed to existing identity verification. Private account
  and watch details never enter model prompts.
- Source units separate inline bullets and vote endings without changing bytes.
  Binding retains governing budget years and narrowly recognized adjacent acronym
  headings. The reader policy includes commercial hearings, expected openings,
  financing and identified utility procurement stages.
- Dagster reading and deterministic refresh jobs include the downstream
  projections. Migration `068` supplies the association index and live views;
  `067` remains the immutable evidence-history prerequisite.

## Reviewed examples

| Example | Outcome and value |
| --- | --- |
| Hanover Community Church, 1959 Smith Station Road | Final-plan consideration and completed DEP stormwater revisions reach PIDN `30000DE0017L0`, its summary and the feed. The original agenda opens at page 2. No final approval is inferred. |
| Restaurant at 2861 East Prospect Road | Recovered the hearing request and recommended September 8, 2026, 6 pm time. Literal `2861east` matches uniquely to PIDN `54000JJ0083A0`. The proposed date remains a proposal. |
| Spring Grove YMCA | Recovered the expected August 3 opening with the YMCA heading, identifying who “they” are. No parcel or completed opening is guessed. |
| Loganville road work | The $230,000 Westridge/Ferndale estimate and related future work retain “Budget Planning for 2027.” They are not presented as funded current work. |
| Jacobus dense minutes | Different property violations no longer inherit neighboring inline bullets. The inspection-service vote retains “unanimously” without attaching that word to the next property inquiry. |
| Newberry flowmeter relocation | Retains the valve-pit order and relocation purpose. An order already placed is not an open bid. This source remains withheld pending metadata review. |

Two diagnosed reader misses remain: West Manchester fairgrounds refinancing and
Hopewell's Armstrong temporary staging arrangement. Both sources also need
metadata review and are not presently served. Some selections remain weak leads;
damaged OCR remains damaged. These limitations are recorded in the acceptance
artifact rather than hidden behind earlier extraction scores.

## Owner-priority result

Production selectors on 6,151 candidate groups now select 402 groups, up from 318.
All **76 previously deferred organization groups with recent-sale signals** now
qualify for verification, including the D.R. Horton example from the diagnosis.
This restores verification coverage; it does not establish identity merges.

There are 178 groups eligible for the registration-only path. After existing
context bounds, the estimate includes 222 paid groups. Source-hash reuse,
conservative identity decisions and adaptive voting remain in force.

## Validation

- Final reader delivery: **50 documents, 342 cards**, all spans bound to source
  bytes. Ten negative-control documents produced no cards. Seven targeted
  stage/context checks passed. This is a targeted product/regression review,
  not a recomputation of the older 94.2%/97.2% topic-coverage claims.
- Five requests changed after source-boundary refinement and were retested.
  Forty-five identical requests were reused only after checking identical source
  hashes and bound responses. Prompts never contained evaluation labels. The final
  YMCA context extension required no additional inference.
- **1,673 pipeline tests passed**, with 124 integration tests deselected; all 18
  Dagster jobs resolved. **129 API unit tests and 148 API integration tests
  passed**. Integration includes **27 municipal workflow cases** covering associations, unchanged scores,
  private property/owner watches, repeat reads, retractions, ambiguity, units,
  wrapped addresses, coverage and obsolete watch matches after projection rebuilds.
- Frontend typecheck, lint and production build passed. The existing large-map
  chunk advisory remains. Desktop/mobile browser checks passed source expansion,
  PDF-page access, feed-to-property navigation, coverage wording and guest-watch
  creation/removal, with no horizontal overflow or console errors observed.
  Private notifications were tested through authenticated API integration tests.
- Migration `068` was applied locally and tested on an isolated database. Four
  reviewed examples were loaded through immutable decisions, including explicit
  resolution of the changed church selection. Source-review holds were preserved.
  Deterministic associations, signals, events and momentum were refreshed.

This is agent product review, not a human pilot. Whether customers find leads
timely, verify them efficiently and return after the next update needs real usage
evidence. Guest watches remain browser-local until sign-in.

## Cost and operating boundary

The revised records backfill estimate is **$5.55**: $4.57 for 3,504 eligible
municipal documents and $0.98 for prioritized owner verification. The documented
maximum-output/retry reservation is $45.07, not expected spending. Cumulative
budget limits can stop a run before completion. Paid Passes 2/3 remain optional.

Additional model testing for this implementation cost **$0.0521**. Total spending
on the original shared $5 test ledger is **$0.7736**. The hypothetical backfill was
not launched, paid schedules remain disabled, and production was not deployed.
The local inventory still has 6,459 proceedings, including the 2,948-record
metadata-review backlog identified in the diagnosis.

## Artifacts and reproduction

Artifacts are in `output/pass03-product-completion/`: `delivery.json`,
`product-evaluation.json`, `quality-receipt.json`, `quality-release-check.json`,
`identity-priority.json`, `records-estimate.json`, `local-import.json`, test logs
and `ui-acceptance.md`. Screenshots are
`output/playwright/product-completion-*.png`. The quality receipt binds the final
Pass 0 model, prompt, code and evaluation artifact.

From `pipelines/`, using the configured database environment:

```bash
COUNTYIQ_PASS0_MODE=evidence PYTHONPATH=. .venv/bin/python \
  scripts/estimate_llm_backfill.py --profile records --sample-size 300 \
  --output ../output/pass03-product-completion/records-estimate.json
```

`proceedings_extraction_refresh` includes reading, linking, signals, events and
momentum. `deterministic_enrichment_refresh` rebuilds approved evidence without
provider calls. Paid runs still require their current quality receipt and a
cumulative budget. Metadata review is a coverage queue, not a reason to bypass
the source gate.
