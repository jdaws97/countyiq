"""Strict JSON Schemas for pass outputs (OpenRouter structured outputs).

These replace bare ``{"type": "json_object"}`` with
``{"type": "json_schema", "strict": true}`` so schema conformance is
enforced provider-side instead of relying entirely on the post-hoc
clamps in each pass's parser. The parsers stay as defense-in-depth —
strict mode guarantees shape, the clamps guarantee vocabulary even if a
provider's strict implementation is leaky.

Vocabulary enums are imported from the pass modules so there is a
single source of truth; changing a VALID_* set updates the schema too.

Design rules:
- Strict mode requires every property listed in ``required`` and
  ``additionalProperties: false`` at every level.
- Optional-by-meaning fields are typed ``["<type>", "null"]``.
- Enums are used only where the prompt states an exact vocabulary;
  free-text fields stay plain strings so models aren't pushed into
  refusals over wording.
"""

from countyiq.lib.pass2_signal_validation import VALID_SIGNIFICANCE, VALID_STATUSES
from countyiq.lib.pass3_brief_generation import (
    VALID_ASSESSMENTS,
)
from countyiq.lib.pass3_brief_generation import (
    VALID_EVIDENCE as VALID_EVIDENCE_P3,
)
from countyiq.lib.pass3_brief_generation import (
    VALID_RECOMMENDATIONS as VALID_RECOMMENDATIONS_P3,
)
from countyiq.lib.pass3_brief_generation import (
    VALID_URGENCY as VALID_URGENCY_P3,
)
from countyiq.lib.pass3_owner_briefs import (
    VALID_EVIDENCE as VALID_EVIDENCE_P3B,
)
from countyiq.lib.pass3_owner_briefs import (
    VALID_RECOMMENDATIONS as VALID_RECOMMENDATIONS_P3B,
)
from countyiq.lib.pass3_owner_briefs import (
    VALID_STRATEGIES,
)
from countyiq.lib.pass3_owner_briefs import (
    VALID_URGENCY as VALID_URGENCY_P3B,
)


def _nullable_string() -> dict:
    return {"type": ["string", "null"]}


def _string_array() -> dict:
    return {"type": "array", "items": {"type": "string"}}


PASS0_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "extractions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "extraction_type": {
                        "type": "string",
                        "enum": [
                            "rezoning_application",
                            "variance_request",
                            "special_exception",
                            "conditional_use",
                            "subdivision_review",
                            "development_proposal",
                            "ordinance_action",
                        ],
                    },
                    "applicant_name": _nullable_string(),
                    "parcel_reference": _nullable_string(),
                    "current_zoning": _nullable_string(),
                    "proposed_zoning": _nullable_string(),
                    "decision": _nullable_string(),
                    "conditions": _string_array(),
                    "event_tags": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "application",
                                "hearing",
                                "revision",
                                "continuance",
                                "approval",
                                "denial",
                                "condition",
                                "upcoming_decision",
                            ],
                        },
                    },
                    "project_name": _nullable_string(),
                    "related_entities": _string_array(),
                    "what_happened": {"type": "string"},
                    "why_it_matters": _nullable_string(),
                    "what_happens_next": _nullable_string(),
                    "upcoming_date": _nullable_string(),
                    "evidence_spans": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "quote": {"type": "string"},
                                "fields": _string_array(),
                            },
                            "required": ["quote", "fields"],
                            "additionalProperties": False,
                        },
                    },
                    "record_status": {
                        "type": "string",
                        "enum": ["scheduled", "recommendation", "decision", "update"],
                    },
                    "event_date": _nullable_string(),
                    "event_date_text": _nullable_string(),
                    "upcoming_date_iso": _nullable_string(),
                    "application_ids": _string_array(),
                    "project_reference": _nullable_string(),
                    "parcel_references": _string_array(),
                    "matter_category": {
                        "type": "string",
                        "enum": [
                            "development",
                            "minor_property",
                            "landuse_policy",
                            "public_works",
                        ],
                    },
                    "supporting_text": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": [
                    "extraction_type",
                    "applicant_name",
                    "parcel_reference",
                    "current_zoning",
                    "proposed_zoning",
                    "decision",
                    "conditions",
                    "event_tags",
                    "project_name",
                    "related_entities",
                    "what_happened",
                    "why_it_matters",
                    "what_happens_next",
                    "upcoming_date",
                    "supporting_text",
                    "confidence",
                    "evidence_spans",
                    "record_status",
                    "event_date",
                    "event_date_text",
                    "upcoming_date_iso",
                    "application_ids",
                    "project_reference",
                    "parcel_references",
                    "matter_category",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["extractions"],
    "additionalProperties": False,
}


PASS1_ENTITY_VERIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "canonical_name": {"type": "string"},
                    "member_names": _string_array(),
                    "entity_type": {
                        "type": "string",
                        "enum": [
                            "individual",
                            "llc",
                            "corporation",
                            "partnership",
                            "trust",
                            "unknown",
                        ],
                    },
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"},
                    "linked_records": {
                        "type": "object",
                        "properties": {
                            "parcels": _string_array(),
                            "tax_claims": _string_array(),
                            "plcb_licenses": _string_array(),
                            "corporate_entities": _string_array(),
                            "proceedings": _string_array(),
                        },
                        "required": [
                            "parcels",
                            "tax_claims",
                            "plcb_licenses",
                            "corporate_entities",
                            "proceedings",
                        ],
                        "additionalProperties": False,
                    },
                    "relationships": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "related_entity": {"type": "string"},
                                "relationship_type": {
                                    "type": "string",
                                    "enum": [
                                        "controls",
                                        "officer_of",
                                        "registered_agent_for",
                                        "subsidiary_of",
                                        "shares_address_with",
                                        "same_person",
                                        "co_owner_of",
                                    ],
                                },
                                "evidence": {"type": "string"},
                            },
                            "required": [
                                "related_entity",
                                "relationship_type",
                                "evidence",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "canonical_name",
                    "member_names",
                    "entity_type",
                    "confidence",
                    "reasoning",
                    "linked_records",
                    "relationships",
                ],
                "additionalProperties": False,
            },
        },
        "rejected_matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name_a": {"type": "string"},
                    "name_b": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["name_a", "name_b", "reason"],
                "additionalProperties": False,
            },
        },
        "abstentions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "names": _string_array(),
                    "reason": {"type": "string"},
                },
                "required": ["names", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["entities", "rejected_matches", "abstentions"],
    "additionalProperties": False,
}


PASS2_BATCHED_VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "validations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "signal_key": {"type": "string"},
                    "validation_status": {
                        "type": "string",
                        "enum": sorted(VALID_STATUSES),
                    },
                    "adjusted_significance": {
                        "type": "string",
                        "enum": sorted(VALID_SIGNIFICANCE),
                    },
                    "reasoning": {"type": "string"},
                    "key_facts": _string_array(),
                    "cross_references": _string_array(),
                },
                "required": [
                    "signal_key",
                    "validation_status",
                    "adjusted_significance",
                    "reasoning",
                    "key_facts",
                    "cross_references",
                ],
                "additionalProperties": False,
            },
        },
        "cross_signal_insight": _nullable_string(),
    },
    "required": ["validations", "cross_signal_insight"],
    "additionalProperties": False,
}


PASS3_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendation": {"type": "string", "enum": sorted(VALID_RECOMMENDATIONS_P3)},
        "urgency": {"type": "string", "enum": ["none"]},
        "evidence_strength": {"type": "string", "enum": sorted(VALID_EVIDENCE_P3)},
        "confidence": {"type": "number"},
        "top_signal_key": _nullable_string(),
        "top_risk": _nullable_string(),
        "assessment": {"type": "string", "enum": sorted(VALID_ASSESSMENTS)},
        "assessment_reasoning": {"type": "string"},
        "brief": {"type": "string"},
        "key_questions": _string_array(),
        "citations": _string_array(),
    },
    "required": [
        "recommendation",
        "urgency",
        "evidence_strength",
        "confidence",
        "top_signal_key",
        "top_risk",
        "assessment",
        "assessment_reasoning",
        "brief",
        "key_questions",
        "citations",
    ],
    "additionalProperties": False,
}


PASS3B_OWNER_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "portfolio_strategy": {"type": "string", "enum": sorted(VALID_STRATEGIES)},
        "concentration_notes": {"type": "string"},
        "key_pattern": {"type": "string"},
        "recommendation": {"type": "string", "enum": sorted(VALID_RECOMMENDATIONS_P3B)},
        "urgency": {"type": "string", "enum": ["none"]},
        "top_risk": {"type": "string"},
        "evidence_strength": {"type": "string", "enum": sorted(VALID_EVIDENCE_P3B)},
        "confidence": {"type": "number"},
        "narrative": {"type": "string"},
        "citations": _string_array(),
        "parcel_citations": _string_array(),
    },
    "required": [
        "portfolio_strategy",
        "concentration_notes",
        "key_pattern",
        "recommendation",
        "urgency",
        "top_risk",
        "evidence_strength",
        "confidence",
        "narrative",
        "citations",
        "parcel_citations",
    ],
    "additionalProperties": False,
}
