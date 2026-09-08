# Municipal case boundaries and property references

The five wrong card/property associations found in the local Dagster canary are
fixed. Replaying the final reader on 31 archived records produced 158 source-bound
cards. The original canary retains all 26 source-reviewed correct associations;
the three Conewago cross-case links and two North Codorus cross-case links are gone.

## Contract and runtime

Cards now distinguish substantive `subject_passages` from shared
`context_passages`. A substantive span cannot belong to two cards or be reused as
another card's context. Titles must come from the card's substantive evidence.
Every visible passage must be accounted for, and every stored span is checked
against the complete original source and its hash before persistence.

The reader labels literal reference occurrences as subject property, speaker
address, meeting venue, representative address, neighboring property, other or
uncertain. Only a source-bound `subject_property` reference contained in that
card's substantive passages can enter the property matcher. Shared context and
incidental addresses cannot produce links. Original surrounding source units
remain attached to each reference so omitting a unit or range suffix from a quote
cannot manufacture a unique parcel address. Existing municipality, uniqueness,
PIDN precedence and range/unit guards remain in force.

A complete response that fails attribution validation gets one correction attempt
with the original source and specific validation errors. Provider failures receive
no additional call, and a second invalid selection is never published. Each
attempt has its own transcript key. This remains bounded by the ordinary paid-pass
spend controls. Quality identity includes the new validator and migration, so old
quality receipts cannot approve this changed reader.

Migration `070` replaces reference extraction and clears the derived link index.
It preserves immutable source and inference history. Pre-contract cards remain
visible as municipal evidence but require a reviewed new read before property
links return. The migration was applied to the local database and tested against
the dedicated test database; it has not been deployed to production.

## Real-source verification

- Conewago source 8078 retains all six substantive matters. Only the Miller
  subdivision carries 95 Butter Road; Carvana, the street adoption and Freedom
  Square carry none of Miller's property evidence.
- North Codorus source 8268 retains the separate Landing Opportunities and
  Eichelberger cases, each with its own addresses and the shared July 16, 7 p.m.
  hearing context. Both correct existing parcel matches survive. The additional
  Fire Hall Road reference remains source evidence without forcing an unmatched
  address to a parcel.
- Lower Windsor source 10299 keeps the speaker's Snyder Corner Road address out
  of the Barshinger Road discussion's property links, while retaining both genuine
  enforcement-site matches.
- Lower Chanceford source 9657 no longer treats an unexplained participant's name
  and address as a property case.
- Repeated address mentions, wrapped parcel identifiers and terminal street
  abbreviation periods were exercised without broadening identity matching.
  A five-digit street address cannot be mistaken for a normalized parcel ID.

The final evaluation used Luna low with the same request payloads as the runtime,
OpenAI-only routing, strict schema and 128,000 output-token capacity. It covered
the original 25 records, the earlier speaker-address case, and five unused records
from the frozen 50-document canary. There were 33 calls: 29 first-attempt successes
and two successful bounded corrections. All exact request hashes, source bindings,
routing and returned costs were verified. Across these 31 sources, the local
matcher produced 34 card/property pairs; the 25 repaired canary sources account
for 26 of them. The multiset of original correct proceeding/PIDN associations is
unchanged after excluding the five previously source-reviewed wrong pairs.

Earlier fix iterations remain archived, including two failed source bindings and
an incorrectly classified unexplained participant address that had no parcel
match. They are not counted as successful final results. The final evaluation
cost $0.03481934; all fix evaluations together cost $0.10181831. The original $5
ledger now accounts for $3.40208580, with no outstanding reservations.

## Local repair and validation

The 25 original canary reads were restored through `persist_evidence` and explicit,
audited contradiction resolutions after primary assistant source review. Reviews
are labeled as AI review, with no claim of independent human gold. This produces
25 current canary reads with 103 cards and two completed empty reads. The other six
evaluation documents were not published. Seven older local reads remain municipal
only until reviewed under the new contract.

The unchanged source loop then checked the same 25 actual database records:
25 unchanged, zero processed, zero errors, zero quarantines and zero model calls.
This check used a provider factory that fails on any call; it was not a new
paid-mode Dagster quality approval.

The ordinary `proceedings_extraction_refresh` Dagster job completed successfully
with paid passes disabled (run `4625fbae-5a8a-4b3e-93ef-37a6c85bb0ab`). It rebuilt
the 26 property associations, municipal signals, events, watches and momentum.
The served 103 cards and their links exactly match the reviewed replay outputs.
Final integrity checks show zero unresolved contradictions and zero projection
mismatches. The owned daemon stopped after completion.

Validation: 1,751 non-integration pipeline tests and 61 API tests pass (126
pipeline integration tests deselected), including
real saved failure fixtures, positive reference retention, source provenance,
shared context and bounded correction. The municipal workflow tests also cover
property/feed/owner/private-watch propagation, current-source retraction, role
exclusions, legacy cards, malformed references, units and wrapped identifiers.
Dagster definitions load successfully, changed Python files pass formatting, and
the new validator/reader/migration tests pass their focused lint check.

## Limits and receipts

The boundary validator proves span ownership and literal provenance. Semantic
reference roles remain a model judgment. This targeted repair does not establish
perfect recall or editorial quality: optional section headings, generic items and
routine maintenance selection still vary, and the holdout includes overbroad budget
framing. No new unrestricted quality approval, paid schedule, full backfill or
production deployment was enabled.

Reproducible artifacts are in `output/municipal-subject-fix-2026-09-08/`:
`audit.json`, `reference-audit.json`, `positive-recall.json`, `evaluation-v3/`,
`repair-receipts.json`, `unchanged-source-loop.json`, `serving-verification.json`,
and test logs. Historical
failed outputs remain under `evaluation/` and `evaluation-v2/`. The baseline
canary archive and source receipts remain unchanged.
