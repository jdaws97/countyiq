"""Extract machine-readable text from supported municipal documents.

PDF extraction uses pdfplumber. A .docx file is a zip archive whose main
content lives in word/document.xml; regex over its simple paragraph/text-run
structure keeps Word extraction dependency-free.

Legacy binary .doc files are not zip archives; extraction fails soft and
returns "" (callers archive the raw bytes and move on without text).
"""

import html
import io
import re
import zipfile

import pdfplumber

_PARAGRAPH_RE = re.compile(r"<w:p[ >].*?</w:p>|<w:p/>", re.DOTALL)
_TEXT_RUN_RE = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.DOTALL)


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Return non-empty PDF page text separated by blank lines."""
    if not pdf_bytes:
        return ""

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
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
