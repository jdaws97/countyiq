"""Evaluate document-level discovery with explicitly deferred enrichment fields."""

from copy import deepcopy

from countyiq.lib.pass0_facts import SYSTEM_PROMPT, facts_schema, structural_review
from countyiq.lib.pass0_source import SourceDocument
from jsonschema import Draft202012Validator

from eval.pass0_schema_guidance import annotated_schema

DEFERRED_FIELDS = ("conditions", "milestones")


def discovery_system_prompt() -> str:
    paragraphs = [
        paragraph
        for paragraph in SYSTEM_PROMPT.split("\n\n")
        if not paragraph.startswith("conditions preserve")
    ]
    paragraphs.append(
        "This is discovery for later intelligence work. Read every substantive "
        "section and preserve distinct matters, grounded identities, actual "
        "actions and their source passages. Detailed conditions and milestones "
        "are explicitly deferred: do not emit those two fields. Keep their "
        "substantive source passages in summary.excerpts so later enrichment "
        "can recover them. An omitted detail does not mean the source lacks it. "
        "event_date copies the stated reporting date; do not use the current "
        "header to date an earlier action. Preserve uncertain project attachment "
        "in conflicts instead of assigning ambiguous evidence confidently. "
        "Separate different properties even when one sentence reports their "
        "shared status. Empty matters is appropriate only when the entire "
        "document has no relevant activity."
    )
    return "\n\n".join(paragraphs)


def discovery_schema(document: SourceDocument) -> dict:
    schema = annotated_schema(facts_schema(document))
    matter = schema["$defs"]["matter"]
    for field in DEFERRED_FIELDS:
        del matter["properties"][field]
        matter["required"].remove(field)
    del schema["$defs"]["milestone"]
    return schema


def review_discovery(payload: object, document: SourceDocument) -> dict:
    errors = [
        error.message
        for error in Draft202012Validator(discovery_schema(document)).iter_errors(
            payload
        )
    ]
    if errors:
        return {"matters": [], "rejected": [], "envelope_errors": errors}
    hydrated = deepcopy(payload)
    for matter in hydrated["matters"]:
        for field in DEFERRED_FIELDS:
            matter[field] = []
    review = structural_review(hydrated, document)
    for matter in review["matters"]:
        for field in DEFERRED_FIELDS:
            del matter[field]
        matter["extraction_scope"] = "discovery"
        matter["deferred_fields"] = list(DEFERRED_FIELDS)
    review["source_candidates"] = _source_candidates(payload, review, document)
    return review


def _source_candidates(
    payload: dict, review: dict, document: SourceDocument
) -> list[dict]:
    """Keep bounded source text for revisiting failed excerpt selections.

    A candidate is not an extracted matter. Its source lines may include other
    projects, so none of the rejected interpretation is promoted into facts.
    """
    candidates = []
    for rejection in review["rejected"]:
        item = payload["matters"][rejection["index"]]
        excerpts = item["summary"]["excerpts"]
        try:
            for excerpt in excerpts:
                document.resolve_excerpt(
                    excerpt["start"],
                    excerpt["end"],
                    *excerpt["lines"],
                    document.sha256,
                )
        except ValueError:
            pass
        else:
            # A different validation failure does not justify replacing an
            # already valid excerpt selection with a broader source range.
            continue
        try:
            spans = document.resolve_ranges(
                [tuple(excerpt["lines"]) for excerpt in excerpts], document.sha256
            )
        except ValueError:
            continue
        if any(not span.text.strip() for span in spans):
            continue
        candidates.append(
            {
                "index": rejection["index"],
                "suggested_title": item["title"],
                "review_flags": ["source_selection_review_needed"],
                "semantic_review_complete": False,
                "original_errors": deepcopy(rejection["errors"]),
                "original_excerpt_selection": deepcopy(excerpts),
                "source_passages": [
                    {
                        "start": span.start,
                        "end": span.end,
                        "quote": span.text,
                        "source_sha256": document.sha256,
                    }
                    for span in spans
                ],
            }
        )
    return candidates
