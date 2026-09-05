import hashlib
import pytest
from countyiq.lib.source_passages import index_source_passages


@pytest.mark.parametrize("source", ["", "  ", "é🌳\r\nPlanning commission\n", "x" * 2501,
                                      "A decision.\n" * 300, "parcel 123 " * 400])
def test_passages_preserve_exact_source_and_offsets(source):
    document = index_source_passages(source)
    assert document.source_sha256 == hashlib.sha256(source.encode()).hexdigest()
    assert "".join(p.text for p in document.passages) == source
    assert all(0 < len(p.text) <= 1200 and p.text == source[p.start:p.end] for p in document.passages)
    assert all(left.end == right.start for left, right in zip(document.passages, document.passages[1:]))
    assert document == index_source_passages(source)


def test_reference_cannot_silently_change_source_or_segmentation():
    first = index_source_passages("Same document but several words", max_chars=12)
    changed = index_source_passages("Changed document but several words", max_chars=12)
    with pytest.raises(ValueError, match="different source"):
        changed.resolve(first.source_sha256, [first.passages[0].passage_id])
    resized = index_source_passages("Same document but several words", max_chars=20)
    with pytest.raises(ValueError, match="Unknown passage"):
        resized.resolve(first.source_sha256, [first.passages[0].passage_id])


@pytest.mark.parametrize("ids", [[], [None], [1], ["unknown"], "v1-1200-p0001",
                                ["v1-1200-p0001", "v1-1200-p0001"]])
def test_invalid_references_are_rejected(ids):
    document = index_source_passages("Recorded source text")
    with pytest.raises(ValueError):
        document.resolve(document.source_sha256, ids)


def test_disjoint_passages_remain_separate_and_in_source_order():
    document = index_source_passages("a" * 3600)
    first, _, last = document.passages
    resolved = document.resolve(document.source_sha256, [last.passage_id, first.passage_id])
    assert resolved == (first, last)
    assert len(resolved) == 2


@pytest.mark.parametrize("limit", [0, 1, -1, True, 1.5])
def test_invalid_segmentation_limits_fail(limit):
    with pytest.raises(ValueError):
        index_source_passages("source", max_chars=limit)
