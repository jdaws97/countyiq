"""Tax Claim Bureau delinquent tax listing → staging.tax_claims.

Source: York County Tax Claim Bureau PDF
URL: /DocumentCenter/View/1911/Delinquent-Tax-Claim-Listing-PDF
Records: ~9,000 delinquent parcels (~37K authority-year rows)
Schedule: Weekly (Sunday, bulk_refresh job via group_name="bulk")
"""

import io
from datetime import date

import pdfplumber
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
from countyiq.lib.parsers.tax_claims import parse_tax_claims_text
from countyiq.lib.scd import scd2_upsert
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

REQUEST_TIMEOUT = 120

KEY_COLUMNS = ["pidn", "unit_suffix", "tax_year", "authority_name"]

VALUE_COLUMNS = [
    "parcel_id_raw",
    "tax_district_code",
    "tax_district_name",
    "owner_name",
    "property_address",
    "tax_owed",
    "penalty_owed",
    "interest_owed",
    "fees_owed",
    "tax_paid",
    "penalty_paid",
    "interest_paid",
    "fees_paid",
    "total",
    "report_date",
]


@asset(
    group_name="bulk",
    description="Delinquent tax claims from York County Tax Claim Bureau PDF → staging.tax_claims",
    kinds={"postgres", "pdf"},
)
def tax_claims(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Download tax claim PDF, parse all pages, SCD2 upsert."""
    county = get_county_config()

    # 1. Download PDF
    context.log.info(f"Downloading tax claim PDF from {county.tax_claims_pdf_url}")
    resp = requests.get(county.tax_claims_pdf_url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    pdf_bytes = resp.content
    context.log.info(f"Downloaded {len(pdf_bytes)} bytes")

    # 2. Archive raw PDF to S3
    s3.archive(f"{county.s3_prefix}/bulk/tax_claims", pdf_bytes, filename="listing.pdf")

    # 3. Extract text page-by-page into a temp file to avoid holding
    #    the entire PDF text in memory (200+ pages can exceed 1GB RAM)
    import tempfile, os as _os
    context.log.info("Extracting text from PDF pages (streaming to disk)...")
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            total_pages = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                tmp.write((page.extract_text() or "") + "\n")
                if (i + 1) % 100 == 0:
                    context.log.info(f"  Extracted {i + 1}/{total_pages} pages")
            context.log.info(f"Extracted text from {total_pages} pages")
        tmp.close()
        # Free the PDF from memory before parsing
        del pdf_bytes

        # 4. Parse from the temp file
        with open(tmp.name, "r") as f:
            text = f.read()
        records = parse_tax_claims_text(text)
        del text  # free the string
        context.log.info(f"Parsed {len(records)} tax claim records")
    finally:
        _os.unlink(tmp.name)

    if not records:
        context.log.warning("No tax claim records parsed — skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    # 4b. Truncation guard
    unique_parcels = len({r["parcel_id_raw"] for r in records})
    if unique_parcels < county.tax_claims_min_records:
        raise RuntimeError(
            f"Only {unique_parcels} unique parcels parsed "
            f"(expected >= {county.tax_claims_min_records}). "
            f"Possible truncated or changed PDF — aborting."
        )

    # 5. SCD2 upsert
    cur = database.cursor()
    try:
        stats = scd2_upsert(
            cursor=cur,
            schema="staging",
            table="tax_claims",
            records=records,
            key_columns=KEY_COLUMNS,
            value_columns=VALUE_COLUMNS,
        )
    finally:
        cur.close()

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(len(records)),
            "unique_parcels": MetadataValue.int(unique_parcels),
            "report_date": MetadataValue.text(str(records[0]["report_date"])),
            "inserted": MetadataValue.int(stats["inserted"]),
            "expired": MetadataValue.int(stats["expired"]),
            "unchanged": MetadataValue.int(stats["unchanged"]),
        }
    )


@asset_check(asset=tax_claims)
def tax_claims_record_count(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.tax_claims has enough current records."""
    county = get_county_config()
    result = database.execute(
        "SELECT COUNT(DISTINCT pidn) FROM staging.tax_claims WHERE valid_to IS NULL"
    )
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count >= county.tax_claims_min_records,
        severity=AssetCheckSeverity.ERROR,
        metadata={
            "unique_pidns": MetadataValue.int(count),
            "threshold": MetadataValue.int(county.tax_claims_min_records),
        },
    )


@asset_check(asset=tax_claims)
def tax_claims_report_freshness(database: DatabaseResource) -> AssetCheckResult:
    """Verify report_date is within 90 days (catches stale PDF URL)."""
    result = database.execute(
        "SELECT MAX(report_date) FROM staging.tax_claims WHERE valid_to IS NULL"
    )
    if not result or result[0][0] is None:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text("No records found")},
        )
    report_date = result[0][0]
    age_days = (date.today() - report_date).days
    return AssetCheckResult(
        passed=age_days <= 90,
        severity=AssetCheckSeverity.WARN,
        metadata={
            "report_date": MetadataValue.text(str(report_date)),
            "age_days": MetadataValue.int(age_days),
        },
    )
