"""PA Open Data Portal (SODA API) → staging.pa_open_data.

Source: https://data.pa.gov/
Starting dataset: Registered Businesses in PA Current by County (xvd7-5r2c)
Records: ~2,000+ York County businesses
Schedule: Monthly (1st of month, 05:00) via bulk_refresh job
"""

import json
import time

import requests
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
from countyiq.lib.parsers.pa_open_data import parse_soda_records, EXPECTED_BUSINESS_FIELDS
from countyiq.lib.scd import scd2_upsert
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

PAGE_SIZE = 10000  # SODA max is 50,000; 10K is a safe default
REQUEST_TIMEOUT = 120
MAX_RETRIES = 3
RETRY_BACKOFF = 5  # seconds, multiplied by attempt number

KEY_COLUMNS = ["dataset_id", "record_id"]
VALUE_COLUMNS = ["data"]


def _fetch_page(url: str, attempt: int = 1) -> list[dict]:
    """Fetch a single SODA API page with retry on 5xx errors."""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if attempt < MAX_RETRIES and e.response is not None and e.response.status_code >= 500:
            wait = RETRY_BACKOFF * attempt
            time.sleep(wait)
            return _fetch_page(url, attempt + 1)
        raise


def _fetch_all_pages(
    base_url: str,
    dataset_id: str,
    filter_field: str,
    filter_value: str,
    context,
) -> list[dict]:
    """Paginate through SODA API using $limit/$offset and return all records."""
    all_records: list[dict] = []
    offset = 0
    while True:
        url = (
            f"{base_url}/{dataset_id}.json"
            f"?{filter_field}={filter_value}"
            f"&$select=*,:id"
            f"&$limit={PAGE_SIZE}"
            f"&$offset={offset}"
            f"&$order=:id"
        )
        context.log.info(f"Fetching dataset {dataset_id} at offset {offset}")
        page = _fetch_page(url)
        all_records.extend(page)
        context.log.info(f"  Got {len(page)} records (total: {len(all_records)})")

        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    return all_records


@asset(
    group_name="bulk",
    description="PA Open Data Portal datasets → staging.pa_open_data",
    kinds={"postgres", "api"},
)
def pa_open_data(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch PA Open Data datasets via SODA API, parse, and SCD2 upsert."""

    county = get_county_config()
    total_records = 0
    total_inserted = 0
    total_expired = 0
    total_unchanged = 0
    datasets_processed = 0

    for dataset_id, filter_field, filter_value, record_id_field in county.soda_datasets:
        context.log.info(f"Processing dataset {dataset_id} (filter: {filter_field}={filter_value})")

        # 1. Fetch all pages
        raw_records = _fetch_all_pages(
            county.soda_base_url,
            dataset_id,
            filter_field,
            filter_value,
            context,
        )
        context.log.info(f"Total records fetched for {dataset_id}: {len(raw_records)}")

        # 2. Archive raw JSON to S3
        s3.archive(
            f"{county.s3_prefix}/bulk/pa_open_data/{dataset_id}",
            raw_records,
            filename="records.json",
        )

        # 3. Parse
        parsed = parse_soda_records(raw_records, dataset_id, record_id_field)
        context.log.info(f"Parsed {len(parsed)} records for {dataset_id}")

        if not parsed:
            context.log.warning(f"No records parsed for {dataset_id} — skipping upsert")
            continue

        # 3b. Truncation guard
        if len(parsed) < county.soda_min_records:
            raise RuntimeError(
                f"Only {len(parsed)} records parsed for dataset {dataset_id} "
                f"(expected >= {county.soda_min_records}). "
                f"Possible truncated response — aborting."
            )

        # 4. SCD2 upsert to staging.pa_open_data
        cur = database.cursor()
        try:
            stats = scd2_upsert(
                cursor=cur,
                schema="staging",
                table="pa_open_data",
                records=parsed,
                key_columns=KEY_COLUMNS,
                value_columns=VALUE_COLUMNS,
            )
        finally:
            cur.close()

        total_records += len(parsed)
        total_inserted += stats["inserted"]
        total_expired += stats["expired"]
        total_unchanged += stats["unchanged"]
        datasets_processed += 1

    return MaterializeResult(
        metadata={
            "datasets_processed": MetadataValue.int(datasets_processed),
            "record_count": MetadataValue.int(total_records),
            "inserted": MetadataValue.int(total_inserted),
            "expired": MetadataValue.int(total_expired),
            "unchanged": MetadataValue.int(total_unchanged),
        }
    )


@asset_check(asset=pa_open_data)
def pa_open_data_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.pa_open_data has at least one current record."""
    result = database.execute(
        "SELECT COUNT(*) FROM staging.pa_open_data WHERE valid_to IS NULL"
    )
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )


@asset_check(asset=pa_open_data)
def pa_open_data_row_count_delta(database: DatabaseResource) -> AssetCheckResult:
    """Verify current record count hasn't dropped by more than 50%."""
    result = database.execute("""
        WITH current AS (
            SELECT COUNT(*) AS cnt FROM staging.pa_open_data WHERE valid_to IS NULL
        ),
        historical AS (
            SELECT COUNT(*) AS cnt FROM staging.pa_open_data WHERE valid_to IS NOT NULL
        )
        SELECT current.cnt, historical.cnt FROM current, historical
    """)
    current_count = result[0][0] if result else 0
    historical_count = result[0][1] if result else 0
    total_ever = current_count + historical_count

    # Skip check on first run (no historical data)
    if total_ever == 0 or historical_count == 0:
        return AssetCheckResult(
            passed=True,
            severity=AssetCheckSeverity.WARN,
            metadata={"note": MetadataValue.text("First run — no historical baseline")},
        )

    # If current is less than 50% of what we've ever seen, flag it
    passed = current_count >= (total_ever * 0.25)
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={
            "current_count": MetadataValue.int(current_count),
            "historical_expired": MetadataValue.int(historical_count),
        },
    )


@asset_check(asset=pa_open_data)
def pa_open_data_schema_drift() -> AssetCheckResult:
    """Verify the SODA API still returns expected fields for the businesses dataset."""
    county = get_county_config()
    # Check the first configured dataset
    if not county.soda_datasets:
        return AssetCheckResult(
            passed=True,
            severity=AssetCheckSeverity.WARN,
            metadata={"note": MetadataValue.text("No datasets configured")},
        )

    dataset_id, filter_field, filter_value, _ = county.soda_datasets[0]
    try:
        url = (
            f"{county.soda_base_url}/{dataset_id}.json"
            f"?{filter_field}={filter_value}&$limit=1"
        )
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        records = resp.json()
        if not records:
            return AssetCheckResult(
                passed=False,
                severity=AssetCheckSeverity.WARN,
                metadata={"error": MetadataValue.text("Empty response from SODA API")},
            )
        actual_fields = set(records[0].keys())
        missing = EXPECTED_BUSINESS_FIELDS - actual_fields
        return AssetCheckResult(
            passed=len(missing) == 0,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "missing_fields": MetadataValue.text(str(missing) if missing else "none"),
                "sample_fields": MetadataValue.text(str(sorted(actual_fields)[:10])),
            },
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
