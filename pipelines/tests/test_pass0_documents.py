from types import SimpleNamespace

import pytest
from countyiq.lib.pass0_documents import read_pdf_source


def pdf_pages(monkeypatch, contents):
    class Document:
        def __init__(self):
            self.pages = [
                SimpleNamespace(extract_text=lambda text=text: text, images=images)
                for text, images in contents
            ]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(
        "countyiq.lib.pass0_documents.pdfplumber.open", lambda _: Document()
    )


def test_mixed_pdf_runs_ocr_and_preserves_page_offsets(monkeypatch):
    pdf_pages(monkeypatch, [("Readable native text. " * 4, []), ("", [object()])])
    calls = []

    def ocr(data, count):
        calls.append(count)
        return ["Page one", "Scanned planning application on page two"]

    monkeypatch.setattr("countyiq.lib.pass0_documents._ocr_pages", ocr)
    result = read_pdf_source(b"%PDF-original")

    assert calls == [2]
    assert result.parser == "docling-rapidocr"
    assert result.text[result.pages[1].start : result.pages[1].end].startswith(
        "Scanned"
    )
    assert result.provenance()["pages"][1]["page"] == 2


def test_unreadable_ocr_page_cannot_be_reported_as_complete(monkeypatch):
    pdf_pages(monkeypatch, [("", [object()])])
    monkeypatch.setattr("countyiq.lib.pass0_documents._ocr_pages", lambda *_: [""])
    with pytest.raises(ValueError, match="unreadable"):
        read_pdf_source(b"%PDF-original")


def test_native_text_does_not_load_ocr_models(monkeypatch):
    text = "A complete native-text planning document. " * 4
    pdf_pages(monkeypatch, [(text, [])])

    def unexpected(*args):
        pytest.fail("Native text should not initialize the OCR model")

    monkeypatch.setattr("countyiq.lib.pass0_documents._ocr_pages", unexpected)
    result = read_pdf_source(b"%PDF-original")
    assert result.text == text.strip()
    assert result.parser == "pdfplumber"


@pytest.mark.parametrize("invalid", ["wrong_hash", "missing_page", "invalid_page"])
def test_isolated_ocr_cannot_return_other_bytes_or_partial_pages(monkeypatch, invalid):
    import hashlib
    import json

    from countyiq.lib.pass0_documents import _ocr_pages

    pdf = b"%PDF-original"
    result = {
        "document_sha256": hashlib.sha256(pdf).hexdigest(),
        "pages": ["Page one", "Page two"],
    }
    if invalid == "wrong_hash":
        result["document_sha256"] = "0" * 64
    elif invalid == "missing_page":
        result["pages"].pop()
    else:
        result["pages"][1] = None
    monkeypatch.setattr("pathlib.Path.is_file", lambda _: True)

    def run(command, **kwargs):
        assert kwargs["input"] == pdf
        assert kwargs["timeout"] == 210
        return SimpleNamespace(stdout=json.dumps(result).encode())

    monkeypatch.setattr("countyiq.lib.pass0_documents.subprocess.run", run)
    with pytest.raises(ValueError):
        _ocr_pages(pdf, 2)
