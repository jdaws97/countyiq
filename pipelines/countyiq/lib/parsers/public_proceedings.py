"""Parser for municipality public proceedings (meeting minutes) pages.

Extracts PDF links from HTML meeting minutes pages and classifies them
by proceeding type (board of supervisors, planning commission, etc.).

All functions are pure — HTML / filename string in, structured dicts out.
"""

import re
from urllib.parse import urljoin, urlparse

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

# Patterns tried in order inside parse_meeting_date_from_filename.
# Each tuple: (compiled_regex, handler_fn(match) -> "YYYY-MM-DD")
_DATE_PATTERNS: list[tuple[re.Pattern, object]] = []


def _register(pattern: str):
    """Decorator that registers a date-extraction handler."""
    def decorator(fn):
        _DATE_PATTERNS.append((re.compile(pattern, re.IGNORECASE), fn))
        return fn
    return decorator


# YYYY-MM-DD  or  YYYY_MM_DD
@_register(r"(?<!\d)(\d{4})[-_](\d{2})[-_](\d{2})(?!\d)")
def _ymd(m: re.Match) -> str:
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


# MM-DD-YYYY  or  MM_DD_YYYY
@_register(r"(?<!\d)(\d{2})[-_](\d{2})[-_](\d{4})(?!\d)")
def _mdy(m: re.Match) -> str:
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"


# "Month Day, Year" or "Month Dayth, Year" — e.g. "January 5, 2026", "March 9th, 2026"
@_register(
    r"(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,?\s+|\s+)(\d{4})"
)
def _month_day_year(m: re.Match) -> str:
    month_num = _MONTH_MAP[m.group(1).lower()]
    day = m.group(2).zfill(2)
    return f"{m.group(3)}-{month_num}-{day}"


# Month_YYYY  or  Month-YYYY  (e.g. "March_2025", "November-2024")
# Note: we avoid (?<!\w) because underscore is a \w char and filenames use
# underscores as separators.  We only require the month not be preceded by
# another letter (to avoid matching "march" inside "marching" etc.).
@_register(
    r"(?<![A-Za-z])(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)[-_ ](\d{4})(?!\d)"
)
def _month_year(m: re.Match) -> str:
    month_num = _MONTH_MAP[m.group(1).lower()]
    return f"{m.group(2)}-{month_num}-01"


# M.D.YY (dotted, short year) — e.g. "3.4.26" → "2026-03-04"
@_register(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{2})(?!\d)")
def _dotted_short_year(m: re.Match) -> str:
    month = m.group(1).zfill(2)
    day = m.group(2).zfill(2)
    year = f"20{m.group(3)}"
    return f"{year}-{month}-{day}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_pdf_links(html: str, base_url: str) -> list[dict]:
    """Find all PDF links in an HTML page.

    Args:
        html:     Raw HTML string of a meeting minutes page.
        base_url: Base URL used to resolve relative hrefs to absolute URLs.

    Returns:
        List of dicts with keys:
            url       — absolute URL to the PDF
            filename  — the filename portion of the URL (e.g. "Minutes.pdf")
            link_text — visible anchor text, whitespace-collapsed
    """
    # Simple regex-based extraction — no BeautifulSoup dependency required.
    anchor_re = re.compile(
        r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    records = []
    seen_urls: set[str] = set()
    for m in anchor_re.finditer(html):
        href = m.group(1).strip()
        raw_text = m.group(2)
        # Strip inner HTML tags from link text, collapse whitespace
        link_text = re.sub(r"<[^>]+>", "", raw_text).strip()
        link_text = re.sub(r"\s+", " ", link_text)

        # Keep links that either:
        #   (a) end with .pdf, OR
        #   (b) match a known PDF-serving route pattern where the URL has
        #       no .pdf extension but the route returns application/pdf.
        #       CivicEngage:   /AgendaCenter/ViewFile/...
        #                       /DocumentCenter/View/...
        #       CourseVector:  /document/<slug>/     (PA Boroughs template)
        path = urlparse(href).path
        path_lower = path.lower()
        is_pdf_ext = path_lower.endswith(".pdf")
        is_civicengage = (
            "/agendacenter/viewfile/" in path_lower
            or "/documentcenter/view/" in path_lower
        )
        is_coursevector_doc = re.match(r"^/document/[^/]+/?$", path_lower) is not None
        if not (is_pdf_ext or is_civicengage or is_coursevector_doc):
            continue

        absolute_url = urljoin(base_url, href)
        # Dedup: CivicEngage lists each meeting item 2-3 times per page
        if absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)

        if is_pdf_ext:
            filename = path.split("/")[-1] or href.split("/")[-1]
        else:
            # Synthesize a filename from the URL tail + link text so the
            # date parser and classifier have something to work with.
            tail = path.rstrip("/").split("/")[-1] or "document"
            filename = f"{tail}.pdf"

        records.append({
            "url": absolute_url,
            "filename": filename,
            "link_text": link_text,
        })

    return records


def parse_meeting_date_from_filename(filename: str) -> str | None:
    """Extract an ISO date (YYYY-MM-DD) from a meeting minutes filename.

    Recognises five common patterns (in priority order):
      1. YYYY-MM-DD or YYYY_MM_DD  →  "2025-11-14"
      2. MM-DD-YYYY or MM_DD_YYYY  →  "2026-01-15"
      3. MonthName Day, Year       →  "2026-01-05"
      4. MonthName_YYYY            →  "2025-03-01"  (day defaults to 01)
      5. M.D.YY                    →  "2026-03-04"

    Args:
        filename: The bare filename string (e.g. "PC_01-15-2026.pdf").

    Returns:
        ISO date string, or None if no recognisable date is found.
    """
    # Strip extension to avoid digit sequences inside ".pdf" confusing patterns
    stem = re.sub(r"\.[^.]+$", "", filename)

    for pattern, handler in _DATE_PATTERNS:
        m = pattern.search(stem)
        if m:
            return handler(m)

    return None


def classify_proceeding_type(filename: str, link_text: str) -> str:
    """Classify a proceeding by type using filename and link text keywords.

    Priority (first match wins):
        "zoning_hearing"      — ZHB, Zoning Hearing
        "planning_commission" — PC (as word/prefix), Planning Commission
        "supervisors"         — BOS, Supervisors
        "council"             — Council
        "unknown"             — no match

    Args:
        filename:  The bare filename (e.g. "ZHB_Minutes_March_2025.pdf").
        link_text: The visible anchor text for the link.

    Returns:
        One of: "zoning_hearing", "planning_commission", "supervisors",
        "council", "unknown".
    """
    # Strip the extension so ".pdf" suffix doesn't interfere with boundary checks.
    stem = re.sub(r"\.[^.]+$", "", filename)
    combined = f"{stem} {link_text}"

    # Helper: match a token that is not part of a longer alphabetic word.
    # We use (?<![A-Za-z]) / (?![A-Za-z]) rather than \b because \b treats
    # underscores as word characters, breaking matching in filenames like
    # "ZHB_Minutes..." where ZHB is followed by '_'.
    def _token(tok: str) -> re.Pattern:
        return re.compile(rf"(?<![A-Za-z]){re.escape(tok)}(?![A-Za-z])", re.IGNORECASE)

    # ZHB or "Zoning Hearing"
    if _token("ZHB").search(combined) or re.search(r"Zoning[\s_-]+Hearing", combined, re.IGNORECASE):
        return "zoning_hearing"

    # PC (standalone) or "Planning Commission"
    if _token("PC").search(combined) or re.search(r"Planning[\s_-]+Commission", combined, re.IGNORECASE):
        return "planning_commission"

    # BOS (standalone) or "Supervisors"
    if _token("BOS").search(combined) or re.search(r"Supervisors?", combined, re.IGNORECASE):
        return "supervisors"

    # "Council"
    if re.search(r"Council", combined, re.IGNORECASE):
        return "council"

    return "unknown"
