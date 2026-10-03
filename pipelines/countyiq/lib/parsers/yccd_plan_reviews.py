"""Parse York County Conservation District plan-review status PDFs.

The report is a fixed-position document rather than a tagged table.  This
parser intentionally validates that layout and raises when the report changes,
instead of trying to infer records from a different document.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable
from datetime import date
from io import BytesIO

import pdfplumber

DOCUMENT_DATE_PATTERN = re.compile(r"^Plan Status as of (\d{1,2}-\d{1,2}-\d{2})$")
ROW_DATE_PATTERN = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
PERMIT_NUMBER_PATTERN = re.compile(r"^(?:PAC|PAD)\d{6}(?:A-1)?$")

STATUS_MAX_X = 70
PLAN_X_RANGE = (80, 250)
MUNICIPALITY_X_RANGE = (250, 370)
PERMIT_X_RANGE = (390, 480)
DATE_MIN_X = 500


class PlanReviewParseError(ValueError):
    """Raised when a PDF does not match the expected YCCD report format."""


def parse_plan_review_pdf(content: bytes) -> dict:
    """Return the document date and in-review rows from a YCCD PDF.

    Coordinates in each ``bbox`` are PDF points in ``x0, top, x1, bottom``
    order.  Plan names are joined with one space where the printed report wraps
    them across lines.
    """
    if not isinstance(content, bytes) or not content:
        raise PlanReviewParseError("expected non-empty PDF bytes")

    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            if not pdf.pages:
                raise PlanReviewParseError("PDF has no pages")

            document_dates = []
            rows = []
            for page_number, page in enumerate(pdf.pages, start=1):
                lines = _group_lines(page.extract_words(x_tolerance=1, y_tolerance=3))
                page_document_dates = _document_dates(lines)
                if len(page_document_dates) != 1:
                    raise PlanReviewParseError(
                        f"expected one document date on page {page_number}"
                    )
                document_dates.extend(page_document_dates)
                rows.extend(
                    _parse_page(
                        lines,
                        page_number,
                        len(rows),
                        page_document_dates[0],
                    )
                )
    except PlanReviewParseError:
        raise
    except Exception as exc:
        raise PlanReviewParseError("could not read plan-review PDF") from exc

    if not document_dates:
        raise PlanReviewParseError("document date is missing")
    if len(set(document_dates)) != 1:
        raise PlanReviewParseError("document dates conflict across pages")
    if not rows:
        raise PlanReviewParseError("PDF contains no plan-review rows")

    return {"document_date": document_dates[0], "rows": rows}


def _group_lines(words: list[dict]) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
        if lines and abs(lines[-1][0]["top"] - word["top"]) < 1:
            lines[-1].append(word)
        else:
            lines.append([word])
    return lines


def _document_dates(lines: Iterable[list[dict]]) -> list[str]:
    dates = []
    for line in lines:
        text = _line_text(line)
        match = DOCUMENT_DATE_PATTERN.fullmatch(text)
        if match:
            dates.append(_iso_date(match.group(1), "%m-%d-%y", "document"))
    return dates


def _parse_page(
    lines: list[list[dict]],
    page_number: int,
    ordinal_start: int,
    document_date: str,
) -> list[dict]:
    rows = []
    plan_lines: list[list[dict]] = []
    saw_status = False

    for line in lines:
        if DOCUMENT_DATE_PATTERN.fullmatch(_line_text(line)):
            continue
        status_words = [word for word in line if word["x0"] < STATUS_MAX_X]
        plan_words = _words_in_range(line, *PLAN_X_RANGE)

        if status_words:
            status = _line_text(status_words)
            if status != "In Review":
                raise PlanReviewParseError(
                    f"unexpected status {status!r} on page {page_number}"
                )
            saw_status = True
            if not plan_words:
                raise PlanReviewParseError(
                    f"missing plan name on page {page_number} at {line[0]['top']:.1f}"
                )
            row_plan_lines = [*plan_lines, plan_words]
            rows.append(
                _build_row(
                    line,
                    row_plan_lines,
                    page_number,
                    ordinal_start + len(rows) + 1,
                    document_date,
                )
            )
            plan_lines = []
            continue

        if plan_words:
            plan_text = _line_text(plan_words)
            if plan_text != "Plan Name":
                plan_lines.append(plan_words)

    if plan_lines:
        raise PlanReviewParseError(f"unfinished plan name on page {page_number}")
    if not saw_status:
        raise PlanReviewParseError(f"no in-review rows found on page {page_number}")
    return rows


def _build_row(
    status_line: list[dict],
    plan_lines: list[list[dict]],
    page_number: int,
    row_ordinal: int,
    document_date: str,
) -> dict:
    municipality_words = _words_in_range(status_line, *MUNICIPALITY_X_RANGE)
    permit_words = _words_in_range(status_line, *PERMIT_X_RANGE)
    date_words = [word for word in status_line if word["x0"] >= DATE_MIN_X]

    if not municipality_words:
        raise PlanReviewParseError(f"missing municipality for row {row_ordinal}")
    if len(date_words) != 1 or not ROW_DATE_PATTERN.fullmatch(date_words[0]["text"]):
        raise PlanReviewParseError(f"invalid row date for row {row_ordinal}")
    if len(permit_words) > 1:
        raise PlanReviewParseError(f"ambiguous permit number for row {row_ordinal}")

    permit_number = _line_text(permit_words) if permit_words else None
    if permit_number and not PERMIT_NUMBER_PATTERN.fullmatch(permit_number):
        raise PlanReviewParseError(f"invalid permit number for row {row_ordinal}")

    administrative_date = _iso_date(date_words[0]["text"], "%m/%d/%Y", "row")
    if administrative_date > document_date:
        raise PlanReviewParseError(
            f"administrative date after document date for row {row_ordinal}"
        )

    all_row_words = [word for plan_line in plan_lines for word in plan_line]
    all_row_words.extend(status_line)
    return {
        "plan_name": " ".join(_line_text(line) for line in plan_lines),
        "municipality_as_printed": _line_text(municipality_words),
        "permit_number": permit_number,
        "administrative_date": administrative_date,
        "status": "in_review",
        "page": page_number,
        "bbox": {
            "x0": min(word["x0"] for word in all_row_words),
            "top": min(word["top"] for word in all_row_words),
            "x1": max(word["x1"] for word in all_row_words),
            "bottom": max(word["bottom"] for word in all_row_words),
        },
        "row_ordinal": row_ordinal,
    }


def _words_in_range(
    words: Iterable[dict], minimum: float, maximum: float
) -> list[dict]:
    return [word for word in words if minimum <= word["x0"] < maximum]


def _line_text(words: Iterable[dict]) -> str:
    return " ".join(word["text"] for word in sorted(words, key=lambda item: item["x0"]))


def _iso_date(value: str, format_string: str, label: str) -> str:
    try:
        parsed = time.strptime(value, format_string)
        return date(parsed.tm_year, parsed.tm_mon, parsed.tm_mday).isoformat()
    except ValueError as exc:
        raise PlanReviewParseError(f"invalid {label} date {value!r}") from exc
