"""Parser helpers for York County Tyler Recorder of Deeds pages."""

from __future__ import annotations

from datetime import datetime
import re
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup


LEGAL_PIDN_RE = re.compile(
    r"([0-9A-Z]{2})-([0-9A-Z]{3})-([0-9A-Z]{2})-([0-9A-Z]{4})\.([0-9A-Z]{2})-([0-9A-Z]{5})",
    re.IGNORECASE,
)
YORK_TZ = ZoneInfo("America/New_York")


def pidn_to_recorder_upi(pidn: str | None) -> str:
    """Convert CountyIQ PIDN to the 18-char recorder UPI/TAX number format."""
    cleaned = _clean_token(pidn)
    if len(cleaned) != 13:
        return ""
    return f"{cleaned}00000"


def pidn_to_recorder_legal(pidn: str | None) -> str:
    """Format PIDN as the recorder legal-string parcel representation."""
    cleaned = _clean_token(pidn)
    if len(cleaned) != 13:
        return ""
    return (
        f"{cleaned[0:2]}-{cleaned[2:5]}-{cleaned[5:7]}-"
        f"{cleaned[7:11]}.{cleaned[11:13]}-00000"
    )


def extract_pidns_from_legal_text(text: str | None) -> list[str]:
    """Extract one or more PIDNs from recorder legal text."""
    if not text:
        return []

    pidns = []
    seen = set()
    for match in LEGAL_PIDN_RE.finditer(text):
        pidn = "".join(match.groups()[:5]).upper()
        if pidn not in seen:
            seen.add(pidn)
            pidns.append(pidn)
    return pidns


def parse_tyler_search_results(html: str) -> list[dict]:
    """Parse a Tyler parcel search results page into document metadata."""
    soup = BeautifulSoup(html, "html.parser")
    records = []

    for row in soup.select("li.ss-search-row[data-documentid]"):
        header = row.find("h1")
        header_text = _clean_text(header.get_text(" ", strip=True)) if header else ""

        document_id = _clean_text(row.get("data-documentid"))
        source_url = _clean_text(row.get("data-href"))
        document_number = ""
        book = ""
        page = ""
        document_type = ""

        if header_text:
            document_number_match = re.search(r"\b(\d{8,})\b", header_text)
            if document_number_match:
                document_number = document_number_match.group(1)
            book_page_match = re.search(r"B:\s*([A-Z0-9-]+)\s+P:\s*([A-Z0-9-]+)", header_text, re.IGNORECASE)
            if book_page_match:
                book = book_page_match.group(1)
                page = book_page_match.group(2)
            header_parts = [part.strip(" \u2022•") for part in re.split(r"\s*[•\u2022]\s*", header_text) if part.strip(" \u2022•")]
            if header_parts:
                last_part = header_parts[-1]
                if last_part != document_number and not last_part.startswith("B:"):
                    document_type = last_part

        section_map: dict[str, list[str]] = {}
        for column in row.select("div.searchResultFourColumn"):
            values = [_clean_text(li.get_text(" ", strip=True)) for li in column.select("li")]
            values = [value for value in values if value]
            if len(values) < 2:
                continue
            section_map[values[0]] = values[1:]

        recording_values = _find_section_values(section_map, "Recording Date")
        grantors = _find_section_values(section_map, "Grantor")
        grantees = _find_section_values(section_map, "Grantee")
        legal_values = _find_section_values(section_map, "Legal")
        legal_text = legal_values[0] if legal_values else ""

        records.append(
            {
                "document_id": document_id,
                "document_number": document_number,
                "document_type": document_type,
                "recording_at": _parse_datetime(recording_values[0] if recording_values else ""),
                "book": book,
                "page": page,
                "grantors": grantors,
                "grantees": grantees,
                "legal_text": legal_text,
                "legal_pidns": extract_pidns_from_legal_text(legal_text),
                "source_url": source_url,
            }
        )

    return records


def parse_tyler_document_detail(html: str) -> dict:
    """Parse a Tyler document detail page into document metadata."""
    soup = BeautifulSoup(html, "html.parser")
    info = soup.find(id="documentIndexingInformation") or soup

    document_type = _find_section_value(info, "Document Type")
    labels = _parse_labeled_values(info)

    book = ""
    page = ""
    book_page_divider = _find_divider(info, "Book Page")
    if book_page_divider:
        cells = book_page_divider.find_next("table").find_all("td")
        if len(cells) >= 2:
            book = _clean_text(cells[0].get_text(" ", strip=True))
            page = _clean_text(cells[1].get_text(" ", strip=True))

    legal_text = ""
    legal_divider = _find_divider(info, "Legal")
    if legal_divider:
        table = legal_divider.find_next("table")
        divs = table.find_all("div") if table else []
        texts = [_clean_text(div.get_text(" ", strip=True)) for div in divs]
        texts = [text for text in texts if text]
        if texts:
            legal_text = texts[-1]

    grantors = _ensure_list(labels.get("Grantor", []))
    grantees = _ensure_list(labels.get("Grantee", []))

    return {
        "document_type": document_type,
        "document_number": _ensure_scalar(labels.get("Document Number", "")),
        "recording_at": _parse_datetime(_ensure_scalar(labels.get("Recording Date", ""))),
        "num_pages": _parse_int(_ensure_scalar(labels.get("Number Pages", ""))),
        "consideration": _parse_currency(_ensure_scalar(labels.get("Consideration", ""))),
        "book": book,
        "page": page,
        "grantors": grantors,
        "grantees": grantees,
        "legal_text": legal_text,
        "legal_pidns": extract_pidns_from_legal_text(legal_text),
    }


def _parse_labeled_values(soup: BeautifulSoup) -> dict[str, str | list[str]]:
    values: dict[str, str | list[str]] = {}
    for td in soup.find_all("td"):
        strong = td.find("strong")
        if not strong:
            continue
        label = _clean_text(strong.get_text(" ", strip=True)).rstrip(":")
        direct_divs = td.find_all("div", recursive=False)
        if len(direct_divs) < 2:
            continue
        value = _extract_div_value(direct_divs[1])
        if value == "" or value == []:
            continue
        values[label] = value
    return values


def _find_section_value(soup: BeautifulSoup, title: str) -> str:
    divider = _find_divider(soup, title)
    if divider is None:
        return ""
    sibling = divider.find_next_sibling("li")
    if sibling is None:
        return ""
    return _clean_text(sibling.get_text(" ", strip=True))


def _find_divider(soup: BeautifulSoup, title: str):
    for divider in soup.find_all("li", attrs={"role": "heading"}):
        if _clean_text(divider.get_text(" ", strip=True)) == title:
            return divider
    return None


def _find_section_values(section_map: dict[str, list[str]], prefix: str) -> list[str]:
    target = prefix.lower()
    for label, values in section_map.items():
        if label.lower().startswith(target):
            return values
    return []


def _extract_div_value(div) -> str | list[str]:
    items = [_clean_text(li.get_text(" ", strip=True)) for li in div.select("li")]
    items = [item for item in items if item]
    if items:
        return items
    return _clean_text(div.get_text(" ", strip=True))


def _ensure_scalar(value: str | list[str]) -> str:
    if isinstance(value, list):
        return value[0] if value else ""
    return value


def _ensure_list(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return value
    return [value] if value else []


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=YORK_TZ)
        except ValueError:
            continue
    return None


def _parse_int(value: str) -> int | None:
    value = _clean_text(value)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_currency(value: str) -> float | None:
    cleaned = _clean_text(value).replace("$", "").replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _clean_token(value: str | None) -> str:
    return _clean_text(value).replace("-", "").replace(".", "").replace(" ", "").upper()
