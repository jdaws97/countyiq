"""Prompt templates for Pass 0: Document Intelligence."""

EXTRACTION_PROMPT = """You are reading a municipal meeting document from {body_name}, York County, PA.
This is page {page_num} of {total_pages} from a {proceeding_type} meeting on {meeting_date}.

Extract ALL of the following if present on this page:
- Rezoning applications (applicant, parcel/address, current zoning, proposed zoning, decision)
- Variance requests (applicant, parcel/address, variance type, decision)
- Conditional use permits (applicant, parcel/address, proposed use, decision)
- Subdivision/land development reviews (applicant, plan name, parcel/address, proposed lots/units, decision)
- Development proposals discussed (developer/applicant name, project description, location)
- Any entity names associated with property actions

For each extracted record, include:
- The exact text from the document that supports your extraction
- Your confidence level (high/medium/low)

If this page contains no relevant records, return {{"extractions": []}}.

OUTPUT FORMAT:
{{
  "extractions": [
    {{
      "extraction_type": "rezoning_application|variance_request|conditional_use|subdivision_review|development_proposal",
      "applicant_name": "name or null",
      "parcel_reference": "PIDN or address or null",
      "current_zoning": "zone code or null",
      "proposed_zoning": "zone code or null",
      "decision": "approved|denied|tabled|continued|null",
      "conditions": ["list of conditions if any"],
      "supporting_text": "exact quote from the document",
      "confidence": "high|medium|low"
    }}
  ]
}}"""
