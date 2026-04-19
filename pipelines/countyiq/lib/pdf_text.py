"""Helpers for extracting machine-readable text from PDF bytes."""

from __future__ import annotations

from io import BytesIO

import pdfplumber


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Return concatenated text extracted from a PDF.

    The result is intended for prompt injection into local text models when a
    native PDF-capable backend is not available.
    """
    if not pdf_bytes:
        return ""

    pages: list[str] = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(text)

    return "\n\n".join(pages)
