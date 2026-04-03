"""Public proceedings scraper — downloads meeting minute PDFs from municipality websites.

Strategy:
  - Read municipality_websites from county config (body_name, minutes_url, proceeding_type)
  - For each municipality, GET the minutes page and extract PDF links
  - For each new PDF (not already in staging.public_proceedings):
      - Download the PDF
      - Archive binary to R2
      - Insert a metadata row into staging.public_proceedings
  - Throttle 0.5–1 second between requests
  - Return MaterializeResult with counts
"""

import random
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.public_proceedings import (
    classify_proceeding_type,
    extract_pdf_links,
    parse_meeting_date_from_filename,
)
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

# Seconds to wait between HTTP requests (randomised in range)
_THROTTLE_MIN = 0.5
_THROTTLE_MAX = 1.0

# Timeout for individual HTTP requests
_REQUEST_TIMEOUT = 30

# User-agent header to avoid trivial bot blocks
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; CountyIQ/1.0; +https://countyiq.app)"
    )
}


@asset(
    group_name="scrapers",
    description="Download meeting minute PDFs from all York County municipality websites",
    kinds={"postgres", "scraper"},
)
def public_proceedings_scrape(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    county = get_county_config()
    log = context.log

    municipality_websites = county.municipality_websites

    if not municipality_websites:
        log.info(
            "No municipalities configured in county_config.municipality_websites — "
            "returning early with zero counts. Populate the tuple to activate scraping."
        )
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("no_municipalities_configured"),
                "municipalities_configured": MetadataValue.int(0),
                "pdfs_found": MetadataValue.int(0),
                "pdfs_new": MetadataValue.int(0),
                "pdfs_skipped_duplicate": MetadataValue.int(0),
                "pdfs_skipped_no_date": MetadataValue.int(0),
                "pdfs_archived": MetadataValue.int(0),
                "errors": MetadataValue.int(0),
            }
        )

    log.info(
        "Starting public proceedings scrape for %d municipalities",
        len(municipality_websites),
    )

    pdfs_found = 0
    pdfs_new = 0
    pdfs_skipped_duplicate = 0
    pdfs_skipped_no_date = 0
    pdfs_archived = 0
    errors = 0

    for body_name, minutes_url, proceeding_type in municipality_websites:
        log.info("Scraping '%s' at %s", body_name, minutes_url)

        # --- Fetch the minutes listing page ---
        try:
            resp = requests.get(
                minutes_url,
                headers=_HEADERS,
                timeout=_REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            resp.raise_for_status()
        except Exception as exc:
            log.warning(
                "Failed to fetch minutes page for '%s' (%s): %s",
                body_name, minutes_url, exc,
            )
            errors += 1
            _throttle()
            continue

        # --- Parse PDF links ---
        pdf_links = extract_pdf_links(resp.text, minutes_url)
        pdfs_found += len(pdf_links)
        log.info(
            "'%s': found %d PDF link(s)", body_name, len(pdf_links)
        )

        for link in pdf_links:
            document_url = link["url"]
            filename = link["filename"]
            link_text = link["link_text"]

            # --- Resolve meeting date ---
            meeting_date = parse_meeting_date_from_filename(filename)
            if meeting_date is None and link_text:
                # Try extracting a date from the visible link text
                meeting_date = parse_meeting_date_from_filename(link_text)

            if meeting_date is None:
                log.warning(
                    "'%s': could not parse meeting date from '%s' (link_text=%r) — skipping",
                    body_name, filename, link_text,
                )
                pdfs_skipped_no_date += 1
                continue

            # --- Resolve proceeding type (override from filename if more specific) ---
            classified = classify_proceeding_type(filename, link_text)
            resolved_type = (
                classified if classified != "unknown" else proceeding_type
            )

            # --- Deduplication check ---
            if _already_exists(database, body_name, document_url):
                log.debug(
                    "'%s': duplicate '%s' — skipping", body_name, document_url
                )
                pdfs_skipped_duplicate += 1
                continue

            # --- Download the PDF ---
            try:
                pdf_resp = requests.get(
                    document_url,
                    headers=_HEADERS,
                    timeout=_REQUEST_TIMEOUT,
                    allow_redirects=True,
                )
                pdf_resp.raise_for_status()
                pdf_bytes = pdf_resp.content
            except Exception as exc:
                log.warning(
                    "'%s': failed to download '%s': %s",
                    body_name, document_url, exc,
                )
                errors += 1
                _throttle()
                continue

            # --- Archive to R2 ---
            safe_body = _safe_name(body_name)
            r2_path = (
                f"{county.s3_prefix}/proceedings/{safe_body}/"
                f"{meeting_date}/{filename}"
            )
            try:
                s3.archive(
                    f"{county.s3_prefix}/proceedings/{safe_body}/{meeting_date}",
                    pdf_bytes,
                    filename=filename,
                )
                pdfs_archived += 1
            except Exception as exc:
                # Archive failure is non-fatal; log and continue to DB insert
                log.warning(
                    "'%s': R2 archive failed for '%s': %s",
                    body_name, filename, exc,
                )

            # --- Insert metadata row into staging.public_proceedings ---
            try:
                _insert_proceeding(
                    database=database,
                    body_name=body_name,
                    meeting_date=meeting_date,
                    proceeding_type=resolved_type,
                    source_url=minutes_url,
                    document_url=document_url,
                )
                pdfs_new += 1
                log.info(
                    "'%s': inserted proceeding %s (%s)",
                    body_name, meeting_date, resolved_type,
                )
            except Exception as exc:
                log.warning(
                    "'%s': DB insert failed for '%s': %s",
                    body_name, document_url, exc,
                )
                errors += 1

            _throttle()

        # Throttle between municipalities too
        _throttle()

    log.info(
        "Scrape complete: %d PDFs found, %d new, %d duplicates, "
        "%d missing date, %d archived, %d errors",
        pdfs_found, pdfs_new, pdfs_skipped_duplicate,
        pdfs_skipped_no_date, pdfs_archived, errors,
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "municipalities_configured": MetadataValue.int(len(municipality_websites)),
            "pdfs_found": MetadataValue.int(pdfs_found),
            "pdfs_new": MetadataValue.int(pdfs_new),
            "pdfs_skipped_duplicate": MetadataValue.int(pdfs_skipped_duplicate),
            "pdfs_skipped_no_date": MetadataValue.int(pdfs_skipped_no_date),
            "pdfs_archived": MetadataValue.int(pdfs_archived),
            "errors": MetadataValue.int(errors),
            "current_records": MetadataValue.int(_get_current_count(database)),
        }
    )


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _already_exists(database: DatabaseResource, body_name: str, document_url: str) -> bool:
    """Return True if this document_url is already in staging.public_proceedings."""
    rows = database.execute(
        """
        SELECT 1
        FROM staging.public_proceedings
        WHERE body_name = %s
          AND document_url = %s
          AND valid_to IS NULL
        LIMIT 1
        """,
        (body_name, document_url),
    )
    return bool(rows)


def _insert_proceeding(
    database: DatabaseResource,
    body_name: str,
    meeting_date: str,
    proceeding_type: str,
    source_url: str,
    document_url: str,
) -> None:
    """Insert a new public proceedings row with SCD2 valid_from."""
    database.execute(
        """
        INSERT INTO staging.public_proceedings
            (body_name, meeting_date, proceeding_type, source_url, document_url, valid_from)
        VALUES (%s, %s, %s, %s, %s, NOW())
        """,
        (body_name, meeting_date, proceeding_type, source_url, document_url),
    )


def _get_current_count(database: DatabaseResource) -> int:
    """Return the count of active public_proceedings rows."""
    rows = database.execute(
        "SELECT COUNT(*) FROM staging.public_proceedings WHERE valid_to IS NULL"
    )
    return rows[0][0] if rows else 0


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _safe_name(name: str) -> str:
    """Convert a municipality/body name to a safe path segment."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _throttle() -> None:
    """Sleep for a random duration between requests."""
    time.sleep(random.uniform(_THROTTLE_MIN, _THROTTLE_MAX))
