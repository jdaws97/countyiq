"""Parser for municipality public proceedings (meeting minutes) pages.

Extracts PDF links from HTML meeting minutes pages and classifies them
by proceeding type (board of supervisors, planning commission, etc.).

All functions are pure — HTML / filename string in, structured dicts out.
"""

import re
from collections.abc import Callable
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

_DateHandler = Callable[[re.Match[str]], str]
_DATE_PATTERNS: list[tuple[re.Pattern[str], _DateHandler]] = []


def _register(pattern: str) -> Callable[[_DateHandler], _DateHandler]:
    """Decorator that registers a date-extraction handler."""
    def decorator(fn: _DateHandler) -> _DateHandler:
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


# M-D-YY (dashed/underscored, short year) — e.g. "minutes 1-3-22" → "2022-01-03".
# Registered after the 4-digit-year patterns so those keep priority.
@_register(r"(?<!\d)(\d{1,2})[-_](\d{1,2})[-_](\d{2})(?!\d)")
def _dashed_short_year(m: re.Match) -> str:
    month = m.group(1).zfill(2)
    day = m.group(2).zfill(2)
    return f"20{m.group(3)}-{month}-{day}"


# Compact 8-digit dates with no separators: MMDDYYYY (West York Drive files
# like "05042026_Meeting_Minutes.pdf") or YYYYMMDD. Lowest priority; the
# handler returns None (skip) when the digits don't form a plausible date.
@_register(r"(?<!\d)(\d{8})(?!\d)")
def _compact_eight_digits(m: re.Match) -> str | None:
    digits = m.group(1)

    def _plausible(year: str, month: str, day: str) -> bool:
        return (
            1900 <= int(year) <= 2099
            and 1 <= int(month) <= 12
            and 1 <= int(day) <= 31
        )

    year, month, day = digits[:4], digits[4:6], digits[6:8]
    if _plausible(year, month, day):
        return f"{year}-{month}-{day}"
    month, day, year = digits[:2], digits[2:4], digits[4:8]
    if _plausible(year, month, day):
        return f"{year}-{month}-{day}"
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_DRIVE_FOLDER_RE = re.compile(
    r"drive\.google\.com/(?:drive/folders/|folderview\?id=)([A-Za-z0-9_-]+)"
)

# One embeddedfolderview entry: the id carries the item ID, the first href
# inside distinguishes file (/file/d/<id>/) from subfolder (/drive/folders/).
_DRIVE_ENTRY_RE = re.compile(
    r'<div class="flip-entry" id="entry-([A-Za-z0-9_-]+)".*?'
    r'<a href="([^"]+)".*?'
    r'<div class="flip-entry-title">([^<]*)</div>',
    re.DOTALL,
)


def extract_drive_folder_ids(html: str) -> list[str]:
    """Find Google Drive folder IDs linked from a municipality minutes page.

    Recognises both modern (/drive/folders/<id>) and legacy
    (/folderview?id=<id>) share links. Order-preserving, deduped.
    """
    seen: set[str] = set()
    ids: list[str] = []
    for folder_id in _DRIVE_FOLDER_RE.findall(html):
        if folder_id not in seen:
            seen.add(folder_id)
            ids.append(folder_id)
    return ids


def parse_drive_folder_listing(html: str) -> dict:
    """Parse a drive.google.com/embeddedfolderview?id=... static HTML page.

    The embedded view is server-side rendered, so no browser is needed.
    Returns {"files": [link records], "subfolder_ids": [...]}; file URLs use
    the uc?export=download endpoint, which serves raw bytes headlessly.
    """
    files: list[dict] = []
    subfolder_ids: list[str] = []
    for entry_id, href, title in _DRIVE_ENTRY_RE.findall(html):
        title = title.strip()
        if "/drive/folders/" in href:
            subfolder_ids.append(entry_id)
        elif "/file/d/" in href:
            files.append({
                "url": f"https://drive.google.com/uc?export=download&id={entry_id}",
                "filename": title,
                "link_text": title,
            })
    return {"files": files, "subfolder_ids": subfolder_ids}



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
        #   (a) end with a document extension (.pdf, .doc, .docx — several
        #       small boroughs post minutes as Word files), OR
        #   (b) match a known PDF-serving route pattern where the URL has
        #       no .pdf extension but the route returns application/pdf.
        #       CivicEngage:   /AgendaCenter/ViewFile/...
        #                       /DocumentCenter/View/...
        #       CourseVector:  /document/<slug>/     (PA Boroughs template)
        parsed = urlparse(href)
        path = parsed.path
        path_lower = path.lower()
        is_doc_ext = path_lower.endswith((".pdf", ".doc", ".docx"))
        is_civicengage = (
            "/agendacenter/viewfile/" in path_lower
            or "/documentcenter/view/" in path_lower
        )
        is_coursevector_doc = re.match(r"^/document/[^/]+/?$", path_lower) is not None
        is_bfd_download = path_lower.startswith("/bfd_download/")
        bfd_type = (
            re.search(r"Type\s*:\s*(pdf|docx?)\b", link_text, re.IGNORECASE)
            if is_bfd_download
            else None
        )
        if not (
            is_doc_ext
            or is_civicengage
            or is_coursevector_doc
            or bfd_type
        ):
            continue

        if is_civicengage and parsed.query:
            # CivicEngage emits a duplicate ``?html=true`` preview link beside
            # the document link. The preview returns HTML from a PDF-shaped
            # route, so canonicalize both variants to the downloadable file.
            query = [
                (key, value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                if key.casefold() != "html"
            ]
            parsed = parsed._replace(query=urlencode(query))
            href = parsed.geturl()

        absolute_url = urljoin(base_url, href)
        # Dedup: CivicEngage lists each meeting item 2-3 times per page
        if absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)

        if is_doc_ext:
            # Municipal CMS/CDN links commonly percent-encode the human
            # filename. Decode it before date parsing and classification so
            # names such as ``January%2019%2C%202026%20Minutes.pdf`` retain
            # their semantic metadata.
            filename = unquote(path.split("/")[-1] or href.split("/")[-1])
            # Wix serves hex-named files with the human-readable name in the
            # dn= query param — prefer it (it carries the meeting date).
            dn_match = re.search(r"[?&]dn=([^&]+)", href)
            if dn_match:
                filename = unquote(dn_match.group(1))
        elif bfd_type:
            # Better Files Download exposes an extensionless redirect, but
            # prints the real file type in the link metadata. Preserve that
            # type so the downloader validates and extracts Word documents
            # correctly after following the redirect.
            tail = path.rstrip("/").split("/")[-1] or "document"
            filename = f"{tail}.{bfd_type.group(1).lower()}"
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
            result = handler(m)
            if result is not None:
                return result

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
