"""Refine selection boundaries without changing source text or value filtering."""

from countyiq.lib.municipal_value import source_value
from countyiq.lib.pass0_source import SourceDocument, SourceUnit


def refine_source_units(
    document: SourceDocument, specification: dict
) -> SourceDocument:
    """Apply operator-selected character offsets to one hash-bound source."""
    if specification.get("source_text_sha256") != document.sha256:
        raise ValueError("Unit refinement source hash does not match")
    offsets = specification.get("offsets")
    if (
        not isinstance(offsets, list)
        or not offsets
        or any(
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or not 0 < offset < len(document.text)
            for offset in offsets
        )
    ):
        raise ValueError("Unit refinement requires valid character offsets")
    boundaries = sorted(set(offsets))
    units = []
    for unit in document.units:
        start = unit.start
        for end in [
            *(offset for offset in boundaries if unit.start < offset < unit.end),
            unit.end,
        ]:
            units.append(
                SourceUnit(len(units) + 1, start, end, document.text[start:end])
            )
            start = end
    refined = SourceDocument(document.text, document.sha256, tuple(units))

    def excluded_text(source):
        value = source_value(source)
        return (
            value.skip_reason,
            "".join(
                unit.text
                for unit in source.units
                if unit.number in value.excluded_lines
            ),
        )

    if excluded_text(document) != excluded_text(refined):
        raise ValueError("Unit refinement changes the accounting exclusion policy")
    return refined
