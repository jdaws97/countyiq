"""Local PDF preparation for Pass 0, including scanned and mixed text pages."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pdfplumber

MAX_BYTES = 8 * 1024 * 1024
MAX_PAGES = 500


@dataclass(frozen=True)
class PageSpan:
    page: int
    start: int
    end: int


@dataclass(frozen=True)
class PdfSource:
    text: str
    pages: tuple[PageSpan, ...]
    document_sha256: str
    parser: str

    def provenance(self) -> dict:
        return {
            "document_sha256": self.document_sha256,
            "text_sha256": hashlib.sha256(self.text.encode()).hexdigest(),
            "parser": self.parser,
            "pages": [asdict(page) for page in self.pages],
        }


def _ocr_pages(pdf_bytes: bytes, page_count: int) -> list[str]:
    runtime_project = Path(__file__).resolve().parents[2] / "ocr"
    executable = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    runtime = runtime_project / ".venv" / executable
    if not runtime.is_file():
        raise RuntimeError(
            "Scanned PDF requires the locked OCR runtime: "
            "uv sync --project pipelines/ocr --locked"
        )
    try:
        completed = subprocess.run(
            [
                str(runtime),
                str(runtime_project / "convert_pdf.py"),
                "--expected-pages",
                str(page_count),
            ],
            input=pdf_bytes,
            capture_output=True,
            timeout=210,
            check=True,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("PDF OCR exceeded its preparation deadline") from error
    except subprocess.CalledProcessError as error:
        raise ValueError("PDF OCR did not complete successfully") from error
    result = json.loads(completed.stdout)
    if not isinstance(result, dict):
        raise TypeError("OCR returned an invalid result envelope")
    if result.get("document_sha256") != hashlib.sha256(pdf_bytes).hexdigest():
        raise ValueError("OCR result belongs to a different PDF")
    pages = result.get("pages")
    if (
        not isinstance(pages, list)
        or len(pages) != page_count
        or any(not isinstance(page, str) for page in pages)
    ):
        raise ValueError("OCR result did not preserve every source page")
    return pages


def read_pdf_source(pdf_bytes: bytes, *, force_layout: bool = False) -> PdfSource:
    """Keep native text unless a raster page is unreadable; never accept partial OCR.

    Page spans refer to the returned text. The PDF hash identifies the original
    bytes, independently of which reader produced the text.
    """
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("Source is not a PDF")
    if len(pdf_bytes) > MAX_BYTES:
        raise ValueError("PDF exceeds the Pass 0 byte limit")
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as document:
        if not document.pages or len(document.pages) > MAX_PAGES:
            raise ValueError("PDF exceeds the Pass 0 page limit or has no pages")
        pages = [(page.extract_text() or "").strip() for page in document.pages]
        unreadable = {
            index
            for index, page in enumerate(document.pages)
            if page.images and len(pages[index]) < 40
        }
    parser = "pdfplumber"
    if force_layout or unreadable:
        pages = _ocr_pages(pdf_bytes, len(pages))
        if any(not pages[index].strip() for index in unreadable):
            raise ValueError("OCR left a raster source page unreadable")
        parser = "docling-rapidocr"
    if not any(page.strip() for page in pages):
        raise ValueError("PDF has no readable text")
    spans = []
    offset = 0
    for number, page in enumerate(pages, start=1):
        spans.append(PageSpan(number, offset, offset + len(page)))
        offset += len(page) + 2
    return PdfSource(
        text="\n\n".join(pages),
        pages=tuple(spans),
        document_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        parser=parser,
    )
