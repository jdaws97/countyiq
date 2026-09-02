"""Static prompt blocks appended to pass system prompts.

Two purposes:

1. Restate the enforced output contract (schema or field list) and the
   citation format the serving gate checks, as plain text.
2. Make the byte-identical system prefix long enough for provider prompt
   caching. OpenAI caches only prompts whose identical prefix is at least
   1,024 tokens; the bare instruction blocks were 490–840 tokens, so no call
   was ever cached. ``tests/test_prompt_cache_prefix.py`` guards the floor.

Every block here is static text with no per-item data. Blocks must not add
domain semantics: a 2026-09-02 trial that appended a signal glossary shifted
Luna's Pass 2 statuses from "downgraded" to "confirmed" on the reviewed gold
cases, so only format and contract restatements are allowed here.
"""

from __future__ import annotations

import json


def schema_block(schema: dict) -> str:
    """Static rendering of the enforced output schema."""
    return "OUTPUT JSON SCHEMA (enforced by the API; conform exactly):\n" + json.dumps(
        schema, indent=1, sort_keys=True
    )


CITATION_FORMAT_BLOCK = """CITATION FORMAT RULES (checked mechanically before any output is served):
- A citation marker is square-bracketed and copied verbatim from a ref printed in the input, for example [Evidence: parcels:1234567890123], [Evidence: signal:vacancy], [Evidence: context:growth_area], [Signal: vacancy], or [Parcel: 1234567890123].
- Put each marker at the end of the sentence it supports. Several markers may follow one sentence; use one bracket pair per ref.
- Never invent a ref, and never change its prefix, group, spelling, spacing, or case. A ref that was not printed in the input is invalid even if it looks plausible.
- Every prose field that states a fact must contain at least one valid marker. When no printed ref supports a statement, say that the evidence is missing instead of asserting the fact.
- Machine-readable citation arrays (cross_references, citations, parcel_citations) must list exactly the refs used in the prose for that item, with no duplicates and no unused entries.
- Identifiers copied into structured fields (member_names, linked_records, signal_key, PIDNs) must match the input byte for byte.

Well-formed examples:
- "The parcel has no mapped building footprint [Evidence: signal:vacancy]."
- "Two touching parcels list the same recorded owner [Evidence: signal:entity_assemblage] [Evidence: context:growth_area]."
- "The recorded sale is not corroborated by any listed proceeding [Signal: ownership_change]."
- "Three of the six parcels carry a current delinquency indicator [Signal: tax_distress] [Parcel: 1234567890123]."
- "The candidate names share a PA DOS entity number [Evidence: candidate:ACME HOLDINGS LLC] [Evidence: corporate_entities:ACME HOLDINGS LLC]."

Malformed examples (rejected):
- "[evidence: vacancy]" — wrong prefix case and missing group.
- "[Signal: Vacancy]" — key case changed.
- "[Evidence: signal:vacancy, context:growth_area]" — two refs in one bracket pair.
- "(signal:vacancy)" — not bracketed.
- "[Parcel: 1234567890123 and 1234567890124]" — two identifiers in one marker."""


PASS3_FIELD_CONTRACT = """FIELD CONTRACT (restates the enforced schema; every value must be one of the listed options):
- recommendation: pursue_now | watchlist | pass
- urgency: urgent_30d | near_term_90d | long_term_12mo | none; a pass recommendation requires none, and pursue_now cannot use none
- top_signal_key: one validated signal_key from the input, or null; when present it must also appear in citations
- top_risk: one cited sentence
- evidence_strength: strong | moderate | weak
- confidence: a number from 0.0 to 1.0
- assessment: strong_opportunity | emerging | speculative | constrained | not_actionable; pursue_now pairs only with strong_opportunity or emerging, watchlist with emerging, speculative, or constrained, and pass with constrained or not_actionable
- assessment_reasoning: one to two cited sentences
- brief: two to four cited paragraphs consistent with the structured fields
- key_questions: a list of short strings
- citations: the exact list of signal keys cited in the prose, without duplicates"""


PASS3B_FIELD_CONTRACT = """FIELD CONTRACT (restates the enforced schema; every value must be one of the listed options):
- portfolio_strategy: accumulator | flipper | holder | distressed | institutional | unclear
- concentration_notes: one cited sentence
- key_pattern: one to two cited sentences
- recommendation: pursue_acquisition | monitor | compete | none; monitor is allowed only with weak evidence_strength, and none requires urgency none
- urgency: urgent_30d | near_term_90d | long_term_12mo | none
- top_risk: one cited sentence
- evidence_strength: strong | moderate | weak
- confidence: a number from 0.0 to 1.0
- narrative: three to five cited paragraphs consistent with the structured fields
- citations: the exact list of signal keys cited in the prose, without duplicates
- parcel_citations: the exact list of PIDNs cited in the prose, without duplicates"""


PASS0_DEFINITIONS = """EXTRACTION TYPE DEFINITIONS:
- rezoning_application: a request to change a parcel's zoning district or map classification.
- variance_request: relief from a dimensional or use requirement of the zoning ordinance, decided by a zoning hearing board.
- special_exception: a use the ordinance permits in the district subject to zoning hearing board approval and stated criteria.
- conditional_use: a use permitted with conditions by the governing body (supervisors, council, commissioners) after a hearing.
- subdivision_review: review of a subdivision or land development plan (sketch, preliminary, or final) by a planning commission or governing body.
- development_proposal: a project discussed or presented without a formal application matter on the agenda.

EVENT TAG DEFINITIONS (include every tag the document supports):
- application: the matter was filed, submitted, or introduced.
- hearing: the matter was heard, discussed, or presented at this meeting.
- revision: a revised plan, amended request, or changed scope was presented.
- continuance: the matter was tabled, continued, or postponed to a later date.
- approval / denial: a recorded vote or decision granting or refusing the request.
- condition: an approval subject to stated conditions; list them in conditions.
- upcoming_decision: a decision is expected at a stated future meeting or deadline.

DECISION VALUES: approved, denied, tabled, continued, or null when this document records no decision. Never infer a decision from a recommendation, a motion without a vote, or a future agenda item."""
