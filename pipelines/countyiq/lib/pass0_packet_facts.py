"""Interpret an explicit source inventory without silently omitting its entries."""

from __future__ import annotations

import json
import re
from copy import deepcopy

from jsonschema import Draft202012Validator

from countyiq.lib.pass0_facts import (
    SYSTEM_PROMPT,
    bounded_range_schema,
    document_prompt,
    facts_schema,
    structural_review,
)
from countyiq.lib.pass0_locator import review_locations
from countyiq.lib.pass0_source import SourceDocument

INSTRUCTIONS = """The source inventory below is a navigation aid, not factual authority. Interpret each numbered inventory entry against the complete source. Return one object under EVERY inventory key. Each object has matter, skip_reason and duplicate_of.

For a relevant distinct matter, populate matter using the municipal facts schema and set both skip fields to null. The inventory is intentionally broad: for ordinary administration, event permits, routine repairs or unrelated topics, set matter=null, skip_reason='irrelevant', duplicate_of=null. Do not drop a specific property enforcement, occupancy, failed regulatory review, legal update or land-use policy proposal merely because it lacks new development.

If an entry is entirely part of another inventory matter, retain the complete matter under one key and use matter=null, skip_reason='duplicate', duplicate_of=<retained key's integer> for its duplicate. The retained entry's original source ranges must contain all ranges of the duplicate. Keep different properties, applications, court proceedings and municipal policy amendments separate. A fence appeal and a proposed ordinance revision governing future cases are separate matters.

Read complete source context to verify every proposed outcome and identity. The inventory may have a mistaken title, duplicated topic or insufficient ranges: correct factual interpretation from the source, and cite the necessary source lines. A missing approval result cannot be supplied from another matter. Addresses of neighbors, speakers, offices and applicants' mailing addresses are not project addresses. Code sections such as SLDO/SWMO provisions are regulations, never application identifiers. Contractors and consultants are not automatically applicants. Dates must be date wording, never phrases such as 'completed', 'again' or 'public hearing'.
"""


def interpretation_system_prompt() -> str:
    return SYSTEM_PROMPT + "\n\n" + INSTRUCTIONS


def packet_schema(
    locations: dict,
    document: SourceDocument,
    *,
    evidence_ranges: list[list[int]] | None = None,
    context_ranges: list[list[int]] | None = None,
) -> dict:
    value = {
        "type": "object",
        "additionalProperties": False,
        "required": ["matter", "skip_reason", "duplicate_of"],
        "properties": {
            "matter": {"anyOf": [{"$ref": "#/$defs/matter"}, {"type": "null"}]},
            "skip_reason": {"enum": ["irrelevant", "duplicate", None]},
            "duplicate_of": {"type": ["integer", "null"]},
        },
    }
    keys = [str(index) for index in range(len(locations["matters"]))]
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": keys,
        "properties": {key: deepcopy(value) for key in keys},
        "$defs": facts_schema(document)["$defs"],
    }
    if evidence_ranges is not None:
        schema["$defs"]["range"] = bounded_range_schema(evidence_ranges)
    if context_ranges is not None:
        definitions = schema["$defs"]
        definitions["context_range"] = bounded_range_schema(context_ranges)
        context_lines = {
            "type": "array",
            "items": {"$ref": "#/$defs/context_range"},
            "minItems": 1,
        }
        definitions["context_claim"] = deepcopy(definitions["claim"])
        definitions["context_claim"]["properties"]["lines"] = deepcopy(context_lines)
        context_date = {"anyOf": [{"$ref": "#/$defs/context_claim"}, {"type": "null"}]}
        definitions["matter"]["properties"]["event_date"] = deepcopy(context_date)
        decision = definitions["decision"]["properties"]
        decision["date"] = context_date
        decision["authority"] = {"anyOf": [deepcopy(context_lines), {"type": "null"}]}
        decision["timing_evidence"] = deepcopy(context_lines)
    return schema


def interpretation_prompt(source: dict, locations: dict) -> tuple[str, SourceDocument]:
    prompt, document = document_prompt(source)
    review = review_locations(locations, document)
    if review["envelope_errors"] or review["rejected"] or not review["matters"]:
        raise ValueError(
            "Interpretation requires a complete, nonempty source inventory"
        )
    inventory = {str(index): item for index, item in enumerate(locations["matters"])}
    return (
        prompt + "\n\nSOURCE INVENTORY:\n" + json.dumps(inventory, ensure_ascii=False),
        document,
    )


def full_source_interpretation_prompt(
    source: dict, locations: dict
) -> tuple[str, SourceDocument, list[list[int]], list[list[int]]]:
    """Keep document metadata citable without exposing other matters' votes."""
    prompt, document = interpretation_prompt(source, locations)
    evidence_ranges = [pair for item in locations["matters"] for pair in item["lines"]]
    context_ranges = [[1, len(document.units)]]
    prompt += (
        "\n\nThe full document supplies context for names, roles and timing. "
        "Return only the assigned inventory matters. Event date, decision date, "
        "deciding authority and timing evidence may cite the full document. "
        "All other fields, including decision subject, motion, result and "
        "applicability, must cite the assigned matter ranges encoded in the "
        "schema. A date or authority still needs to apply to its own action; "
        "a document header does not date a reported historical decision."
    )
    return prompt, document, evidence_ranges, context_ranges


def _header_end(document: SourceDocument) -> int:
    header_end = 0
    for unit in document.units[:5]:
        if re.search(
            r"\b(?:motion|moved|seconded|approved|denied|tabled|adopted)\b|"
            r"(?:call|called).{0,20}to order|roll call|public comments?",
            unit.text,
            re.IGNORECASE,
        ):
            break
        header_end = unit.number
    return header_end


def overlap_groups(locations: dict, document: SourceDocument) -> list[list[int]]:
    """Group shared item evidence without linking everything through the header."""
    review = review_locations(locations, document)
    if review["envelope_errors"] or review["rejected"]:
        raise ValueError("Overlap grouping requires valid inventory entries")
    parents = list(range(len(locations["matters"])))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    owners = {}
    header_end = _header_end(document)
    for index, item in enumerate(locations["matters"]):
        for number in _numbers(item):
            if number <= header_end:
                continue
            if number in owners:
                parents[root(index)] = root(owners[number])
            else:
                owners[number] = index
    groups = {}
    for index in range(len(parents)):
        groups.setdefault(root(index), []).append(index)
    return sorted(groups.values(), key=lambda indices: indices[0])


def _numbers(item: dict) -> set[int]:
    return {
        number for first, last in item["lines"] for number in range(first, last + 1)
    }


def review_packet_facts(
    payload: object,
    document: SourceDocument,
    locations: dict,
    *,
    evidence_ranges: list[list[int]] | None = None,
    context_ranges: list[list[int]] | None = None,
) -> dict:
    errors = [
        error.message
        for error in Draft202012Validator(
            packet_schema(
                locations,
                document,
                evidence_ranges=evidence_ranges,
                context_ranges=context_ranges,
            )
        ).iter_errors(payload)
    ]
    if errors:
        return {"matters": [], "rejected": [], "envelope_errors": errors}
    retained, rejected, skipped = [], [], []
    for key, value in payload.items():
        index = int(key)
        matter = value["matter"]
        reason = value["skip_reason"]
        duplicate = value["duplicate_of"]
        if matter is not None:
            if reason is not None or duplicate is not None:
                rejected.append(
                    {"index": index, "errors": ["Retained matter cannot be skipped"]}
                )
                continue
            continuation_ranges = locations["matters"][index]["lines"]
            if evidence_ranges is not None:
                clipped = []
                for first, last in continuation_ranges:
                    for supplied_first, supplied_last in evidence_ranges:
                        start = max(first, supplied_first)
                        end = min(last, supplied_last)
                        if start <= end:
                            clipped.append([start, end])
                continuation_ranges = clipped
            review = structural_review(
                {"matters": [matter]},
                document,
                continuation_ranges=continuation_ranges,
            )
            if review["rejected"] or review["envelope_errors"]:
                rejected.append(
                    {
                        "index": index,
                        "errors": [
                            *review["envelope_errors"],
                            *[
                                error
                                for rejection in review["rejected"]
                                for error in rejection["errors"]
                            ],
                        ],
                    }
                )
                continue
            result = {
                **review["matters"][0],
                "index": index,
                "source_inventory": locations["matters"][index],
            }
            retained.append(result)
            continue
        valid_skip = reason == "irrelevant" and duplicate is None
        if (
            reason == "duplicate"
            and duplicate is not None
            and str(duplicate) in payload
        ):
            target = payload[str(duplicate)]
            valid_skip = (
                duplicate != index
                and target["matter"] is not None
                and target["skip_reason"] is None
                and _numbers(locations["matters"][index]).issubset(
                    _numbers(locations["matters"][duplicate])
                )
            )
        if valid_skip:
            skipped.append(
                {"index": index, "reason": reason, "duplicate_of": duplicate}
            )
        else:
            rejected.append({"index": index, "errors": ["Invalid or unsupported skip"]})
    retained_indices = {matter["index"] for matter in retained}
    valid_skips = []
    for skip in skipped:
        if (
            skip["reason"] == "duplicate"
            and skip["duplicate_of"] not in retained_indices
        ):
            rejected.append(
                {
                    "index": skip["index"],
                    "errors": ["Duplicate target failed validation"],
                }
            )
        else:
            valid_skips.append(skip)
    return {
        "matters": retained,
        "rejected": rejected,
        "envelope_errors": [],
        "skipped": valid_skips,
    }
