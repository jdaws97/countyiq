"""PA Department of State corporate entity lookup -> staging.corporate_entities.

Strategy:
  - Extract unique LLC/Corp/LP/etc. owner names from staging.parcels
  - Skip entities already looked up in the last 7 days
  - Use Playwright to search file.dos.pa.gov/search/business for each entity
  - Intercept the underlying REST API responses (behind Cloudflare)
  - SCD2 upsert results to staging.corporate_entities
  - Archive raw responses to R2
"""

import re
import time
from datetime import datetime, timezone

from playwright.sync_api import Error as PlaywrightError

from dagster import (
    AssetCheckSeverity,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.pa_dos_entities import parse_search_results
from countyiq.lib.playwright_utils import browser_context, take_screenshot
from countyiq.lib.scd import scd2_upsert
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource


SOURCE_NAME = "pa_dos_entities"

# SCD2 key / value column split
KEY_COLUMNS = ["entity_name"]
VALUE_COLUMNS = [
    "entity_number",
    "entity_type",
    "status",
    "formation_date",
    "registered_agent_name",
    "registered_agent_address",
    "office_address",
    "officers",
    "source_url",
]

# Regex that identifies a business entity owner name (case-insensitive)
_ENTITY_PATTERN = re.compile(
    r"\b(LLC|L\.L\.C|INC|CORP|LP|L\.P|LTD|TRUST|PARTNERS|ASSOCIATES|"
    r"HOLDINGS|ENTERPRISES|PROPERTIES|GROUP|VENTURES|CAPITAL|INVESTMENTS)\b",
    re.IGNORECASE,
)

# Cap on consecutive errors before aborting the run
_MAX_ERRORS = 50

# Progress log interval
_LOG_INTERVAL = 25

# Throttle between searches (seconds)
_THROTTLE_SECONDS = 1.5

# Cloudflare wait — how long to give the challenge to resolve
_CF_WAIT_MS = 30_000

# Selector starting points (adjusted to real site after Playwright inspection)
_SEARCH_INPUT_SELECTOR = 'input[placeholder*="Search by name"], [role="textbox"]'
_SEARCH_BUTTON_TEXT = "Execute search"
_RESULTS_TABLE_SELECTOR = "table"
_NO_RESULTS_INDICATOR = "No results"


@asset(
    group_name="scrapers",
    description="PA DOS corporate entity lookup for parcel owners -> staging.corporate_entities",
    kinds={"postgres", "playwright"},
)
def pa_dos_entities(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    county = get_county_config()
    log = context.log

    # --- 1. Fetch entity names that need lookup ---
    entity_names = _get_pending_entity_names(database)
    if not entity_names:
        log.info("No new business entity names to look up")
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("no_work"),
                "entities_queued": MetadataValue.int(0),
                "current_records": MetadataValue.int(_get_current_count(database)),
            }
        )

    log.info("Found %d entity names to look up", len(entity_names))

    # --- 2. Playwright scrape loop ---
    records: list[dict] = []
    raw_archive: list[dict] = []
    processed = 0
    skipped = 0
    error_count = 0

    with browser_context(timeout_ms=_CF_WAIT_MS) as page:
        # Navigate once and wait for Cloudflare to clear
        log.info("Navigating to PA DOS search: %s", county.pa_dos_search_url)
        try:
            page.goto(county.pa_dos_search_url, wait_until="networkidle")
        except Exception as nav_err:
            log.warning("Initial navigation error (retrying): %s", nav_err)
            try:
                page.goto(county.pa_dos_search_url, wait_until="domcontentloaded")
            except Exception as retry_err:
                log.error("Could not load PA DOS site: %s", retry_err)
                raise

        # Wait for the search input to appear (signals CF challenge is done)
        try:
            page.wait_for_selector(_SEARCH_INPUT_SELECTOR, timeout=_CF_WAIT_MS)
        except Exception:
            take_screenshot(page, "/tmp/pa_dos_cf_failure.png")
            raise RuntimeError(
                "Cloudflare challenge did not resolve within %dms" % _CF_WAIT_MS
            )

        for entity_name in entity_names:
            if error_count >= _MAX_ERRORS:
                log.error("Reached max error cap (%d) — stopping run", _MAX_ERRORS)
                break

            if processed > 0 and processed % _LOG_INTERVAL == 0:
                log.info(
                    "Progress: %d/%d processed, %d records, %d errors",
                    processed, len(entity_names), len(records), error_count,
                )

            result = _lookup_entity(page, entity_name, log)
            processed += 1

            if result is None:
                # No results or irrecoverable error already logged
                skipped += 1
                error_count += 1
                continue

            if result == "no_results":
                skipped += 1
                continue

            records.append(result)
            raw_archive.append({"entity_name": entity_name, "result": result})
            time.sleep(_THROTTLE_SECONDS)

    # --- 3. SCD2 upsert ---
    upsert_stats = {"inserted": 0, "expired": 0, "unchanged": 0}
    if records:
        cur = database.cursor()
        try:
            upsert_stats = scd2_upsert(
                cursor=cur,
                schema="staging",
                table="corporate_entities",
                records=records,
                key_columns=KEY_COLUMNS,
                value_columns=VALUE_COLUMNS,
                expire_missing=False,
            )
        finally:
            cur.close()

    # --- 4. Archive raw responses to R2 ---
    if raw_archive:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
        s3.archive(
            f"{county.s3_prefix}/scrapers/pa_dos_entities",
            {"run_at": datetime.now(timezone.utc).isoformat(), "results": raw_archive},
            filename=f"{date_str}.json",
        )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "entities_queued": MetadataValue.int(len(entity_names)),
            "entities_processed": MetadataValue.int(processed),
            "entities_skipped": MetadataValue.int(skipped),
            "entities_found": MetadataValue.int(len(records)),
            "errors": MetadataValue.int(error_count),
            "scd2_inserted": MetadataValue.int(upsert_stats.get("inserted", 0)),
            "scd2_expired": MetadataValue.int(upsert_stats.get("expired", 0)),
            "current_records": MetadataValue.int(_get_current_count(database)),
        }
    )


# ---------------------------------------------------------------------------
# Playwright lookup helpers
# ---------------------------------------------------------------------------

def _lookup_entity(page, entity_name: str, log) -> dict | None | str:
    """Search for a single entity on the PA DOS site.

    Returns:
        dict  — parsed entity record
        "no_results" — search returned nothing (not an error)
        None  — error occurred
    """
    try:
        return _do_search(page, entity_name, log)
    except Exception as err:
        log.warning("Error looking up entity '%s': %s", entity_name, err)
        take_screenshot(page, f"/tmp/pa_dos_err_{_safe_filename(entity_name)}.png")
        try:
            page.reload(wait_until="networkidle", timeout=20_000)
            page.wait_for_selector(_SEARCH_INPUT_SELECTOR, timeout=15_000)
        except PlaywrightError:
            pass
        return None


def _do_search(page, entity_name: str, log) -> dict | str:
    """Fill search form, wait for results, click first match, read detail."""
    # Clear and fill the search box
    search_input = page.locator(_SEARCH_INPUT_SELECTOR).first
    search_input.click()
    search_input.select_all()
    search_input.type(entity_name, delay=30)

    # Click Execute search
    page.get_by_role("button", name=re.compile(_SEARCH_BUTTON_TEXT, re.IGNORECASE)).click()

    # Wait for results or a "no results" indicator
    try:
        page.wait_for_selector(
            f"{_RESULTS_TABLE_SELECTOR}, text={_NO_RESULTS_INDICATOR}",
            timeout=15_000,
        )
    except Exception:
        log.debug("Search timed out waiting for results for '%s'", entity_name)
        return None

    # Check for "no results"
    page_text = page.inner_text("body")
    if _NO_RESULTS_INDICATOR.lower() in page_text.lower():
        log.debug("No results for '%s'", entity_name)
        return "no_results"

    # Grab raw search API response by reading the results table
    search_api_data = _intercept_search_data(page, entity_name)
    if not search_api_data:
        return "no_results"

    # Try to get detail by clicking the first result row
    detail_data = _click_first_result_and_get_detail(page, entity_name, log)
    if detail_data:
        record = _merge_search_and_detail(search_api_data, detail_data, entity_name)
    else:
        # Fall back to search data only
        parsed = parse_search_results(search_api_data)
        record = parsed[0] if parsed else None

    return record


def _intercept_search_data(page, entity_name: str) -> dict | None:
    """Read visible table rows into a synthetic search API response dict."""
    try:
        rows = page.locator(f"{_RESULTS_TABLE_SELECTOR} tbody tr").all()
        if not rows:
            return None

        results = []
        for row in rows[:10]:  # cap at 10 rows per search
            try:
                cells = row.locator("td").all()
                cell_texts = [c.inner_text().strip() for c in cells]
                if not cell_texts:
                    continue
                # Best-effort extraction from visible columns:
                # typical order: entity name, entity number, status, type, city
                results.append({
                    "entityName": cell_texts[0] if len(cell_texts) > 0 else "",
                    "entityNumber": cell_texts[1] if len(cell_texts) > 1 else "",
                    "status": cell_texts[2] if len(cell_texts) > 2 else "",
                    "entityType": cell_texts[3] if len(cell_texts) > 3 else "",
                    "address": cell_texts[4] if len(cell_texts) > 4 else "",
                })
            except Exception:
                continue

        if not results:
            return None

        return {"results": results}
    except Exception:
        return None


def _click_first_result_and_get_detail(page, entity_name: str, log) -> dict | None:
    """Click the first table row and read the detail panel."""
    try:
        first_row = page.locator(f"{_RESULTS_TABLE_SELECTOR} tbody tr").first
        first_row.click(timeout=5_000)

        # Wait for a detail panel to appear — look for characteristic content
        detail_panel = page.locator(
            '[class*="detail"], [class*="panel"], [role="dialog"], [aria-label*="detail"]'
        )
        detail_panel.wait_for(state="visible", timeout=10_000)

        detail_text = detail_panel.inner_text()
        return _parse_detail_panel_text(detail_text, entity_name)
    except Exception as e:
        log.debug("Detail panel not available for '%s': %s", entity_name, e)
        return None


def _parse_detail_panel_text(text: str, entity_name: str) -> dict:
    """Parse plain text from a detail panel into a partial entity record.

    The field layout is approximate — confirmed by live inspection.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    def _find_after(label: str) -> str:
        for i, line in enumerate(lines):
            if label.lower() in line.lower() and i + 1 < len(lines):
                return lines[i + 1]
        return ""

    return {
        "entityName": _find_after("Entity Name") or entity_name,
        "entityNumber": _find_after("Entity Number") or _find_after("File Number"),
        "entityType": _find_after("Entity Type") or _find_after("Filing Type"),
        "status": _find_after("Status"),
        "initialFilingDate": _find_after("Filing Date") or _find_after("Formation Date"),
        "registeredOffice": {
            "addressLine1": _find_after("Office Address") or _find_after("Registered Address"),
        },
    }


def _merge_search_and_detail(
    search_data: dict, detail_dict: dict, entity_name: str
) -> dict | None:
    """Merge search result row with detail panel data, preferring detail."""
    # Use the parser's logic for both halves
    search_records = parse_search_results(search_data)
    base = search_records[0] if search_records else {}

    # Build a mock "filing detail" response from the parsed panel text
    from countyiq.lib.parsers.pa_dos_entities import _parse_date, _build_source_url

    entity_number = detail_dict.get("entityNumber") or base.get("entity_number", "")
    reg_office = detail_dict.get("registeredOffice") or {}
    office_addr = reg_office.get("addressLine1", "") or base.get("office_address", "")

    merged = {
        "entity_name": detail_dict.get("entityName") or base.get("entity_name", entity_name),
        "entity_number": entity_number or base.get("entity_number", ""),
        "entity_type": detail_dict.get("entityType") or base.get("entity_type", ""),
        "status": detail_dict.get("status") or base.get("status", ""),
        "formation_date": (
            _parse_date(detail_dict.get("initialFilingDate"))
            or base.get("formation_date")
        ),
        "registered_agent_name": base.get("registered_agent_name", ""),
        "registered_agent_address": base.get("registered_agent_address", ""),
        "office_address": office_addr,
        "officers": base.get("officers", []),
        "source_url": _build_source_url(entity_number) if entity_number else base.get("source_url", ""),
    }
    return merged


def _safe_filename(name: str) -> str:
    """Convert an entity name to a safe filename fragment."""
    return re.sub(r"[^a-z0-9]", "_", name.lower())[:40]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_pending_entity_names(database: DatabaseResource) -> list[str]:
    """Return unique business entity names from staging.parcels that haven't
    been looked up in the last 7 days."""
    rows = database.execute(
        r"""
        SELECT DISTINCT p.owner_full
        FROM staging.parcels p
        WHERE p.valid_to IS NULL
          AND p.owner_full ~* %s
          AND NOT EXISTS (
              SELECT 1
              FROM staging.corporate_entities ce
              WHERE ce.entity_name = p.owner_full
                AND ce.valid_to IS NULL
                AND ce.valid_from > NOW() - INTERVAL '7 days'
          )
        ORDER BY p.owner_full
        """,
        (
            r"(LLC|L\.L\.C|INC|CORP|LP|L\.P|LTD|TRUST|PARTNERS|ASSOCIATES|"
            r"HOLDINGS|ENTERPRISES|PROPERTIES|GROUP|VENTURES|CAPITAL|INVESTMENTS)",
        ),
    )
    return [row[0] for row in rows if row and row[0]]


def _get_current_count(database: DatabaseResource) -> int:
    rows = database.execute(
        "SELECT COUNT(*) FROM staging.corporate_entities WHERE valid_to IS NULL"
    )
    return rows[0][0] if rows else 0


# ---------------------------------------------------------------------------
# Asset check
# ---------------------------------------------------------------------------

pa_dos_entities_record_count = make_row_count_check(
    pa_dos_entities,
    table="corporate_entities",
    threshold_fn=lambda: get_county_config().pa_dos_min_records,
    severity=AssetCheckSeverity.WARN,
    metadata_key="current_records",
    name="pa_dos_entities_record_count",
)
