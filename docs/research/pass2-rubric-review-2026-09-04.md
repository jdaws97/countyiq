# Pass 2 current-evidence rubric review (2026-09-04)

Reviewer: OpenAI Codex GPT-5.6 Sol, an AI reviewer acting at the product
owner's direction. This is not a human review. The review record and release
receipt identify the reviewer this way so the audit trail does not imply that a
person confirmed the labels.

## Scope and method

The review covers every case in
`pipelines/eval/fixtures/p2_expanded_stability20.json` after regenerating the
100-case expanded corpus from the current production evidence view. For each
case, the de-identified parcel, neighbor, portfolio, tax, proceeding, signal,
and context evidence was checked against every accepted status/significance
range, required fact group, and forbidden claim.

The generator was treated as code under review, not as the answer key. Rules
that contradicted current signal semantics or omitted decision-determinative
evidence were corrected in `pipelines/eval/build_expanded_pass2.py`; labels
were then regenerated from stored contexts. The selection/gather invariant now
fails if the selected signal set, gathered signal set, and label set differ.

## Findings and corrections

- The prior corpus silently omitted `entity_assemblage` from its stratification
  even when the gathered prompt contained that production signal. Fifteen of
  100 old cases therefore compared outputs against incomplete labels. The
  current corpus covers all six interpretive signals and 46 observed
  interaction shapes.
- The ownership rubric expected obsolete `buyer_is_llc`; production now emits
  `buyer_name_looks_organizational`. Both current and legacy evidence are
  handled explicitly, and neither is allowed to imply distress, developer
  identity, a flip, or intent.
- A land-development plan may legitimately contain zero lots and zero dwelling
  units. Parcel proximity, acreage, lots, and units are reviewed separately;
  low-scale proposals do not become high significance merely because the
  source record exists.
- Zero assessment and institutional/public ownership are vacancy data-gap or
  non-market warnings absent direct vacancy evidence.
- Agricultural/conservation/open-space labels are compatible, but the word
  `rural` alone no longer erases a real Rural Living to Rural Conservation
  policy shift. Mixed-use and single-use families are also not treated as
  identical.
- Assemblage required facts now include combined adjacent acreage and the
  presence or absence of adjacent delinquency. Ownership-change facts include
  the price-to-assessment ratio when supplied.
- The model prompt now exposes a citeable precomputed adjacent-acre total and
  requires both proposed lots and dwelling units when both source fields are
  present, including zero.

## Case decisions

Every case below was checked against rubric `pass2_expanded_v5`. `Approved`
means its accepted ranges and required/forbidden facts are defensible readings
of the supplied evidence; it does not claim that one stochastic wording is the
only valid answer.

| Case | Signals | Decision |
|---|---|---|
| p2x-040 | vacancy, zoning_mismatch | Approved |
| p2x-005 | active_subdivision, ownership_change | Approved |
| p2x-004 | active_subdivision, entity_assemblage | Approved |
| p2x-002 | active_subdivision, assemblage | Approved |
| p2x-013 | assemblage, entity_assemblage | Approved |
| p2x-008 | active_subdivision, vacancy | Approved |
| p2x-023 | assemblage, zoning_mismatch | Approved |
| p2x-050 | active_subdivision, assemblage, zoning_mismatch | Approved |
| p2x-061 | assemblage, entity_assemblage, ownership_change | Approved |
| p2x-049 | active_subdivision, assemblage, zoning_mismatch | Approved |
| p2x-051 | active_subdivision, entity_assemblage, ownership_change | Approved |
| p2x-057 | active_subdivision, ownership_change, zoning_mismatch | Approved |
| p2x-075 | entity_assemblage, ownership_change, zoning_mismatch | Approved |
| p2x-058 | active_subdivision, ownership_change, zoning_mismatch | Approved |
| p2x-086 | active_subdivision, assemblage, vacancy, zoning_mismatch | Approved |
| p2x-089 | active_subdivision, entity_assemblage, ownership_change, zoning_mismatch | Approved |
| p2x-093 | active_subdivision, ownership_change, vacancy, zoning_mismatch | Approved |
| p2x-082 | active_subdivision, assemblage, entity_assemblage, ownership_change | Approved |
| p2x-095 | assemblage, entity_assemblage, ownership_change, zoning_mismatch | Approved |
| p2x-100 | entity_assemblage, ownership_change, vacancy, zoning_mismatch | Approved |

## Minimal-spend validation

The first 20-case Luna run was archived and reused for later rubric rescoring,
so corrections did not trigger duplicate provider calls. Rescoring those same
outputs against v5 produced 55/59 grounded decisions, 155/178 required facts,
zero prohibited claims, and 20/20 production gates. The four decision misses
were exactly the newly clarified low-scale-plan and vacancy-data-gap classes.

Rerunning only those four cases with the corrected prompt produced 11/11
grounded decisions, 31/34 required facts, zero prohibited claims, and 4/4
production gates for $0.00557. Combining those four with the sixteen archived
outputs gives 59/59 grounded decisions, zero prohibited claims, and 20/20
production gates. A final one-case check of the citeable adjacent-acre and
lots/units rules produced 2/2 grounded decisions and, after the reviewed
no-delinquency phrasing correction, 8/8 required facts for $0.00167.

## Conclusion

The old expanded fact-recall score is not comparable to the current corpus. It
mixed an obsolete six-key rubric with a prompt that could contain an unlabeled
sixth signal, so the apparent drop was substantially a scoring artifact. The
review also found genuine prompt-calibration gaps; those were corrected and
verified on the smallest failing subset. The refreshed 20-case fixture is the
