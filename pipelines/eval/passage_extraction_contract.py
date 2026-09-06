"""Offline candidate: select source passages instead of generating quotations.

This schema is not wired into paid inference or publication. Hydrated records
must still pass the existing evidence and semantic release checks.
"""

from copy import deepcopy
from jsonschema import Draft202012Validator, ValidationError

from countyiq.lib.pass_schemas import PASS0_EXTRACTION_SCHEMA
from countyiq.lib.source_passages import PassageDocument

CANDIDATE_SCHEMA = deepcopy(PASS0_EXTRACTION_SCHEMA)
CANDIDATE_SCHEMA["properties"]["source_sha256"] = {
    "type": "string",
    "pattern": "^[0-9a-f]{64}$",
}
CANDIDATE_SCHEMA["required"].append("source_sha256")
_item = CANDIDATE_SCHEMA["properties"]["extractions"]["items"]
for _field in ("supporting_text", "evidence_spans"):
    del _item["properties"][_field]
    _item["required"].remove(_field)
_item["properties"]["evidence_refs"] = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "properties": {
            "passage_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "uniqueItems": True,
            },
            "fields": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(_item["properties"])},
                "minItems": 1,
                "uniqueItems": True,
            },
        },
        "required": ["passage_ids", "fields"],
        "additionalProperties": False,
    },
}
_item["required"].append("evidence_refs")
_VALIDATOR = Draft202012Validator(CANDIDATE_SCHEMA)


def passage_input(document: PassageDocument) -> dict:
    return {
        "source_sha256": document.source_sha256,
        "passages": [{"id": p.passage_id, "text": p.text} for p in document.passages],
    }


def hydrate_extractions(payload: dict, document: PassageDocument) -> list[dict]:
    """Recover exact text while retaining the unmodified model payload separately."""
    try:
        _VALIDATOR.validate(payload)
    except ValidationError as error:
        raise ValueError(
            f"Invalid passage candidate at {error.json_path}: {error.message}"
        ) from error
    if payload["source_sha256"] != document.source_sha256:
        raise ValueError("Candidate belongs to a different source")
    hydrated = []
    for item in payload["extractions"]:
        by_passage = {}
        for reference in item["evidence_refs"]:
            for passage in document.resolve(
                payload["source_sha256"], reference["passage_ids"]
            ):
                if passage.passage_id not in by_passage:
                    by_passage[passage.passage_id] = (passage, set())
                by_passage[passage.passage_id][1].update(reference["fields"])
        ordered = sorted(by_passage.values(), key=lambda entry: entry[0].start)
        spans = [
            {"quote": passage.text, "fields": sorted(fields)}
            for passage, fields in ordered
        ]
        display = next(
            (span["quote"] for span in spans if "what_happened" in span["fields"]),
            spans[0]["quote"],
        )
        result = deepcopy(item)
        del result["evidence_refs"]
        result.update(evidence_spans=spans, supporting_text=display)
        hydrated.append(result)
    return hydrated
