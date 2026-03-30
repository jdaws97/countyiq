"""Assessment data from iasWorld Public Access portal -> staging.assessment_properties.

Records: ~176K properties scraped via Playwright
Schedule: Weekly (Monday 03:00, scraper_refresh job)
Strategy: Two-tier -- search results sweep + printable summary enrichment
"""

import json
import time

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
from countyiq.lib.parsers.assessment import (
    parid_to_pidn,
    parse_search_results_page,
    get_total_found,
    parse_printable_summary,
)
from countyiq.lib.playwright_utils import browser_context
from countyiq.lib.scd import scd2_upsert
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["pidn"]

VALUE_COLUMNS = [
    "parid", "owner_name", "address", "municipality", "school_district",
    "property_class", "land_use_code", "assessed_land", "assessed_building",
    "assessed_total", "sale_date", "sale_price", "permits",
    "delinquent_taxes", "value_history",
]


@asset(
    group_name="scrapers",
    description=f"{get_county_config().name} assessment data from iasWorld portal -> staging.assessment_properties",
    kinds={"postgres", "playwright"},
)
def assessment_scrape(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Two-tier scrape: search results sweep + detail enrichment."""
    county = get_county_config()

    # Load checkpoint
    checkpoint = _load_checkpoint(database, "assessment")
    tier1_stats = {"inserted": 0, "expired": 0}

    with browser_context() as page:
        _accept_disclaimer(page, county.assessment_url)

        # --- Tier 1: Search results sweep ---
        tier1 = checkpoint.get("tier1", {})
        if tier1.get("status") != "complete":
            context.log.info("Starting Tier 1: search results sweep")
            tier1_results, tier1 = _run_tier1(
                page, context, database, county, tier1
            )

            if not tier1_results:
                context.log.warning("No properties found in Tier 1")
                return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

            # Upsert Tier 1 results (basic fields only, expire_missing=False)
            records_t1 = _prepare_tier1_records(tier1_results)
            cur = database.cursor()
            try:
                tier1_stats = scd2_upsert(
                    cursor=cur,
                    schema="staging",
                    table="assessment_properties",
                    records=records_t1,
                    key_columns=KEY_COLUMNS,
                    value_columns=VALUE_COLUMNS,
                    expire_missing=False,
                )
            finally:
                cur.close()

            # Save Tier 1 checkpoint (only prefixes + counts, NOT full results)
            checkpoint["tier1"] = tier1
            _save_checkpoint(database, "assessment", checkpoint)
        else:
            context.log.info("Tier 1 already complete -- skipping to Tier 2")

        # Load all PARIDs from staging for Tier 2 (works for both fresh + resumed runs)
        tier1_results = _load_tier1_results_from_staging(database)
        if not tier1_results:
            context.log.warning("No properties in staging.assessment_properties")
            return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

        # --- Tier 2: Detail enrichment ---
        tier2 = checkpoint.get("tier2", {})
        enriched_count = _run_tier2(
            page, context, database, s3, county, tier1_results, tier2, checkpoint
        )

    total_count = _get_current_count(database)

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(total_count),
            "tier1_properties": MetadataValue.int(len(tier1_results)),
            "tier2_enriched_this_run": MetadataValue.int(enriched_count),
            "tier1_inserted": MetadataValue.int(tier1_stats.get("inserted", 0)),
            "tier1_expired": MetadataValue.int(tier1_stats.get("expired", 0)),
        }
    )


# ---------------------------------------------------------------------------
# Disclaimer
# ---------------------------------------------------------------------------

def _accept_disclaimer(page, base_url: str):
    """Navigate to search page, accepting disclaimer if shown."""
    page.goto(f"{base_url}search/commonsearch.aspx?mode=realprop")
    if "Disclaimer" in page.url:
        page.get_by_role("button", name="Agree", exact=True).click()
        page.wait_for_load_state("networkidle")


# ---------------------------------------------------------------------------
# Tier 1: Search results sweep
# ---------------------------------------------------------------------------

def _run_tier1(page, context, database, county, tier1_state: dict):
    """Search by prefix, page through results, collect all PARIDs.

    Results are NOT stored in the checkpoint (would be 20+ MB JSONB).
    Only completed prefixes and counts are checkpointed. Results are
    returned in-memory for the current run's Tier 1 upsert.
    """
    completed_prefixes = set(tier1_state.get("completed_prefixes", []))
    all_results = []
    total_found = tier1_state.get("total_properties_found", 0)

    # Get district prefixes from staging.parcels
    prefixes = _get_district_prefixes(database)
    context.log.info(f"Found {len(prefixes)} district prefixes to search")

    for prefix in prefixes:
        if prefix in completed_prefixes:
            continue
        context.log.info(f"Tier 1: searching prefix '{prefix}'")
        refined = _refine_prefix(page, prefix, county, max_depth=6)
        for rp in refined:
            if rp in completed_prefixes:
                continue
            batch = _search_all_pages(page, rp, county)
            all_results.extend(batch)
            total_found += len(batch)
            completed_prefixes.add(rp)
            context.log.info(f"  prefix '{rp}': {len(batch)} results")
        completed_prefixes.add(prefix)

        # Periodic checkpoint (prefixes + counts only, no results)
        tier1_state = {
            "completed_prefixes": list(completed_prefixes),
            "total_properties_found": total_found,
        }

    tier1_state["status"] = "complete"
    return all_results, tier1_state


def _get_district_prefixes(database: DatabaseResource) -> list[str]:
    """Get unique 2-char district prefixes from staging.parcels PIDNs."""
    rows = database.execute(
        "SELECT DISTINCT SUBSTRING(pidn FROM 1 FOR 2) AS prefix "
        "FROM staging.parcels WHERE valid_to IS NULL ORDER BY prefix"
    )
    return [r[0] for r in rows if r[0]]


def _refine_prefix(page, prefix: str, county, max_depth: int = 6) -> list[str]:
    """If prefix yields >500 results, subdivide into longer prefixes.

    max_depth prevents infinite recursion on extremely dense data ranges.
    """
    if len(prefix) >= max_depth:
        # At depth limit -- accept truncation, log warning
        return [prefix]

    total = _search_and_count(page, prefix, county)
    if total <= 500:
        return [prefix]

    sub_prefixes = []
    for char in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        sub = prefix + char
        sub_total = _search_and_count(page, sub, county)
        if sub_total == 0:
            continue
        if sub_total <= 500:
            sub_prefixes.append(sub)
        else:
            sub_prefixes.extend(_refine_prefix(page, sub, county, max_depth))
    return sub_prefixes


def _search_and_count(page, prefix: str, county) -> int:
    """Perform a search and return the total found count."""
    _navigate_to_search(page, county.assessment_url)
    page.get_by_role("textbox", name="Parcel:").fill(prefix)
    page.get_by_label("Results/page:").select_option("50")
    page.get_by_role("button", name="Search").click()
    page.wait_for_load_state("networkidle")
    time.sleep(county.assessment_throttle_seconds)
    return get_total_found(page.content())


def _search_all_pages(page, prefix: str, county) -> list[dict]:
    """Search a prefix and page through all results (max 500 = 10 pages of 50)."""
    _navigate_to_search(page, county.assessment_url)
    page.get_by_role("textbox", name="Parcel:").fill(prefix)
    page.get_by_label("Results/page:").select_option("50")
    page.get_by_role("button", name="Search").click()
    page.wait_for_load_state("networkidle")
    time.sleep(county.assessment_throttle_seconds)

    all_rows = []
    for page_num in range(10):  # max 10 pages of 50 = 500
        html = page.content()
        rows = parse_search_results_page(html)
        if not rows:
            break
        all_rows.extend(rows)

        # Check for next page link
        next_link = page.get_by_text("Next >>")
        if not next_link.count():
            break
        next_link.click()
        page.wait_for_load_state("networkidle")
        time.sleep(county.assessment_throttle_seconds)

    return all_rows


def _navigate_to_search(page, base_url: str):
    """Navigate to search page, handle disclaimer if it reappears."""
    page.goto(f"{base_url}search/commonsearch.aspx?mode=realprop")
    if "Disclaimer" in page.url:
        page.get_by_role("button", name="Agree", exact=True).click()
        page.wait_for_load_state("networkidle")


# ---------------------------------------------------------------------------
# Tier 2: Detail enrichment
# ---------------------------------------------------------------------------

def _run_tier2(page, context, database, s3, county, tier1_results, tier2_state, checkpoint):
    """Visit detail pages for each property, extract full data."""
    last_parid = tier2_state.get("last_completed_parid", "")
    enriched = tier2_state.get("properties_enriched", 0)
    max_per_run = county.assessment_max_per_run
    processed_this_run = 0

    # Build dict lookup for O(1) access (instead of O(n) per property)
    t1_by_parid = {r["parid"]: r for r in tier1_results}

    # Sort PARIDs for deterministic ordering
    sorted_parids = sorted(t1_by_parid.keys())

    # Resume from checkpoint
    start_idx = 0
    if last_parid:
        for i, p in enumerate(sorted_parids):
            if p > last_parid:
                start_idx = i
                break
        else:
            # All done
            context.log.info("Tier 2 already complete")
            tier2_state["status"] = "complete"
            checkpoint["tier2"] = tier2_state
            _save_checkpoint(database, "assessment", checkpoint)
            return 0

    context.log.info(
        f"Tier 2: starting at index {start_idx}/{len(sorted_parids)}, "
        f"max {max_per_run} this run"
    )

    session_count = 0
    batch_records = []

    for parid in sorted_parids[start_idx:]:
        if processed_this_run >= max_per_run:
            break

        # Refresh session periodically
        if session_count >= county.assessment_session_refresh:
            context.log.info("Refreshing browser session")
            _accept_disclaimer(page, county.assessment_url)
            session_count = 0

        try:
            detail = _scrape_property_detail(page, parid, county)
            if detail:
                # Merge Tier 1 basic data with Tier 2 detail
                t1_data = t1_by_parid.get(parid, {})
                record = _merge_record(parid, t1_data, detail)
                batch_records.append(record)
        except Exception as e:
            context.log.warning(f"Failed to scrape {parid}: {e}")

        enriched += 1
        processed_this_run += 1
        session_count += 1

        # Update checkpoint every 10 properties
        if processed_this_run % 10 == 0:
            tier2_state["last_completed_parid"] = parid
            tier2_state["properties_enriched"] = enriched
            checkpoint["tier2"] = tier2_state
            _save_checkpoint(database, "assessment", checkpoint)

    # Final checkpoint
    if sorted_parids[start_idx:] and processed_this_run > 0:
        last = sorted_parids[min(start_idx + processed_this_run - 1, len(sorted_parids) - 1)]
        tier2_state["last_completed_parid"] = last
        tier2_state["properties_enriched"] = enriched
        if start_idx + processed_this_run >= len(sorted_parids):
            tier2_state["status"] = "complete"
        checkpoint["tier2"] = tier2_state
        _save_checkpoint(database, "assessment", checkpoint)

    # Upsert enriched records
    if batch_records:
        cur = database.cursor()
        try:
            scd2_upsert(
                cursor=cur,
                schema="staging",
                table="assessment_properties",
                records=batch_records,
                key_columns=KEY_COLUMNS,
                value_columns=VALUE_COLUMNS,
                expire_missing=False,
            )
        finally:
            cur.close()

        # Archive to S3
        s3.archive(
            f"{county.s3_prefix}/scrapers/assessment",
            batch_records,
            filename="enriched_batch.json",
        )

    context.log.info(f"Tier 2: enriched {processed_this_run} properties this run")
    return processed_this_run


def _scrape_property_detail(page, parid: str, county) -> dict | None:
    """Search for exact PARID, navigate to Printable Summary, parse."""
    _navigate_to_search(page, county.assessment_url)
    page.get_by_role("textbox", name="Parcel:").fill(parid)
    page.get_by_role("button", name="Search").click()
    page.wait_for_load_state("networkidle")
    time.sleep(county.assessment_throttle_seconds)

    # If exact match, portal goes straight to detail page (1 of 1)
    # If multiple results, we land on search results — click first row
    if "Datalet" not in page.url:
        result_rows = page.query_selector_all("tr[onclick]")
        if not result_rows:
            return None
        result_rows[0].click()
        page.wait_for_load_state("networkidle")
        time.sleep(county.assessment_throttle_seconds)

    # Click Printable Summary (opens popup)
    with page.expect_popup() as popup_info:
        page.get_by_text("Printable Summary").click()
    popup = popup_info.value
    popup.wait_for_load_state("networkidle")
    html = popup.content()
    popup.close()

    time.sleep(county.assessment_throttle_seconds)
    return parse_printable_summary(html)


# ---------------------------------------------------------------------------
# Record merging
# ---------------------------------------------------------------------------

def _prepare_tier1_records(tier1_results: list[dict]) -> list[dict]:
    """Convert Tier 1 search results to staging records with PIDN."""
    records = []
    for r in tier1_results:
        pidn = parid_to_pidn(r["parid"])
        if not pidn:
            continue
        records.append({
            "pidn": pidn,
            "parid": r["parid"],
            "owner_name": r.get("owner_name"),
            "address": r.get("address"),
            "property_class": r.get("property_class"),
            # Tier 2 fields default to None
            "municipality": None,
            "school_district": None,
            "land_use_code": None,
            "assessed_land": None,
            "assessed_building": None,
            "assessed_total": None,
            "sale_date": None,
            "sale_price": None,
            "permits": None,
            "delinquent_taxes": None,
            "value_history": None,
        })
    return records


def _merge_record(parid: str, t1_data: dict, detail: dict) -> dict:
    """Merge Tier 1 basic data with Tier 2 detail data."""
    pidn = parid_to_pidn(parid)
    return {
        "pidn": pidn,
        "parid": parid,
        "owner_name": t1_data.get("owner_name"),
        "address": t1_data.get("address"),
        "property_class": t1_data.get("property_class"),
        "municipality": detail.get("municipality"),
        "school_district": detail.get("school_district"),
        "land_use_code": detail.get("land_use_code"),
        "assessed_land": detail.get("assessed_land"),
        "assessed_building": detail.get("assessed_building"),
        "assessed_total": detail.get("assessed_total"),
        "sale_date": detail.get("sale_date"),
        "sale_price": detail.get("sale_price"),
        "permits": detail.get("permits", []),
        "delinquent_taxes": detail.get("delinquent_taxes", []),
        "value_history": detail.get("value_history", []),
    }


# ---------------------------------------------------------------------------
# Checkpoint (meta.scrape_checkpoints)
# ---------------------------------------------------------------------------

def _load_checkpoint(database: DatabaseResource, source_name: str) -> dict:
    """Load checkpoint from meta.scrape_checkpoints."""
    rows = database.execute(
        "SELECT checkpoint FROM meta.scrape_checkpoints WHERE source_name = %s",
        (source_name,),
    )
    if rows:
        return rows[0][0] or {}
    return {}


def _save_checkpoint(database: DatabaseResource, source_name: str, data: dict):
    """Save checkpoint to meta.scrape_checkpoints (upsert)."""
    cur = database.cursor()
    try:
        cur.execute(
            """
            INSERT INTO meta.scrape_checkpoints (source_name, checkpoint, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (source_name) DO UPDATE
            SET checkpoint = EXCLUDED.checkpoint, updated_at = NOW()
            """,
            (source_name, json.dumps(data, default=str)),
        )
        cur.connection.commit()
    finally:
        cur.close()


def _load_tier1_results_from_staging(database: DatabaseResource) -> list[dict]:
    """Load all PARIDs from staging.assessment_properties for Tier 2 processing.

    This replaces storing Tier 1 results in the checkpoint JSONB (which would
    be 20+ MB for 176K properties). The staging table is the source of truth
    after Tier 1 upsert completes.
    """
    rows = database.execute(
        "SELECT parid, owner_name, address, property_class "
        "FROM staging.assessment_properties WHERE valid_to IS NULL"
    )
    return [
        {"parid": r[0], "owner_name": r[1], "address": r[2], "property_class": r[3]}
        for r in rows if r[0]
    ]


def _get_current_count(database: DatabaseResource) -> int:
    """Get current record count in staging.assessment_properties."""
    rows = database.execute(
        "SELECT COUNT(*) FROM staging.assessment_properties WHERE valid_to IS NULL"
    )
    return rows[0][0] if rows else 0


# ---------------------------------------------------------------------------
# Asset checks
# ---------------------------------------------------------------------------

@asset_check(asset=assessment_scrape)
def assessment_record_count(database: DatabaseResource) -> AssetCheckResult:
    """Verify assessment data is present.

    During backfill: passes if count > 0.
    After backfill: passes if count > assessment_min_records.
    """
    county = get_county_config()
    count = _get_current_count(database)
    checkpoint = _load_checkpoint(database, "assessment")
    tier2_status = checkpoint.get("tier2", {}).get("status", "")

    if tier2_status == "complete":
        passed = count > county.assessment_min_records
        description = f"{count} records (threshold: {county.assessment_min_records})"
    else:
        passed = count > 0
        description = f"{count} records (backfill in progress)"

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR,
        metadata={
            "current_record_count": MetadataValue.int(count),
            "description": MetadataValue.text(description),
        },
    )


@asset_check(asset=assessment_scrape)
def assessment_row_count_delta(database: DatabaseResource) -> AssetCheckResult:
    """Verify record count hasn't dropped by more than 50% vs checkpoint.

    Compares current staging count against the checkpoint's
    total_properties_found (set during Tier 1). This avoids needing
    meta.pipeline_status which the assessment asset doesn't write to.
    """
    count = _get_current_count(database)
    checkpoint = _load_checkpoint(database, "assessment")
    prev = checkpoint.get("tier1", {}).get("total_properties_found", 0)

    if prev == 0:
        return AssetCheckResult(passed=True, severity=AssetCheckSeverity.WARN)

    delta_pct = abs(count - prev) / prev
    return AssetCheckResult(
        passed=delta_pct < 0.5,
        severity=AssetCheckSeverity.ERROR,
        metadata={
            "current": MetadataValue.int(count),
            "tier1_total": MetadataValue.int(prev),
            "delta_pct": MetadataValue.float(delta_pct),
        },
    )
