"""Sheriff sale listings from York County attorney portal → staging.sheriff_sales.

Source: https://attorneyportal.yorkcountypa.gov/sheriff.salelisting/
Records: ~95-120 active listings per sale date
Schedule: Weekly (scraper_refresh job)
Strategy: Playwright scrape — page is JavaScript-rendered
"""

import re
from datetime import datetime

from bs4 import BeautifulSoup
from dagster import (
    asset,
    asset_check,
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.lib.county_config import get_county_config
from countyiq.lib.playwright_utils import browser_context
from countyiq.lib.scd import scd2_upsert
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["case_no", "property_address"]
VALUE_COLUMNS = [
    "plaintiff", "defendant", "zip_code",
    "municipality", "judgment_amount", "status", "status_date", "source_url",
]


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
                street = before_zip[:before_zip.rfind(city_match.group(1))].strip()

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

        records.append({
            "case_no": case_no,
            "plaintiff": plaintiff[:500],
            "defendant": defendant[:500],
            "property_address": street[:200],
            "zip_code": zip_code,
            "municipality": municipality[:100],
            "judgment_amount": judgment,
            "status": status_base,
            "status_date": status_date,
        })

    return records


@asset(
    group_name="scrapers",
    description="Sheriff sale listings → staging.sheriff_sales",
    kinds={"postgres", "playwright"},
)
def sheriff_sales_scrape(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Scrape sheriff sale listings via Playwright."""
    county = get_county_config()

    with browser_context() as page:
        context.log.info(f"Navigating to {county.sheriff_sales_url}")
        page.goto(county.sheriff_sales_url)
        page.wait_for_selector("table", timeout=15000)

        # Get the page HTML after JS rendering
        html = page.content()

    context.log.info(f"Page loaded, parsing...")
    s3.archive(f"{county.s3_prefix}/scrapers/sheriff_sales", html, filename="listing.html")

    records = parse_sheriff_sale_page(html)
    for rec in records:
        rec["source_url"] = county.sheriff_sales_url
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

    active = sum(1 for r in records if r["status"] == "Active" or r["status"] == "Active (P)")
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


@asset_check(asset=sheriff_sales_scrape)
def sheriff_sales_record_count(database: DatabaseResource) -> AssetCheckResult:
    county = get_county_config()
    result = database.execute("SELECT COUNT(*) FROM staging.sheriff_sales WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count >= county.sheriff_sales_min_records,
        severity=AssetCheckSeverity.ERROR,
        metadata={"count": MetadataValue.int(count)})
