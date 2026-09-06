"""Sheriff sale listings from York County attorney portal → staging.sheriff_sales.

Source: https://attorneyportal.yorkcountypa.gov/sheriff.salelisting/
Records: ~95-120 active listings per sale date
Schedule: Weekly (scraper_refresh job)
Strategy: honest direct HTTP fetch of the official listing
"""

import re
from datetime import datetime

from bs4 import BeautifulSoup
from dagster import (
    asset,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import get_county_config
from countyiq.lib.robots import RobotsPolicy, get_with_robots, source_origin
from countyiq.lib.scd import scd2_upsert
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["case_no", "property_address"]
VALUE_COLUMNS = [
    "plaintiff",
    "defendant",
    "zip_code",
    "municipality",
    "judgment_amount",
    "status",
    "status_date",
    "source_url",
]

_USER_AGENT = "Mozilla/5.0 (compatible; CountyIQ/1.0; +https://countyiq.app)"
_ROBOTS_PRODUCT_TOKEN = "CountyIQ"


def parse_sheriff_sale_page(html: str) -> list[dict]:
    """Parse sheriff sale listing HTML into records."""
    soup = BeautifulSoup(html, "html.parser")
    records = []

    table = soup.find("table")
    if not table:
        return records

    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 6:
            continue

        case_no = cells[0].get_text(strip=True)
        if not case_no or not re.match(r"\d{4}-\w{2}-\d+", case_no):
            continue

        parties_text = cells[1].get_text(strip=True)
        address_text = cells[3].get_text(strip=True)
        judgment_text = cells[4].get_text(strip=True)
        status_text = cells[5].get_text(strip=True)

        # Parse parties: "PLAINTIFF vs. DEFENDANT"
        parts = re.split(r"\s+vs?\.\s+", parties_text, maxsplit=1)
        plaintiff = parts[0].strip() if parts else ""
        defendant = parts[1].strip() if len(parts) > 1 else ""

        # Parse address: "STREET ADDRESSCITY, PA ZIPMUNICIPALIY"
        zip_match = re.search(r"PA (\d{5})", address_text)
        zip_code = zip_match.group(1) if zip_match else ""
        municipality = ""
        street = address_text
        if zip_code:
            after_zip = address_text.split(f"PA {zip_code}")
            if len(after_zip) > 1:
                municipality = after_zip[1].strip().rstrip(".")
            before_zip = after_zip[0].strip()
            # City is the last word group before PA
            city_match = re.search(r"([A-Z][A-Z ]+)$", before_zip)
            if city_match:
                street = before_zip[: before_zip.rfind(city_match.group(1))].strip()

        # Parse judgment
        judgment_clean = judgment_text.replace("$", "").replace(",", "").strip()
        judgment = float(judgment_clean) if judgment_clean else None

        # Parse status
        status_base = status_text.split("(")[0].strip()
        date_match = re.search(r"\(\s*(\d+/\d+/\d+)\s*\)", status_text)
        status_date = None
        if date_match:
            try:
                status_date = datetime.strptime(date_match.group(1), "%m/%d/%Y").date()
            except ValueError:
                pass

        records.append(
            {
                "case_no": case_no,
                "plaintiff": plaintiff[:500],
                "defendant": defendant[:500],
                "property_address": street[:200],
                "zip_code": zip_code,
                "municipality": municipality[:100],
                "judgment_amount": judgment,
                "status": status_base,
                "status_date": status_date,
            }
        )

    return records


@asset(
    group_name="scrapers",
    description="Sheriff sale listings → staging.sheriff_sales",
    kinds={"postgres", "html"},
)
def sheriff_sales_scrape(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch the official sheriff listing without browser impersonation."""
    county = get_county_config()
    authorization = authorize_source(
        database,
        source_key="sheriff_sales",
        acquisition_method="official_html_direct",
        asset_key="sheriff_sales_scrape",
        dagster_run_id=context.run_id,
    )
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")

    context.log.info(f"Fetching official sheriff listing: {county.sheriff_sales_url}")
    robots = RobotsPolicy(
        _USER_AGENT,
        product_token=_ROBOTS_PRODUCT_TOKEN,
    )
    response = get_with_robots(
        county.sheriff_sales_url,
        robots=robots,
        headers={"User-Agent": _USER_AGENT},
        timeout=60,
        allowed_origins={source_origin(county.sheriff_sales_url)},
    )
    response.raise_for_status()
    html = response.text

    context.log.info("Page loaded, parsing...")
    s3.archive(
        f"{county.s3_prefix}/scrapers/sheriff_sales", html, filename="listing.html"
    )

    records = parse_sheriff_sale_page(html)
    for rec in records:
        rec["source_url"] = county.sheriff_sales_url
        # property_address is part of the PK (migration 028) — never NULL.
        rec["property_address"] = rec.get("property_address") or ""

    # The portal lists a continued/postponed sale under BOTH its original and
    # rescheduled date — the same (case_no, property_address) twice in one
    # page. Two rows with one SCD2 key in a single batch violate the
    # (key, valid_from) PK; keep the last occurrence (latest status wins).
    deduped: dict = {}
    for rec in records:
        deduped[(rec.get("case_no"), rec.get("property_address"))] = rec
    if len(deduped) < len(records):
        context.log.info(
            f"Deduplicated {len(records) - len(deduped)} repeated listing(s) "
            "(continued sales appear under both dates)"
        )
    records = list(deduped.values())
    context.log.info(f"Parsed {len(records)} sheriff sale records")

    if not records:
        context.log.warning("No sheriff sale records found")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    # SCD2 upsert
    cur = database.cursor()
    try:
        stats = scd2_upsert(
            cursor=cur,
            schema="staging",
            table="sheriff_sales",
            records=records,
            key_columns=KEY_COLUMNS,
            value_columns=VALUE_COLUMNS,
        )
    finally:
        cur.close()

    active = sum(
        1 for r in records if r["status"] == "Active" or r["status"] == "Active (P)"
    )
    total_judgment = sum(r["judgment_amount"] or 0 for r in records)

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(len(records)),
            "active_sales": MetadataValue.int(active),
            "total_judgment": MetadataValue.float(total_judgment),
            "inserted": MetadataValue.int(stats["inserted"]),
            "expired": MetadataValue.int(stats["expired"]),
        }
    )


sheriff_sales_record_count = make_row_count_check(
    sheriff_sales_scrape,
    table="sheriff_sales",
    threshold_fn=lambda: get_county_config().sheriff_sales_min_records,
    metadata_key="count",
    name="sheriff_sales_record_count",
)
