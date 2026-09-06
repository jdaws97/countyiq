"""Offline experiment: select exact source ranges without copying quotations.

This is not a serving contract. Original text (including PDF layout artifacts)
is neither normalized nor repaired. Membership alone never proves entailment.
"""

from dataclasses import dataclass
import hashlib
import json

from countyiq.lib.source_passages import SourcePassage


@dataclass(frozen=True)
class EvidenceRangeDocument:
    source_text: str
    source_sha256: str
    units: tuple[SourcePassage, ...]

    def model_input(self) -> str:
        """Expose selectors and original text; the caller owns the fingerprint."""
        return json.dumps(
            {
                "source_units": [
                    {"id": unit.passage_id, "text": unit.text} for unit in self.units
                ]
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def resolve(
        self, expected_source_sha256: str, *, first_id: str, last_id: str
    ) -> SourcePassage:
        """Recover one continuous original range, never concatenate quotations."""
        if expected_source_sha256 != self.source_sha256:
            raise ValueError("Evidence range belongs to a different source")
        if not isinstance(first_id, str) or not isinstance(last_id, str):
            raise ValueError("Evidence range IDs must be strings")
        by_id = {unit.passage_id: unit for unit in self.units}
        if first_id not in by_id or last_id not in by_id:
            raise ValueError("Unknown evidence range ID")
        first, last = by_id[first_id], by_id[last_id]
        if first.start > last.start:
            raise ValueError("Evidence range is reversed")
        return SourcePassage(
            f"{first_id}..{last_id}",
            first.start,
            last.end,
            self.source_text[first.start : last.end],
        )


def index_evidence_ranges(
    source_text: str, *, max_unit_chars: int = 1200
) -> EvidenceRangeDocument:
    """Index original lines, splitting unusually long lines at word boundaries.

    Every character appears once. Unicode character offsets match stored source
    spans; the SHA-256 covers original UTF-8 bytes. Version and size are in every
    selector, so old passage IDs or a new segmentation cannot silently resolve.
    """
    if not isinstance(source_text, str):
        raise TypeError("Source text must be a string")
    if (
        isinstance(max_unit_chars, bool)
        or not isinstance(max_unit_chars, int)
        or max_unit_chars < 2
    ):
        raise ValueError("max_unit_chars must be an integer of at least two")
    units = []
    offset = 0
    for line in source_text.splitlines(keepends=True):
        line_end = offset + len(line)
        while offset < line_end:
            end = min(offset + max_unit_chars, line_end)
            if end < line_end:
                split = source_text.rfind(" ", offset + max_unit_chars // 2, end)
                if split >= 0:
                    end = split + 1
            selector = f"r1-{max_unit_chars}-u{len(units) + 1:04d}"
            units.append(SourcePassage(selector, offset, end, source_text[offset:end]))
            offset = end
    return EvidenceRangeDocument(
        source_text,
        hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        tuple(units),
    )
