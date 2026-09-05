# Pass 2 stability-subset rubric review (2026-09-03)

Reviewer: Claude Fable 5.1, an AI reviewer acting at the product owner's
direction. This is not a human review. The product owner chose to delegate
the one-time 20-case label confirmation that `intelligence-rollout.md`
section 2 requires; the receipt outside the tree names the reviewer the same
way so the audit trail does not imply a person confirmed these labels.

Scope: every case in `pipelines/eval/fixtures/p2_expanded_stability20.json`,
inspected as the de-identified context (parcel facts, neighbors, tax claims,
proceedings, signal evidence, context signals) against the generated accepted
status/significance ranges, required fact groups, and forbidden claims.

## Method

1. Read each signal's evidence and the parcel context, and decide what a
   careful analyst following the Pass 2 prompt rules would return.
2. Compare with the generated rubric. Where the rubric contradicted the
   evidence or the score-version-7 signal contract, the generator rule was
   corrected in `pipelines/eval/build_expanded_pass2.py` (rubric
   `pass2_expanded_v2`) rather than editing labels by hand, so the same rule
   applies to every case and the correction is reproducible.
3. Labels were regenerated with `python -m eval.build_expanded_pass2 --relabel`
   from the stored contexts. Contexts and `context_sha256` values are
   unchanged; only labels and the `review` block changed.

## Generator rules corrected

| Rule | Was | Now | Why |
|---|---|---|---|
| `active_subdivision` believability | `max(lots, units) >= 3` confirms; 0 or 1 forces downgrade | believable when `pt_land_dev = YES` or `prop_du > 0` (the v7 signal filter); plus a plausibility test that the plan point sits within one parcel width and the plan is not far smaller than the parcel | Land-development plans (commercial/industrial buildings) legitimately have zero lots and zero dwelling units. The old rule penalized a correct "confirmed" on exactly the plan class the v7 filter keeps. |
| `vacancy` status | only class F with no footprint may be confirmed | F/A confirmed; R under the $50k screen confirmed or downgraded; C/I confirmed or downgraded at low significance; zero assessment or institutional owner forces downgrade | The deterministic signal already caps residential parcels at $50k. A $35k residential parcel with no footprint is land-only value; forcing "downgraded" contradicted the signal contract. |
| `zoning_mismatch` compatibility | four hard-coded keyword pairs (rural, commercial, industrial, residential) | coarse land-use families (rural/open, residential, commercial, industrial, institutional); overlap means no divergence | "Agricultural-Conservation Zone" vs "Rural Conservation / Open Space" and "Open Space Residential / Agricultural" vs "Parks, Recreation and Open Space" are the same family, not a divergence. |

Unchanged rules were checked and kept: the `assemblage` scale/institutional
rule (the "Company" alias deliberately stands in for utilities in the
de-identified corpus), the neighbor-delinquency fact group (each flagged case
has a neighbor with a delinquency history in the context), and the
`ownership_change` price bands and forbidden claims.

## Case decisions

All 20 cases are approved against rubric v2. "Changed" lists the label
differences from rubric v1.

| Case | Signals | Decision | Notes |
|---|---|---|---|
| p2x-095 | active_subdivision, assemblage, vacancy, zoning_mismatch | approved | 67-lot plan whose acreage equals the parcel; R-1 vs Open Space Residential is one family. No change. |
| p2x-076 | assemblage, ownership_change, zoning_mismatch | approved | $3.4M LLC purchase of commercial land planned residential; strongest case in the subset. No change. |
| p2x-087 | active_subdivision, assemblage, ownership_change, zoning_mismatch | approved | 87-lot plan matching parcel acreage; residential zoning vs institutional plan is a real divergence. No change. |
| p2x-088 | active_subdivision, assemblage, ownership_change, zoning_mismatch | approved | 3-lot plan on a 38-acre tract within reach of this 19-acre parcel; rural agricultural vs rural open space is one family. No change. |
| p2x-082 | ownership_change, vacancy, zoning_mismatch | approved | Changed: vacancy may be confirmed (class R, $35,300 assessed, no footprint, land-only value). |
| p2x-045 | ownership_change, zoning_mismatch | approved | $159k individual purchase; rural residential vs rural conservation is one family. No change. |
| p2x-097 | active_subdivision, ownership_change, vacancy, zoning_mismatch | approved | Changed: land-development plan 36 m away with matching acreage on an industrial parcel may be confirmed; vacancy on industrial land may be confirmed or downgraded at low significance. |
| p2x-099 | assemblage, ownership_change, vacancy, zoning_mismatch | approved | Changed: vacancy may be confirmed (class R, $21,150 assessed, 4.7 acres). |
| p2x-067 | active_subdivision, ownership_change, zoning_mismatch | approved | A 5.1-acre plan 231 m from a 0.165-acre house lot is not this parcel's plan; downgrade stands. Commercial vs residential plan is a real divergence. No change. |
| p2x-062 | active_subdivision, assemblage, zoning_mismatch | approved | Changed: land-development plan 87 m away whose acreage matches the 33-acre parcel and whose title matches the owner alias may be confirmed. Industrial zoning vs rural conservation plan is a real divergence. Assemblage stays downgraded because the owner alias is institutional. |
| p2x-080 | assemblage, vacancy, zoning_mismatch | approved | Changed: open-space/agricultural zoning vs parks/open-space plan is one family, so zoning divergence must be downgraded. Vacancy stays downgraded because the assessment is zero (data gap). |
| p2x-077 | assemblage, ownership_change, zoning_mismatch | approved | $1.18M LLC purchase of 43 acres; residential-agricultural vs agriculture/low-density plan is one family. No change. |
| p2x-056 | active_subdivision, assemblage, ownership_change | approved | 3-unit land-development plan 10 m away with matching acreage; $1.3M sale. No change. |
| p2x-075 | assemblage, ownership_change, zoning_mismatch | approved | Agricultural zoning vs residential plan is a real divergence; $500k LLC purchase. No change. |
| p2x-024 | assemblage, ownership_change | approved | One-acre residential lot sold for $1.45M; neighbor-fragmentation is not an assemblage signal here, downgrade stands. No change. |
| p2x-044 | ownership_change, vacancy | approved | Changed: vacancy may be confirmed (class R, $29,120 assessed, half-acre lot sold for $99,900). |
| p2x-089 | active_subdivision, assemblage, ownership_change, zoning_mismatch | approved | A one-lot plan 237 m from a 1.2-acre parcel is beyond one parcel width; downgrade stands. No change. |
| p2x-084 | active_subdivision, assemblage, ownership_change, zoning_mismatch | approved | Changed: agricultural-conservation zoning vs rural conservation plan is one family, so zoning divergence must be downgraded. The 2-lot plan on a 78-acre farm sold for $1.375M stays confirmed-or-downgraded. |
| p2x-093 | active_subdivision, assemblage, vacancy, zoning_mismatch | approved | Changed: vacancy on an industrial parcel with no footprint may be confirmed or downgraded at low significance. The 4-lot land-development plan whose title matches the owner stays confirmed. |
| p2x-078 | assemblage, vacancy, zoning_mismatch | approved | Class F, $820 assessed, no footprint: confirmed vacancy stands. Rural living vs rural conservation is one family. No change. |

## Effect on the wider expanded corpus

Applying rubric v2 to all 100 expanded cases changed status or significance
ranges on 49 cases, mostly residential vacancy cases that v1 forced to
"downgraded". Those 80 unreviewed cases keep
`rubric_generated_requires_human_confirmation`; only the 20 above carry
`rubric_reviewed`.

## Caveats

- The corpus was frozen before score version 7. Several `active_subdivision`
  cases sit 90 to 240 m from the parcel; under v7 those would be
  `nearby_subdivision` context, not a validated signal. The evidence keys
  (`buyer_is_llc`, centroid flood zone) also predate v7. The corpus is still a
  valid regression oracle for model comparison, but it does not represent the
  live v7 workload; refresh the live shadow after the York backfill.
- De-identification replaces owner names with stable aliases. The review
  judged institutional ownership from the alias pattern the corpus README
  documents; it could not verify the underlying real owner.
- Approval means the accepted ranges are defensible readings of the evidence,
  not that any single status is the only correct one.

## Eval runs after the 2026-09-03 changes (Luna, $0.26 total)

Run with the production model after the Pass 0 `ordinance_action` schema,
the Pass 2 evidence-keys-v2 formatter and resolved-owner portfolio, and the
withdrawal of the person-naming prompt rules.

| Lane | Result | Prior (2026-09-02) |
|---|---|---|
| Pass 0 frozen gold (6 PDFs) | 5/6 gold, 5/5 records, 0 extras, $0.011 | Luna text mode 4/4 records, same Dillsburg quote-gate miss |
| Pass 2 frozen gold (10) | 3/10 cases, 11/20 strict, 20/20 status, 19/20 decisions, 0 prohibited, facts 35/48 | 4/10, 11/20, 17/20, 17/20, 0, 37/48 |
| Pass 2 expanded (100, rubric v2) | trials A/B: 13/10 cases, 117/106 strict, 192/194 decisions, 0/1 prohibited, facts 556/547 of 683 | rubric v1: 191 decisions, 133 strict, 595 facts, 0 prohibited |
| Pass 2 expanded rescored on rubric v1 labels | 12 cases, 111 strict, 195 decisions, 556 facts | same as above |
| Pass 3 frozen gold (4) | 1/4 (p3-004 flipped on `recommendation` only) | 2/4 |

Attribution check: rendering the prompt for eight frozen cases from the
committed code and from this tree differs only in dropped `source_url`
values and the extra evidence keys now shown (`pt_land_dev`, `total_acres`,
`screening_only`, soil map units, PennDOT dates). The system prompt and rules
are identical. The most-missed required facts (`no delinquency` for
assemblage 33/34, `structure_count=0` 23/48, `buyer_is_llc=False` 14/32,
zero-unit plans 14/14) are rubric phrasings derived from the old six-key
evidence view; with more keys on screen the model spends its `key_facts` on
facts the rubric does not count. Regenerating the expanded corpus from the
current view changes labels on 99 of 100 cases and resets the 20-case review,
so it was not done here; the file in the tree is byte-identical to the
reviewed version.
