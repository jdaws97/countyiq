"""Trust boundaries for the offline source-range interface experiment."""

import hashlib
import json

import pytest

from eval.evidence_ranges import index_evidence_ranges


@pytest.mark.parametrize(
    "source",
    [
        "",
        "  ",
        "é🌳\r\nCouncil\n",
        "x" * 2501,
        "Review\n" * 300,
        "30-26-07-22-\no\n0134\n",
        "First\rSecond\u2028Third\n\n",
    ],
)
def test_view_preserves_all_original_characters_and_unicode_offsets(source):
    doc = index_evidence_ranges(source)
    assert doc.source_sha256 == hashlib.sha256(source.encode()).hexdigest()
    assert "".join(unit.text for unit in doc.units) == source
    assert all(unit.text == source[unit.start : unit.end] for unit in doc.units)
    assert all(0 < len(unit.text) <= 1200 for unit in doc.units)
    assert all(left.end == right.start for left, right in zip(doc.units, doc.units[1:]))
    assert index_evidence_ranges(source) == doc
    assert (
        "".join(unit["text"] for unit in json.loads(doc.model_input())["source_units"])
        == source
    )


def test_recovery_preserves_broken_identifier_instead_of_silently_repairing_it():
    source = "Ruhlman\n30-26-07-22-\no\n0134\nNext matter\n"
    doc = index_evidence_ranges(source)
    selected = doc.resolve(
        doc.source_sha256,
        first_id=doc.units[1].passage_id,
        last_id=doc.units[3].passage_id,
    )
    assert selected.text == "30-26-07-22-\no\n0134\n"
    assert selected.text == source[selected.start : selected.end]
    assert "30-26-07-22-0134" not in selected.text


def test_separated_item_and_vote_cannot_skip_intervening_action():
    source = "Motion to approve Plan A.\nMotion to deny Plan B.\nMotion carried: 6-0.\n"
    doc = index_evidence_ranges(source)
    selected = doc.resolve(
        doc.source_sha256,
        first_id=doc.units[0].passage_id,
        last_id=doc.units[-1].passage_id,
    )
    assert selected.text == source
    # Existing semantic rejection remains necessary after exact range recovery.
    from countyiq.lib.proceeding_semantics import decision_errors

    assert decision_errors(
        {"outcome": "approved", "scope": "plan", "authority": "Council"}, selected.text
    )


def test_same_unit_is_a_valid_continuous_range():
    doc = index_evidence_ranges("First\nSecond\n")
    unit = doc.units[1]
    selected = doc.resolve(
        doc.source_sha256, first_id=unit.passage_id, last_id=unit.passage_id
    )
    assert selected.text == "Second\n"


def test_unknown_reversed_source_and_version_references_fail():
    doc = index_evidence_ranges("First\nSecond\n")
    first, last = [unit.passage_id for unit in doc.units]
    for start, end, message in [
        ("unknown", last, "Unknown"),
        (first, "unknown", "Unknown"),
        (last, first, "reversed"),
        (None, last, "strings"),
        ("v1-1200-p0001", last, "Unknown"),
        (first.replace("1200", "2400"), last, "Unknown"),
    ]:
        with pytest.raises(ValueError, match=message):
            doc.resolve(doc.source_sha256, first_id=start, last_id=end)
    changed = index_evidence_ranges("First\nAltered\n")
    with pytest.raises(ValueError, match="different source"):
        changed.resolve(doc.source_sha256, first_id=first, last_id=last)


@pytest.mark.parametrize("limit", [0, 1, -1, True, 1.5])
def test_invalid_segmentation_fails(limit):
    with pytest.raises(ValueError):
        index_evidence_ranges("source", max_unit_chars=limit)
