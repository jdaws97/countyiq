"""PLCB liquor licenses bulk CSV → staging.plcb_licenses.

Source: https://plcbplus.pa.gov/pub/LicenseExport.aspx
Records: ~1,400 licenses per county (filtered from statewide CSV)
Schedule: Monthly (1st of month, 05:00)
"""

import csv as csv_mod
from io import StringIO

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
from countyiq.lib.parsers.plcb import parse_plcb_csv, EXPECTED_HEADERS
from countyiq.lib.scd import scd2_upsert
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

# PLCB CSV URL is statewide (same for all PA counties)
PLCB_CSV_URL = "https://plcbplus.pa.gov/pub/LicenseExport.aspx"

KEY_COLUMNS = ["lid"]
VALUE_COLUMNS = [
    "license_number",
    "license_type",
    "status",
    "licensee",
    "premises_name",
    "premises_address",
    "premises_mailing_address",
    "premises_owner",
    "premises_manager",
    "municipality",
    "last_issue_date",
    "expiration_date",
    "source_url",
]


@asset(
    group_name="bulk",
    description=f"PLCB liquor licenses for {get_county_config().name} → staging.plcb_licenses",
    kinds={"postgres", "csv"},
)
def plcb_licenses(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Download PLCB CSV, filter to configured county, SCD2 upsert."""

    # 1. Download CSV
    context.log.info(f"Downloading PLCB CSV from {PLCB_CSV_URL}")
    resp = requests.get(PLCB_CSV_URL, timeout=120)
    resp.raise_for_status()
    csv_text = resp.text
    context.log.info(f"Downloaded {len(csv_text)} characters")

    # 2. Archive raw CSV to S3 (skipped locally if no AWS creds)
    county = get_county_config()
    s3.archive(f"{county.s3_prefix}/bulk/plcb", csv_text, filename="licenses.csv")

    # 3. Parse and filter to county
    records = parse_plcb_csv(csv_text, county_filter=county.plcb_filter)
    for rec in records:
        rec["source_url"] = PLCB_CSV_URL
    context.log.info(f"Parsed {len(records)} {county.name} license records")

    if not records:
        context.log.warning(f"No {county.name} records found — skipping upsert")
        return MaterializeResult(
            metadata={"record_count": MetadataValue.int(0)}
        )

    # 3b. Guard against truncated downloads
    if len(records) < county.plcb_min_records:
        raise RuntimeError(
            f"Only {len(records)} {county.name} records parsed "
            f"(expected >= {county.plcb_min_records}). "
            f"Possible truncated download — aborting to prevent mass expiration."
        )

    # 4. SCD2 upsert to staging.plcb_licenses
    cur = database.cursor()
    try:
        stats = scd2_upsert(
            cursor=cur,
            schema="staging",
            table="plcb_licenses",
            records=records,
            key_columns=KEY_COLUMNS,
            value_columns=VALUE_COLUMNS,
        )
    finally:
        cur.close()

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(len(records)),
            "inserted": MetadataValue.int(stats["inserted"]),
            "expired": MetadataValue.int(stats["expired"]),
            "unchanged": MetadataValue.int(stats["unchanged"]),
        }
    )


@asset_check(asset=plcb_licenses)
def plcb_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.plcb_licenses has at least one current record."""
    result = database.execute(
        "SELECT COUNT(*) FROM staging.plcb_licenses WHERE valid_to IS NULL"
    )
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )


@asset_check(asset=plcb_licenses)
def plcb_no_schema_drift() -> AssetCheckResult:
    """Verify PLCB CSV headers haven't changed."""
    try:
        with requests.get(PLCB_CSV_URL, timeout=30, stream=True) as resp:
            resp.raise_for_status()
            # Read just the first line (header), strip BOM if present
            first_line = next(resp.iter_lines(decode_unicode=True)).lstrip("\ufeff")
        reader = csv_mod.reader(StringIO(first_line))
        actual_headers = {h.strip() for h in next(reader)}
        missing = EXPECTED_HEADERS - actual_headers
        extra = actual_headers - EXPECTED_HEADERS
        passed = len(missing) == 0
        return AssetCheckResult(
            passed=passed,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "missing_headers": MetadataValue.text(str(missing) if missing else "none"),
                "extra_headers": MetadataValue.text(str(extra) if extra else "none"),
            },
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
    except StopIteration:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text("Empty response from PLCB CSV endpoint")},
        )
