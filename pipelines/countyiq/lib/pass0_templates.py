"""Prompt templates for Pass 0: Document Intelligence.

The prompt is split into a static system block and a dynamic user block so
providers with implicit prompt caching (OpenAI, DeepSeek, Gemini, ...) can
cache the instruction prefix across the whole batch — only the per-document
header and document text vary call to call.
"""

import hashlib as _hashlib

from countyiq.lib.pass_schemas import PASS0_EXTRACTION_SCHEMA
from countyiq.lib.prompt_prefix import PASS0_DEFINITIONS, schema_block

# Static instruction block. It uses doubled braces so `.format()` can produce
# the final JSON examples without treating them as interpolation fields.
_SYSTEM_TEMPLATE = """You are a municipal-government document analyst extracting structured property records from meeting documents.

Read the ENTIRE document and extract ALL of the following if present:
- Rezoning applications (applicant, parcel/address, current zoning, proposed zoning, decision)
- Variance requests (applicant, parcel/address, variance type, decision)
- Special exception applications (applicant, parcel/address, proposed use, decision)
- Conditional use permits (applicant, parcel/address, proposed use, decision)
- Subdivision/land development reviews (applicant, plan name, parcel/address, proposed lots/units, decision)
- Development proposals discussed (developer/applicant name, project description, location)
- Any entity names associated with property actions

Return one extraction per distinct application or project matter. When one
matter requests multiple related forms of relief, choose the best-supported
primary extraction_type and summarize the other requests in the grounded text
fields; do not duplicate the same applicant/project/parcel as separate records.

For each extracted record, include:
- The exact text from the document that supports your extraction
- Your confidence level (high/medium/low)
- Event tags describing every supported procedural state: application,
  hearing, revision, continuance, approval, denial, condition, and/or
  upcoming_decision
- A concise project name when the document gives enough information
- Other named entities directly involved in the matter
- "what_happened": a neutral one-sentence statement of the sourced fact
- "why_it_matters": a concise procedural or development implication grounded
  in the document; use null when the document does not support one
- "what_happens_next": the stated or procedurally likely next step, clearly
  identifying uncertainty; use null when no next step can be supported
- "upcoming_date": preserve the document's wording for a future meeting or
  deadline (including approximate wording such as "next month"), or null

Do not infer market value, financing, owner motivation, probability of
approval, or construction intent unless the document explicitly states it.
The supporting_text quote remains the authoritative evidence.

If the document contains no relevant records, return {{"extractions": []}}.

OUTPUT FORMAT:
{{
  "extractions": [
    {{
      "extraction_type": "rezoning_application|variance_request|special_exception|conditional_use|subdivision_review|development_proposal",
      "applicant_name": "name or null",
      "parcel_reference": "PIDN or address or null",
      "current_zoning": "zone code or null",
      "proposed_zoning": "zone code or null",
      "decision": "approved|denied|tabled|continued|null",
      "conditions": ["list of conditions if any"],
      "event_tags": ["application", "hearing", "approval"],
      "project_name": "stated or concise grounded name, or null",
      "related_entities": ["other directly involved names"],
      "what_happened": "neutral sourced fact",
      "why_it_matters": "grounded procedural significance or null",
      "what_happens_next": "stated or qualified next step or null",
      "upcoming_date": "source wording for next meeting/deadline or null",
      "supporting_text": "exact quote from the document",
      "confidence": "high|medium|low"
    }}
  ]
}}

Return ONLY valid JSON."""

# Dynamic per-document header. The trailing "valid JSON" sentence is
# load-bearing: OpenAI-family endpoints reject json_object response format
# unless the prompt mentions JSON (found 2026-08-06 when every
# gpt-5-nano/gpt-5.6-luna Pass 0 call 400'd) — keeping it in the user
# message guarantees the requirement holds regardless of message layout.
EXTRACTION_USER_TEMPLATE = """This is a municipal meeting document from {body_name}, {county_name}, {state}.
It is a {proceeding_type} meeting document{date_clause}.

Extract all relevant property records from it. Return ONLY valid JSON."""

# Final system string sent to the API (single braces). The static definition
# and schema blocks carry the vocabulary contract and push the byte-identical
# prefix past the provider caching minimum (see prompt_prefix.py).
PASS0_SYSTEM_PROMPT = (
    _SYSTEM_TEMPLATE.format()
    + "\n\n"
    + PASS0_DEFINITIONS
    + "\n\n"
    + schema_block(PASS0_EXTRACTION_SCHEMA)
)


# Covers both halves of the prompt so a contract change invalidates the input
# hash even when the source document itself is unchanged.
PROMPT_VERSION = _hashlib.sha256(
    (PASS0_SYSTEM_PROMPT + "\n\n" + EXTRACTION_USER_TEMPLATE).encode("utf-8")
).hexdigest()[:12]
