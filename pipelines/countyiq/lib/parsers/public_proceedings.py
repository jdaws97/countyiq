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
    for m in anchor_re.finditer(html):
        href = m.group(1).strip()
        raw_text = m.group(2)
        # Strip inner HTML tags from link text, collapse whitespace
        link_text = re.sub(r"<[^>]+>", "", raw_text).strip()
        link_text = re.sub(r"\s+", " ", link_text)

        # Only keep links that end with .pdf (case-insensitive)
        path = urlparse(href).path
        if not path.lower().endswith(".pdf"):
            continue

        absolute_url = urljoin(base_url, href)
        filename = path.split("/")[-1] or href.split("/")[-1]

        records.append({
            "url": absolute_url,
            "filename": filename,
            "link_text": link_text,
        })

    return records


def parse_meeting_date_from_filename(filename: str) -> str | None:
    """Extract an ISO date (YYYY-MM-DD) from a meeting minutes filename.

    Recognises three common patterns (in priority order):
      1. YYYY-MM-DD or YYYY_MM_DD  →  "2025-11-14"
      2. MM-DD-YYYY or MM_DD_YYYY  →  "2026-01-15"
      3. MonthName_YYYY            →  "2025-03-01"  (day defaults to 01)

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
