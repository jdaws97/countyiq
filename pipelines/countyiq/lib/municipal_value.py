"""Conservative, free filtering of administrative municipal source sections.

This gate removes recognizable accounting tables, not documents merely lacking
a keyword. Narrative decisions, including funding and contract awards, remain.
Original line numbers and bytes are retained for downstream evidence binding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from countyiq.lib.pass0_source import SourceDocument

VALUE_POLICY_VERSION = "property-project-value-v1"

_ACCOUNTING_HEADER = re.compile(
    r"expenses\s+by\s+vendor\s+detail|bills\s+list|"
    r"(?:check|payroll)\s+register|cash\s+disbursements|"
    r"accounts\s+payable\s+(?:report|register)",
    re.IGNORECASE,
)
_COLUMNS = re.compile(
    r"(?:name|vendor|date|payee).*(?:account|amount|paid|balance)",
    re.IGNORECASE,
)
_NARRATIVE_SECTION = re.compile(
    r"^\s*(?:\d+[.)]\s*)?(?:"
    r"(?:township|borough)\s+manager[’']?s?\s+report|"
    r"(?:public\s+works|engineer[’']?s?|solicitor[’']?s?)\s+report|"
    r"(?:new|old|unfinished)\s+business|planning\s*(?:&|and)\s*development|"
    r"MS4\s+monthly\s+report|zoning\s+violation\s+letters|"
    r"subdivision\s*/\s*land\s+development\s+plans"
    r")(?:\s*[:—–-].*)?\s*$",
    re.IGNORECASE,
)
_NARRATIVE_CUE = re.compile(
    r"\b(?:motion\s+(?:to|was)|moved\s+to|seconded|public\s+hearing|"
    r"plan\s+approval|request\s+for|proposed\s+(?:project|ordinance))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceValue:
    excluded_lines: frozenset[int]
    excluded_sections: tuple[tuple[int, int], ...]
    skip_reason: str | None


def source_value(document: SourceDocument) -> SourceValue:
    """Keep uncertain documents for semantic reading; skip only clear controls."""
    sections = []
    start = None
    units = document.units
    for index, unit in enumerate(units):
        line = unit.text.strip()
        if start is not None and (
            _NARRATIVE_SECTION.fullmatch(line) or _NARRATIVE_CUE.search(line)
        ):
            sections.append((start, unit.number - 1))
            start = None
        if start is not None or not _ACCOUNTING_HEADER.search(line):
            continue
        # "Approve the bills list" is a narrative agenda item, not a table.
        if re.search(r"\b(?:motion|approve|authorize|review)\b", line, re.IGNORECASE):
            continue
        following = " ".join(item.text for item in units[index : index + 20])
        amounts = re.findall(r"\b\d[\d,]*\.\d{2}\b", following)
        if _COLUMNS.search(following) or len(amounts) >= 3:
            start = unit.number
    if start is not None:
        sections.append((start, len(units)))
    excluded = frozenset(
        number for first, last in sections for number in range(first, last + 1)
    )
    retained = "".join(unit.text for unit in units if unit.number not in excluded)
    reason = None
    has_substantive_text = re.search(
        r"\b(?:plan|subdivision|zoning|variance|permit|project|bid|award|"
        r"property|road|street|building|sewer|grant)\b",
        retained,
        re.IGNORECASE,
    )
    if excluded and len(retained.strip()) < 300 and not has_substantive_text:
        reason = "accounting_table_only"
    elif len(document.text.strip()) < 200 and (
        re.search(
            r"\bmeeting\s+(?:(?:has been|is)\s+)?cancel(?:led|ed)\b\s*[.!]*$",
            document.text.strip(),
            re.IGNORECASE,
        )
        or document.text.strip().lower() in {"cancelled", "canceled"}
        or (
            re.search(r"\b(?:board|commission|council)\b", document.text, re.IGNORECASE)
            and re.search(r"\bcancel(?:led|ed)\s*$", document.text, re.IGNORECASE)
            and not re.search(
                r"\b(?:permit|application|variance|property|street|road)\b",
                document.text,
                re.IGNORECASE,
            )
        )
    ):
        reason = "cancelled_meeting_notice"
    return SourceValue(excluded, tuple(sections), reason)
