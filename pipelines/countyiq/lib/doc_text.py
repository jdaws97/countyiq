"""Extract machine-readable text from supported municipal documents.

PDF extraction uses pdfplumber. A .docx file is a zip archive whose main
content lives in word/document.xml; regex over its simple paragraph/text-run
structure keeps Word extraction dependency-free.

Legacy binary .doc files are not zip archives; extraction fails soft and
returns "" (callers archive the raw bytes and move on without text).
"""

import html
import io
import os
import re
import zipfile

import pdfplumber

_PARAGRAPH_RE = re.compile(r"<w:p[ >].*?</w:p>|<w:p/>", re.DOTALL)
_TEXT_RUN_RE = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.DOTALL)
_DEFAULT_PDF_TEXT_MAX_BYTES = 8 * 1024 * 1024
_DEFAULT_PDF_TEXT_MAX_PAGES = 500


def _positive_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Return non-empty PDF page text separated by blank lines.

    PDF content streams can expand to many times the download size while
    pdfplumber parses them.  Bound both the compressed input and page count so
    an unusually large plan set cannot exhaust a worker's memory.  The raw
    document remains archived even when text extraction is deliberately
    skipped by callers.
    """
    if not pdf_bytes:
        return ""

    max_bytes = _positive_int_env(
        "COUNTYIQ_PDF_TEXT_MAX_BYTES", _DEFAULT_PDF_TEXT_MAX_BYTES
    )
    if len(pdf_bytes) > max_bytes:
        raise ValueError(
            "PDF exceeds local text-extraction byte limit: "
            f"{len(pdf_bytes)} > {max_bytes}"
        )

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        max_pages = _positive_int_env(
            "COUNTYIQ_PDF_TEXT_MAX_PAGES", _DEFAULT_PDF_TEXT_MAX_PAGES
        )
        if len(pdf.pages) > max_pages:
            raise ValueError(
                "PDF exceeds local text-extraction page limit: "
                f"{len(pdf.pages)} > {max_pages}"
            )
        for page in pdf.pages:
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def extract_text_from_docx_bytes(docx_bytes: bytes) -> str:
    """Return the plain text of a .docx file, one line per paragraph.

    Returns "" for anything that isn't a readable .docx (legacy .doc,
    corrupt downloads, zips without word/document.xml).
    """
    if not docx_bytes:
        return ""
    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError, OSError):
        return ""

    paragraphs = []
    for para_xml in _PARAGRAPH_RE.findall(xml):
        runs = _TEXT_RUN_RE.findall(para_xml)
        text = html.unescape("".join(runs)).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)
