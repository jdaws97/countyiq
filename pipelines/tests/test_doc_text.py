"""Unit tests for supported municipal-document text extraction."""

import io
import zipfile

from countyiq.lib.doc_text import (
    extract_text_from_docx_bytes,
    extract_text_from_pdf_bytes,
)

_DOCX_XML_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
    '2006/main"><w:body>{body}</w:body></w:document>'
)


def _make_docx(paragraphs: list[list[str]]) -> bytes:
    """Build a minimal .docx: each inner list is one paragraph's text runs."""
    body = "".join(
        "<w:p>" + "".join(f"<w:r><w:t>{run}</w:t></w:r>" for run in runs) + "</w:p>"
        for runs in paragraphs
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", _DOCX_XML_TEMPLATE.format(body=body))
    return buf.getvalue()


class TestExtractTextFromDocxBytes:
    def test_single_paragraph(self):
        docx = _make_docx([["Meeting called to order at 7:00 PM."]])
        assert (
            extract_text_from_docx_bytes(docx) == "Meeting called to order at 7:00 PM."
        )

    def test_multiple_paragraphs_joined_with_newlines(self):
        docx = _make_docx([["Call to order."], ["Roll call: all present."]])
        assert extract_text_from_docx_bytes(docx) == (
            "Call to order.\nRoll call: all present."
        )

    def test_runs_within_a_paragraph_concatenated(self):
        docx = _make_docx([["Motion by ", "Smith", " to approve."]])
        assert extract_text_from_docx_bytes(docx) == "Motion by Smith to approve."

    def test_xml_entities_unescaped(self):
        docx = _make_docx([["Smith &amp; Jones &lt;LLC&gt;"]])
        assert extract_text_from_docx_bytes(docx) == "Smith & Jones <LLC>"

    def test_empty_paragraphs_dropped(self):
        docx = _make_docx([["First."], [], ["Second."]])
        assert extract_text_from_docx_bytes(docx) == "First.\nSecond."

    def test_not_a_zip_returns_empty(self):
        """Legacy binary .doc (or corrupt bytes) must fail soft, not raise."""
        assert extract_text_from_docx_bytes(b"\xd0\xcf\x11\xe0 not a zip") == ""

    def test_zip_without_document_xml_returns_empty(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("something/else.txt", "hi")
        assert extract_text_from_docx_bytes(buf.getvalue()) == ""

    def test_empty_bytes_return_empty(self):
        assert extract_text_from_docx_bytes(b"") == ""


class TestExtractTextFromPdfBytes:
    def test_oversized_pdf_skips_parser(self, monkeypatch):
        monkeypatch.setenv("COUNTYIQ_PDF_TEXT_MAX_BYTES", "4")

        def fail_if_called(_stream):
            raise AssertionError("pdfplumber should not be called")

        monkeypatch.setattr("countyiq.lib.doc_text.pdfplumber.open", fail_if_called)

        try:
            extract_text_from_pdf_bytes(b"12345")
        except ValueError as exc:
            assert "byte limit" in str(exc)
        else:
            raise AssertionError("oversized PDFs must be rejected")

    def test_non_empty_pages_joined_with_blank_lines(self, monkeypatch):
        class FakePage:
            def __init__(self, text):
                self.text = text

            def extract_text(self):
                return self.text

        class FakePdf:
            pages = [
                FakePage(" First page. "),
                FakePage(None),
                FakePage("Second page."),
            ]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        def fake_open(stream):
            assert stream.read() == b"pdf bytes"
            return FakePdf()

        monkeypatch.setattr("countyiq.lib.doc_text.pdfplumber.open", fake_open)

        assert extract_text_from_pdf_bytes(b"pdf bytes") == (
            "First page.\n\nSecond page."
        )

    def test_excess_page_count_skips_page_extraction(self, monkeypatch):
        monkeypatch.setenv("COUNTYIQ_PDF_TEXT_MAX_PAGES", "1")

        class FakePage:
            def extract_text(self):
                raise AssertionError("pages should not be extracted")

        class FakePdf:
            pages = [FakePage(), FakePage()]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        monkeypatch.setattr(
            "countyiq.lib.doc_text.pdfplumber.open", lambda _stream: FakePdf()
        )

        try:
            extract_text_from_pdf_bytes(b"pdf bytes")
        except ValueError as exc:
            assert "page limit" in str(exc)
        else:
            raise AssertionError("over-page-limit PDFs must be rejected")

    def test_empty_bytes_skip_pdf_parser(self, monkeypatch):
        def fail_if_called(_stream):
            raise AssertionError("pdfplumber should not be called")

        monkeypatch.setattr("countyiq.lib.doc_text.pdfplumber.open", fail_if_called)
        assert extract_text_from_pdf_bytes(b"") == ""
