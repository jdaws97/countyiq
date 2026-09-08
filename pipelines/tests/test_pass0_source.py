import hashlib

import pytest
from countyiq.lib.pass0_source import index_source


def test_unicode_hash_and_exact_reconstruction() -> None:
    text = "café 😀\n第二行\n"
    document = index_source(text)

    assert document.sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert "".join(unit.text for unit in document.units) == text
    assert document.resolve(1, len(document.units), document.sha256).text == text


def test_blank_and_crlf_lines_are_preserved_and_displayed_on_one_line() -> None:
    document = index_source("first\r\n\r\nlast")

    assert [unit.text for unit in document.units] == ["first\r\n", "\r\n", "last"]
    assert document.model_input() == "1\tfirst\\r\\n\n2\t\\r\\n\n3\tlast"


def test_long_lines_split_at_words_with_hard_limit() -> None:
    document = index_source("one two three four", max_unit_chars=8)

    assert [unit.text for unit in document.units] == ["one two ", "three ", "four"]
    assert all(len(unit.text) <= 8 for unit in document.units)


def test_resolution_rejects_bad_ids_ranges_and_hash() -> None:
    document = index_source("alpha\nbeta\ngamma")
    wrong_hash = "0" * 64

    with pytest.raises(ValueError):
        document.resolve(1, 1, wrong_hash)
    with pytest.raises(ValueError):
        document.resolve(True, 1, document.sha256)
    with pytest.raises(ValueError):
        document.resolve(2, 1, document.sha256)
    with pytest.raises(ValueError):
        document.resolve(1, 99, document.sha256)


def test_redundant_citations_preserve_exact_union_without_filling_gaps() -> None:
    document = index_source("alpha\nbeta\ngamma\ndelta\nepsilon")

    resolved = document.resolve_ranges(
        [(2, 3), (1, 2), (1, 1), (5, 5)], document.sha256
    )

    assert [span.text for span in resolved] == ["alpha\nbeta\ngamma\n", "epsilon"]
    assert all(document.text[span.start : span.end] == span.text for span in resolved)


def test_invalid_citation_is_not_hidden_by_a_valid_overlapping_citation() -> None:
    document = index_source("alpha\nbeta")

    with pytest.raises(ValueError, match="Invalid unit range"):
        document.resolve_ranges([(1, 2), (1, 3)], document.sha256)


def test_quote_anchors_preserve_unicode_offsets_and_trim_a_shared_line() -> None:
    text = "😀 WWI – no reply. Dough Boy – deposit\r\nwas\u00a0made.\n"
    document = index_source(text)

    excerpt = document.resolve_quote(
        "Dough Boy – deposit was made.", [(1, 2)], document.sha256
    )

    assert excerpt.text == "Dough Boy – deposit\r\nwas\u00a0made."
    assert text[excerpt.start : excerpt.end] == excerpt.text
    assert excerpt.start == text.index("Dough Boy")
    assert "WWI" not in excerpt.text


def test_quote_anchors_reject_ambiguous_including_overlapping_occurrences() -> None:
    document = index_source("a a a\nApproved.\nApproved.\n")

    for quote, ranges in (("a a", [(1, 1)]), ("Approved.", [(2, 3)])):
        with pytest.raises(ValueError, match="ambiguous"):
            document.resolve_quote(quote, ranges, document.sha256)
    assert document.resolve_quote("Approved.", [(3, 3)], document.sha256).number == 3


def test_quote_anchors_do_not_repair_text_or_cross_unprovided_gaps() -> None:
    document = index_source("110 Main Street\nUnrelated.\nApproved.\n")

    for quote, ranges in (
        ("10 Main Street", [(1, 1)]),
        ("110 Main Street Approved.", [(1, 1), (3, 3)]),
        ("Denied.", [(3, 3)]),
    ):
        with pytest.raises(ValueError, match="not literal"):
            document.resolve_quote(quote, ranges, document.sha256)
    with pytest.raises(ValueError, match="hash"):
        document.resolve_quote("Approved.", [(3, 3)], "0" * 64)


def test_quote_anchor_checks_word_boundary_outside_a_hard_split_unit() -> None:
    document = index_source("1110", max_unit_chars=2)

    with pytest.raises(ValueError, match="not literal"):
        document.resolve_quote("10", [(2, 2)], document.sha256)
    assert not document.contains_quote("10", (document.units[1],))


def test_literal_membership_allows_repetition_but_rejects_partial_identity() -> None:
    document = index_source("110 Main Street; 110 Main Street.\n")

    assert document.contains_quote("110 main STREET", document.units)
    assert not document.contains_quote("10 Main Street", document.units)
    assert not document.contains_quote("110 Main", document.units[:0])
    with pytest.raises(ValueError, match="ambiguous"):
        document.resolve_quote("110 Main Street", [(1, 1)], document.sha256)


def test_quote_anchor_accepts_adjacent_ranges_without_duplicate_matches() -> None:
    document = index_source("Kinsley\nConstruction\n")

    result = document.resolve_quote(
        "Kinsley Construction", [(1, 1), (1, 2), (2, 2)], document.sha256
    )

    assert result.text == "Kinsley\nConstruction"


def test_typographic_quotes_preserve_source_offsets_and_other_punctuation() -> None:
    text = "Address: Moore’s Mountain Road; “Lot-A”.\n"
    document = index_source(text)

    result = document.resolve_quote(
        'Moore\'s Mountain Road; "Lot-A"', [(1, 1)], document.sha256
    )

    assert result.text == "Moore’s Mountain Road; “Lot-A”"
    assert text[result.start : result.end] == result.text
    for changed in ("Moores Mountain Road", '"Lot A"', '"Lot–A"'):
        assert not document.contains_quote(changed, document.units)


def test_typographic_quote_equivalence_does_not_choose_ambiguous_occurrences() -> None:
    document = index_source("Moore's Mountain Road; Moore’s Mountain Road.\n")

    with pytest.raises(ValueError, match="ambiguous"):
        document.resolve_quote("Moore's Mountain Road", [(1, 1)], document.sha256)


def test_excerpt_anchors_recover_intervening_page_markers_and_broken_words() -> None:
    text = (
        "Payment to Kinsley\n1\n\nConstruction is approved.\n"
        "Contact a hydro-\nexcavating company and report back.\n"
    )
    document = index_source(text)

    payment = document.resolve_excerpt(
        "Payment to", "is approved.", 1, 4, document.sha256
    )
    investigation = document.resolve_excerpt(
        "Contact a", "report back.", 5, 6, document.sha256
    )

    assert payment.text == "Payment to Kinsley\n1\n\nConstruction is approved."
    assert investigation.text == "Contact a hydro-\nexcavating company and report back."
    for span in (payment, investigation):
        assert span.text == text[span.start : span.end]


def test_excerpt_anchors_require_the_named_endpoint_lines_and_order() -> None:
    document = index_source("Begin here.\nMotion carried.\nMotion carried.\n")

    with pytest.raises(ValueError, match="not literal"):
        document.resolve_excerpt(
            "Begin here.", "Motion carried.", 1, 1, document.sha256
        )
    with pytest.raises(ValueError, match="Invalid unit range"):
        document.resolve_excerpt(
            "Motion carried.", "Begin here.", 3, 1, document.sha256
        )
    assert (
        document.resolve_excerpt(
            "Begin here.", "Begin here.", 1, 1, document.sha256
        ).text
        == "Begin here."
    )
    assert (
        document.resolve_excerpt(
            "Begin here.", "Motion carried.", 1, 3, document.sha256
        ).text
        == document.text.rstrip()
    )


def test_anchor_case_variation_recovers_original_case_without_picking_a_match() -> None:
    document = index_source("A complaint was received.\nAlpha ALPHA\n")

    result = document.resolve_excerpt(
        "a complaint", "was received.", 1, 1, document.sha256
    )

    assert result.text == "A complaint was received."
    with pytest.raises(ValueError, match="ambiguous"):
        document.resolve_quote("alpha", [(2, 2)], document.sha256)


def test_endpoint_anchors_can_wrap_while_their_boundaries_stay_on_named_lines() -> None:
    text = (
        "The Applicants wish\n"
        "to build a garage. The motion carried.\n"
        "A separate motion was made. The motion\n"
        "carried.\n"
    )
    document = index_source(text)

    excerpt = document.resolve_excerpt(
        "The Applicants wish to build", "The motion carried.", 1, 4, document.sha256
    )

    assert excerpt.text == text.rstrip()
    assert text[excerpt.start : excerpt.end] == excerpt.text
    with pytest.raises(ValueError, match="not literal"):
        document.resolve_excerpt(
            "The Applicants wish to build", "The motion carried.", 1, 3, document.sha256
        )


def test_unique_excerpt_anchors_can_shrink_an_overbroad_cited_range() -> None:
    text = (
        "Engineer report:\n"
        "The report was circulated.\n"
        "Harbor Park needs repairs in spring.\n"
        "Next item:\n"
    )
    document = index_source(text)

    span = document.resolve_excerpt("Harbor Park", "in spring.", 1, 4, document.sha256)

    assert span.number == 3
    assert span.text == "Harbor Park needs repairs in spring."
    assert text[span.start : span.end] == span.text


@pytest.mark.parametrize(
    ("text", "start", "end", "first", "last"),
    [
        # An anchor outside the cited range cannot pull in neighboring evidence.
        ("Heading\nHarbor Park needs repairs.\n", "Harbor Park", "repairs.", 1, 1),
        # A second occurrence outside the range makes relocation ambiguous too.
        (
            "Heading\nHarbor Park needs repairs.\nOther item\nHarbor Park reopens.\n",
            "Harbor Park",
            "repairs.",
            1,
            2,
        ),
        # The unique anchors must still be in source order.
        ("Heading\nBegin here. End here.\n", "End here.", "Begin here.", 1, 2),
        # No spelling repair is permitted.
        ("Heading\nHarbor Park needs repairs.\n", "Harbour Park", "repairs.", 1, 2),
    ],
)
def test_excerpt_endpoint_correction_does_not_guess_or_expand(
    text, start, end, first, last
) -> None:
    document = index_source(text)

    with pytest.raises(ValueError):
        document.resolve_excerpt(start, end, first, last, document.sha256)
