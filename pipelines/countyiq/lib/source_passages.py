"""Source-bound passage indexing for offline extraction-contract evaluation.

No model calls or publication. Passage selection establishes source membership,
not whether a claim follows from the selected source text.
"""
from dataclasses import dataclass
import hashlib


@dataclass(frozen=True)
class SourcePassage:
    passage_id: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class PassageDocument:
    source_sha256: str
    passages: tuple[SourcePassage, ...]

    def resolve(self, source_sha256: str, passage_ids: list[str]) -> tuple[SourcePassage, ...]:
        """Resolve distinct IDs in source order; never concatenate disjoint quotes."""
        if source_sha256 != self.source_sha256:
            raise ValueError("Passage references belong to a different source")
        if not isinstance(passage_ids, list) or not passage_ids:
            raise ValueError("At least one passage ID is required")
        if not all(isinstance(value, str) for value in passage_ids):
            raise ValueError("Passage IDs must be strings")
        if len(set(passage_ids)) != len(passage_ids):
            raise ValueError("Duplicate passage IDs are not allowed")
        by_id = {passage.passage_id: passage for passage in self.passages}
        if any(value not in by_id for value in passage_ids):
            raise ValueError("Unknown passage ID")
        return tuple(sorted((by_id[value] for value in passage_ids), key=lambda passage: passage.start))


def index_source_passages(source_text: str, *, max_chars: int = 1200) -> PassageDocument:
    """Partition text exactly, preferring line/word boundaries in each chunk.

    Offsets are Python Unicode character offsets, not UTF-8 byte offsets. The
    document hash binds the original UTF-8 bytes. IDs are stable for the same
    source and segmentation setting; each ID includes that setting so changing
    it cannot silently reinterpret a previously selected ID.
    """
    if not isinstance(source_text, str):
        raise TypeError("Source text must be a string")
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 2:
        raise ValueError("max_chars must be an integer of at least two")
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    passages = []
    start = 0
    while start < len(source_text):
        end = min(start + max_chars, len(source_text))
        if end < len(source_text):
            split = source_text.rfind("\n", start + max_chars // 2, end)
            if split < 0:
                split = source_text.rfind(" ", start + max_chars // 2, end)
            if split >= 0:
                end = split + 1
        passage_id = f"v1-{max_chars}-p{len(passages) + 1:04d}"
        passages.append(SourcePassage(passage_id, start, end, source_text[start:end]))
        start = end
    return PassageDocument(source_hash, tuple(passages))
