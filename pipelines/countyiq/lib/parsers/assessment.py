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


def _parse_currency(text: str) -> int:
    """Strip $ and commas, return int. Returns 0 for empty/whitespace."""
    cleaned = text.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return 0
    return int(cleaned)


def _get_section(soup: BeautifulSoup, section_name: str):
    """Find a <div name="SECTION_NAME"> in the soup."""
    return soup.find("div", attrs={"name": section_name})


def _get_label_value(section, label: str) -> str:
    """Find a DataletSideHeading matching label and return its DataletData sibling."""
    if section is None:
        return ""
    for td in section.find_all("td", class_="DataletSideHeading"):
        if td.get_text(strip=True) == label:
            data_td = td.find_next_sibling("td", class_="DataletData")
            if data_td:
                return data_td.get_text(strip=True)
    return ""


def _parse_data_table(section) -> list[dict]:
    """Parse a table with DataletTopHeading headers and DataletData rows.

    Returns list of dicts keyed by header text (lowercased, spaces → underscores).
    Skips rows where the first cell is empty or contains 'Total:'.
    """
    if section is None:
        return []

    headers = []
    for th in section.find_all("td", class_="DataletTopHeading"):
        headers.append(th.get_text(strip=True))

    if not headers:
        return []

    rows = []
    # Find all DataletData cells, group them by header count
    all_data_cells = section.find_all("td", class_="DataletData")
    n_cols = len(headers)

    for i in range(0, len(all_data_cells), n_cols):
        chunk = all_data_cells[i:i + n_cols]
        if len(chunk) < n_cols:
            break
        first_val = chunk[0].get_text(strip=True)
        if not first_val or "Total:" in first_val:
            continue
        row = {}
        for j, hdr in enumerate(headers):
            key = hdr.lower().replace(" ", "_").replace(".", "")
            row[key] = chunk[j].get_text(strip=True)
        rows.append(row)

    return rows


def parse_printable_summary(html: str) -> dict:
    """Extract all fields from the Printable Summary page.

    Returns dict with keys: municipality, school_district, land_use_code,
    assessed_land, assessed_building, assessed_total, sale_date, sale_price,
    permits (list[dict]), delinquent_taxes (list[dict]), value_history (list[dict])
    """
    soup = BeautifulSoup(html, "html.parser")

    # --- Municipality & School District from header ---
    municipality = ""
    school_district = ""
    for td in soup.find_all("td", class_="DataletHeaderTop"):
        text = td.get_text(strip=True)
        if text.startswith("MUNICIPALITY:"):
            # "MUNICIPALITY: 46I - SPRINGETTSBURY I-DST" → "SPRINGETTSBURY"
            after_dash = text.split(" - ", 1)
            if len(after_dash) > 1:
                muni = after_dash[1].strip()
                # Strip common suffixes like " I-DST", " TWP", " BORO"
                muni = re.sub(r"\s+\d*-?DST$", "", muni)
                muni = re.sub(r"\s+I-DST$", "", muni)
                municipality = muni
        elif text.startswith("SCHOOL:"):
            # "SCHOOL: 030 - YORK SUBURBAN SCHOOL" → "YORK SUBURBAN SCHOOL"
            after_dash = text.split(" - ", 1)
            if len(after_dash) > 1:
                school_district = after_dash[1].strip()

    # --- LUC from PARCEL section ---
    parcel_section = _get_section(soup, "PARCEL")
    luc_raw = _get_label_value(parcel_section, "LUC")
    # "102 - R - TWO STORY HOUSE" → "102"
    land_use_code = luc_raw.split(" - ", 1)[0].strip() if luc_raw else ""

    # --- Assessed values from VALUESALL section ---
    values_section = _get_section(soup, "VALUESALL")
    assessed_land = _parse_currency(_get_label_value(values_section, "Appraised Land"))
    assessed_building = _parse_currency(_get_label_value(values_section, "Appraised Building"))
    assessed_total = _parse_currency(_get_label_value(values_section, "Appraised Total"))

    # --- Sale history from SALE_HIST section ---
    sale_section = _get_section(soup, "SALE_HIST")
    sale_rows = _parse_data_table(sale_section)
    sale_date = ""
    sale_price = 0
    if sale_rows:
        sale_date = sale_rows[0].get("sale_date", "")
        sale_price = _parse_currency(sale_rows[0].get("sale_price", "0"))

    # --- Permits from PERMITS_LIST section ---
    permits_section = _get_section(soup, "PERMITS_LIST")
    raw_permits = _parse_data_table(permits_section)
    permits = []
    for p in raw_permits:
        permits.append({
            "permit_date": p.get("permit_date", ""),
            "permit_number": p.get("permit_number", ""),
            "amount": _parse_currency(p.get("amount", "0")),
            "completion_date": p.get("completion_date", ""),
        })

    # --- Value history from ASSESSHIST_RLP section ---
    hist_section = _get_section(soup, "ASSESSHIST_RLP")
    raw_history = _parse_data_table(hist_section)
    value_history = []
    for h in raw_history:
        value_history.append({
            "tax_year": h.get("tax_year", ""),
            "land_asmt": _parse_currency(h.get("land_asmt", "0")),
            "bldg_asmt": _parse_currency(h.get("bldg_asmt", "0")),
            "total_asmt": _parse_currency(h.get("total_asmt", "0")),
        })

    # --- Delinquent taxes from TAXCLAIMBYYEAR section ---
    delinquent_section = _get_section(soup, "TAXCLAIMBYYEAR")
    delinquent_taxes = _parse_data_table(delinquent_section) if delinquent_section else []

    return {
        "municipality": municipality,
        "school_district": school_district,
        "land_use_code": land_use_code,
        "assessed_land": assessed_land,
        "assessed_building": assessed_building,
        "assessed_total": assessed_total,
        "sale_date": sale_date,
        "sale_price": sale_price,
        "permits": permits,
        "delinquent_taxes": delinquent_taxes,
        "value_history": value_history,
    }
