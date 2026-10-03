"""The final physical page must survive bounded PDF extraction."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from countyiq.assets.bulk import tax_claims


@pytest.mark.parametrize("page_count", [1, 20, 21, 40, 41])
def test_every_physical_page_is_extracted_once(monkeypatch, tmp_path, page_count):
    physical_pages = [
        SimpleNamespace(
            page_number=number,
            extract_text=Mock(return_value=f"physical page {number}"),
        )
        for number in range(1, page_count + 1)
    ]

    @contextmanager
    def open_pdf(path, pages=None):
        # pdfplumber's external contract is one-based, including its filter.
        selected = [
            page
            for page in physical_pages
            if pages is None or page.page_number in pages
        ]
        yield SimpleNamespace(pages=selected)

    monkeypatch.setattr(tax_claims.pdfplumber, "open", open_pdf)
    output_path = tmp_path / "extracted.txt"
    tax_claims._extract_pdf_text(
        "listing.pdf", str(output_path), SimpleNamespace(log=Mock())
    )

    assert output_path.read_text().splitlines() == [
        f"physical page {number}" for number in range(1, page_count + 1)
    ]
    for page in physical_pages:
        page.extract_text.assert_called_once_with()
