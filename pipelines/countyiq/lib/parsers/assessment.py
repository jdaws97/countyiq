"""Parser for York County Assessment portal (iasWorld Public Access).

Handles two page types:
  1. Search results page — table of PARID, Owner, Location, Class
  2. Printable Summary page — all tabs rendered on one page (added in Task 5)

HTML parsing uses BeautifulSoup with the portal's table-based layout.
"""

import re

from bs4 import BeautifulSoup


def parid_to_pidn(parid: str | None) -> str:
    """Convert 18-digit PARID to 13-char PIDN.

    SQL equivalent (1-based): SUBSTRING(1,2) + SUBSTRING(4,3) + SUBSTRING(8,2) + SUBSTRING(11,6)
    Python (0-based):         parid[0:2]     + parid[3:6]     + parid[7:9]     + parid[10:16]

    Example: 460000001000100000 → 4600001001000
    """
    if not parid or len(parid) < 16:
        return ""
    return parid[0:2] + parid[3:6] + parid[7:9] + parid[10:16]


def get_total_found(html: str) -> int:
    """Extract total record count from search results page.

    Looks for text like "Total found: 9305 records" in the page.
    Returns 0 if no match found.
    """
    match = re.search(r"Total found:\s*([\d,]+)\s*records", html)
    if match:
        return int(match.group(1).replace(",", ""))
    return 0


def parse_search_results_page(html: str) -> list[dict]:
    """Extract property rows from search results HTML.

    The results table has clickable rows with 4 cells: Parcel, Owner, Location, Class.
    Header rows and empty rows are skipped.

    Returns:
        List of dicts with keys: parid, owner_name, address, property_class
    """
    soup = BeautifulSoup(html, "html.parser")
    records = []

    for tr in soup.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) != 4:
            continue

        parid_text = cells[0].get_text(strip=True)
        if not parid_text or len(parid_text) < 16:
            continue
        if parid_text.lower() in ("parcel", "sort by parcel"):
            continue

        records.append({
            "parid": parid_text,
            "owner_name": cells[1].get_text(strip=True),
            "address": cells[2].get_text(strip=True),
            "property_class": cells[3].get_text(strip=True),
        })

    return records
