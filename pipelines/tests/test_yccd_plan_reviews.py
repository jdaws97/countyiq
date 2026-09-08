from pathlib import Path

import pytest
from countyiq.lib.parsers.yccd_plan_reviews import (
    PlanReviewParseError,
    parse_plan_review_pdf,
)

PDF_PATH = Path(__file__).parent / "fixtures/yccd/plan-review-status-2026-08-31.pdf"


def word(text, x0, top):
    return {
        "text": text,
        "x0": x0,
        "x1": x0 + 20,
        "top": top,
        "bottom": top + 10,
    }


def test_parses_preserved_yccd_plan_review_pdf():
    result = parse_plan_review_pdf(PDF_PATH.read_bytes())

    assert result["document_date"] == "2026-08-31"
    assert len(result["rows"]) == 35

    first = result["rows"][0]
    assert first == {
        "plan_name": "Red Land High School Athletic Facility",
        "municipality_as_printed": "FAIRVIEW",
        "permit_number": "PAD670146",
        "administrative_date": "2026-07-17",
        "status": "in_review",
        "page": 1,
        "bbox": first["bbox"],
        "row_ordinal": 1,
    }
    assert first["bbox"] == {
        "x0": pytest.approx(8.52),
        "top": pytest.approx(110.8378),
        "x1": pytest.approx(578.67474),
        "bottom": pytest.approx(133.6378),
    }

    blank_permit = result["rows"][4]
    assert blank_permit["plan_name"] == "Pr. Residence 672 Wilt Drive"
    assert blank_permit["permit_number"] is None
    assert blank_permit["administrative_date"] == "2026-07-30"

    page_transition = result["rows"][28]
    assert page_transition["page"] == 2
    assert page_transition["row_ordinal"] == 29
    assert (
        page_transition["plan_name"]
        == "Pr S/W Management Improvements for Sand Bank Hill LLC"
    )

    final_row = result["rows"][-1]
    assert (
        final_row["plan_name"]
        == "SR 2005-004 Camp Betty Washington Rd Safety Improvements"
    )
    assert final_row["permit_number"] == "PAD670147"


@pytest.mark.parametrize("content", [b"", b"this is not a PDF"])
def test_rejects_invalid_pdf_bytes(content):
    with pytest.raises(PlanReviewParseError):
        parse_plan_review_pdf(content)


def test_rejects_unexpected_status(monkeypatch):
    class FakePage:
        def extract_words(self, **_kwargs):
            return [
                word("Plan", 224, 15),
                word("Status", 252, 15),
                word("as", 292, 15),
                word("of", 308, 15),
                word("8-31-26", 323, 15),
                word("Approved", 8, 120),
                word("Example", 86, 120),
                word("YORK", 255, 120),
                word("PAC670001", 395, 120),
                word("8/31/2026", 533, 120),
            ]

    class FakePdf:
        def __init__(self):
            self.pages = [FakePage()]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        "countyiq.lib.parsers.yccd_plan_reviews.pdfplumber.open",
        lambda _content: FakePdf(),
    )

    with pytest.raises(PlanReviewParseError, match="unexpected status"):
        parse_plan_review_pdf(b"fake")


def test_rejects_invalid_row_date(monkeypatch):
    class FakePage:
        def extract_words(self, **_kwargs):
            return [
                word("Plan", 224, 15),
                word("Status", 252, 15),
                word("as", 292, 15),
                word("of", 308, 15),
                word("8-31-26", 323, 15),
                word("In", 8, 120),
                word("Review", 20, 120),
                word("Example", 86, 120),
                word("YORK", 255, 120),
                word("PAC670001", 395, 120),
                word("not-a-date", 533, 120),
            ]

    class FakePdf:
        def __init__(self):
            self.pages = [FakePage()]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        "countyiq.lib.parsers.yccd_plan_reviews.pdfplumber.open",
        lambda _content: FakePdf(),
    )

    with pytest.raises(PlanReviewParseError, match="invalid row date"):
        parse_plan_review_pdf(b"fake")


def test_rejects_missing_document_date(monkeypatch):
    _install_fake_pdf(monkeypatch, _review_row_words())

    with pytest.raises(PlanReviewParseError, match="one document date"):
        parse_plan_review_pdf(b"fake")


def test_rejects_conflicting_document_dates(monkeypatch):
    _install_fake_pdf(
        monkeypatch,
        [*_document_date_words("8-31-26"), *_review_row_words()],
        [*_document_date_words("9-1-26"), *_review_row_words()],
    )

    with pytest.raises(PlanReviewParseError, match="document dates conflict"):
        parse_plan_review_pdf(b"fake")


def test_rejects_invalid_required_row_fields(monkeypatch):
    cases = [
        (_review_row_words(include_municipality=False), "missing municipality"),
        (_review_row_words(permit="invalid"), "invalid permit number"),
        (
            _review_row_words(administrative_date="9/1/2026"),
            "administrative date after document date",
        ),
    ]

    for row_words, error in cases:
        _install_fake_pdf(
            monkeypatch,
            [*_document_date_words("8-31-26"), *row_words],
        )

        with pytest.raises(PlanReviewParseError, match=error):
            parse_plan_review_pdf(b"fake")


def _install_fake_pdf(monkeypatch, *pages):
    class FakePage:
        def __init__(self, words):
            self.words = words

        def extract_words(self, **_kwargs):
            return self.words

    class FakePdf:
        def __init__(self):
            self.pages = [FakePage(page) for page in pages]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        "countyiq.lib.parsers.yccd_plan_reviews.pdfplumber.open",
        lambda _content: FakePdf(),
    )


def _document_date_words(value):
    return [
        word("Plan", 224, 15),
        word("Status", 252, 15),
        word("as", 292, 15),
        word("of", 308, 15),
        word(value, 323, 15),
    ]


def _review_row_words(
    *, include_municipality=True, permit="PAC670001", administrative_date="8/31/2026"
):
    words = [
        word("In", 8, 120),
        word("Review", 20, 120),
        word("Example", 86, 120),
        word(permit, 395, 120),
        word(administrative_date, 533, 120),
    ]
    if include_municipality:
        words.append(word("YORK", 255, 120))
    return words
