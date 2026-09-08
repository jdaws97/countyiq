"""Source ownership and explicit reference roles for municipal evidence cards."""

from __future__ import annotations

from itertools import combinations

from countyiq.lib.pass0_source import SourceDocument

SELECTION_CONTRACT = "subject-passages-v1"
REFERENCE_ROLES = (
    "subject_property",
    "speaker_address",
    "meeting_venue",
    "representative_address",
    "neighboring_property",
    "other",
    "uncertain",
)


class SubjectValidationError(ValueError):
    """Source attribution is invalid, including malformed JSON field values."""


def source_span(document: SourceDocument, start: int, end: int) -> dict:
    return {
        "start": start,
        "end": end,
        "text": document.text[start:end],
        "source_text_sha256": document.sha256,
    }


def contains_span(parent: dict, child: dict) -> bool:
    return parent["start"] <= child["start"] and child["end"] <= parent["end"]


def spans_overlap(left: dict, right: dict) -> bool:
    return max(left["start"], right["start"]) < min(left["end"], right["end"])


def bind_references(
    items: list[dict],
    document: SourceDocument,
    subject_passages: list[dict],
    context_passages: list[dict],
) -> list[dict]:
    """Bind a classified literal reference; shared context cannot create a link."""
    references = []
    for item in items:
        first, last = item["lines"]
        selected = document.resolve(first, last, document.sha256)
        try:
            quote = document.resolve_quote(
                item["quote"], [(first, last)], document.sha256
            )
        except ValueError as error:
            raise ValueError(
                f"Reference {item['quote']!r} at lines {first}-{last}: {error}. "
                "Use the smallest range containing one occurrence, and copy all "
                "source characters, including whitespace inside wrapped parcel IDs. "
                "Preserve complete source tokens: if OCR joined a preceding word "
                "to an address, include that word in the quote. "
                f"Selected source: {selected.text[:500]!r}"
            ) from error
        reference = source_span(document, quote.start, quote.end)
        permitted = (
            subject_passages
            if item["role"] == "subject_property"
            else [*subject_passages, *context_passages]
        )
        if not any(contains_span(passage, reference) for passage in permitted):
            raise ValueError("Reference is outside its subject's permitted evidence")
        # Retain surrounding original units even if the model omitted a unit or
        # range suffix. Matching must not turn '1 Main St / Suite 4' into a parcel
        # assertion by selecting only the address words on the preceding line.
        surrounding = document.resolve(
            max(1, first - 1), min(len(document.units), last + 1), document.sha256
        )
        reference.update(
            role=item["role"],
            context=source_span(document, surrounding.start, surrounding.end),
        )
        if not contains_span(reference["context"], reference):
            raise ValueError("Reference context does not contain its literal quote")
        # Resolving the complete range above checks its bounds before any scans.
        assert selected.start <= reference["start"] < selected.end
        references.append(reference)
    return references


def validate_subject_cards(cards: list[dict], document: SourceDocument) -> None:
    """Reject cross-card ownership and forged reference provenance before storage.

    Shared context is explicit and cannot overlap anyone's substantive evidence.
    This verifies attribution boundaries and literal membership. A model's role
    classification still needs semantic evaluation against the complete source.
    """
    for card in cards:
        if card.get("selection_contract") != SELECTION_CONTRACT:
            raise ValueError("Municipal card lacks the current subject contract")
        subjects = card.get("subject_passages")
        contexts = card.get("context_passages")
        references = card.get("references")
        if not isinstance(subjects, list) or not subjects:
            raise ValueError("Municipal card needs substantive subject passages")
        if not isinstance(contexts, list) or not isinstance(references, list):
            raise SubjectValidationError(
                "Municipal context and references must be explicit lists"
            )
        if not isinstance(card.get("passages"), list):
            raise SubjectValidationError(
                "Municipal visible passages must be an explicit list"
            )
        spans = [card.get("subject"), *card["passages"], *subjects, *contexts]
        for reference in references:
            if (
                not isinstance(reference, dict)
                or reference.get("role") not in REFERENCE_ROLES
            ):
                raise ValueError("Unknown municipal reference role")
            if not isinstance(reference.get("context"), dict):
                raise SubjectValidationError(
                    "Reference needs surrounding source context"
                )
            spans.extend([reference, reference["context"]])
        for span in spans:
            if (
                not isinstance(span, dict)
                or type(span.get("start")) is not int
                or type(span.get("end")) is not int
                or not 0 <= span["start"] < span["end"] <= len(document.text)
                or span.get("source_text_sha256") != document.sha256
                or span.get("text") != document.text[span["start"] : span["end"]]
            ):
                raise ValueError("Evidence changed after source binding")
        for reference in references:
            allowed = (
                subjects
                if reference["role"] == "subject_property"
                else [*subjects, *contexts]
            )
            if not any(contains_span(passage, reference) for passage in allowed):
                raise ValueError(
                    "Reference is outside its subject's permitted evidence"
                )
            if not contains_span(reference["context"], reference):
                raise ValueError("Reference is outside its surrounding source context")
        if not any(contains_span(passage, card["subject"]) for passage in subjects):
            raise ValueError("Card title must identify its own substantive evidence")
        for passage in [*subjects, *contexts]:
            if not any(contains_span(visible, passage) for visible in card["passages"]):
                raise ValueError(
                    "Subject or shared context is absent from visible evidence"
                )
        for visible in card["passages"]:
            covered = sorted(
                (max(visible["start"], span["start"]), min(visible["end"], span["end"]))
                for span in [*subjects, *contexts]
                if spans_overlap(visible, span)
            )
            end = visible["start"]
            for start, stop in covered:
                if start > end:
                    raise ValueError("Visible evidence contains unassigned source text")
                end = max(end, stop)
            if end != visible["end"]:
                raise ValueError("Visible evidence contains unassigned source text")

    for left, right in combinations(cards, 2):
        if any(
            spans_overlap(a, b)
            for a in left["subject_passages"]
            for b in right["subject_passages"]
        ):
            raise ValueError(
                f"Substantive passages overlap between '{left['title']}' and "
                f"'{right['title']}'; separate each case and put shared headings "
                "or collective decisions in context"
            )
    for context_card in cards:
        for subject_card in cards:
            if any(
                spans_overlap(context, subject)
                for context in context_card["context_passages"]
                for subject in subject_card["subject_passages"]
            ):
                raise ValueError(
                    f"Shared context for '{context_card['title']}' includes "
                    f"substantive evidence owned by '{subject_card['title']}'"
                )
