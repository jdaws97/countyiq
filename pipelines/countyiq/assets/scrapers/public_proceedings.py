"""Public proceedings scraper — downloads meeting minute PDFs from municipality websites.

Strategy:
  - Read municipality_websites from county config (body_name, minutes_url, proceeding_type)
  - For each municipality:
      1. GET the minutes page via simple HTTP and extract PDF links
      2. If 0 PDFs found, retry via headless Playwright (handles JS-rendered sites
         like CivicEngage AgendaCenter, CourseVector, Wix, GoDaddy, etc.)
  - For each new PDF (not already in staging.public_proceedings):
      - Download the PDF
      - Archive binary to R2
      - Insert a metadata row into staging.public_proceedings
  - Throttle 0.5–1 second between requests
  - Return MaterializeResult with counts
"""

import hashlib
import random
import re
import time

import requests
from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.county_config import get_county_config
from countyiq.lib.pdf_text import extract_text_from_pdf_bytes
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

# How long to wait for JS-rendered content before grabbing the DOM
_PLAYWRIGHT_NAV_TIMEOUT_MS = 20000
_PLAYWRIGHT_SETTLE_MS = 2000


class _PlaywrightFetcher:
    """Lazy headless-browser fetcher for JS-rendered sites.

    Reuses a single Chromium instance across all municipalities to avoid
    the ~1s startup cost per page. Lazy-imports playwright so the scraper
    can run without it installed if every site uses static HTML.
    """

    def __init__(self, log):
        self._log = log
        self._playwright = None
        self._browser = None
        self._unavailable = False

    def _ensure_browser(self) -> bool:
        if self._unavailable:
            return False
        if self._browser is not None:
            return True
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self._log.warning(
                "playwright not installed — skipping JS-rendered fallback. "
                "Install with: uv pip install playwright && playwright install chromium"
            )
            self._unavailable = True
            return False
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._log.info("Playwright Chromium launched for JS fallback")
            return True
        except Exception as exc:
            self._log.warning("Failed to launch Playwright Chromium: %s", exc)
            self._unavailable = True
            return False

    def fetch_html(self, url: str) -> str | None:
        """Fetch the fully-rendered HTML for a URL, or None on failure."""
        if not self._ensure_browser():
            return None
        try:
            page = self._browser.new_page(user_agent=_HEADERS["User-Agent"])
            try:
                page.goto(url, timeout=_PLAYWRIGHT_NAV_TIMEOUT_MS, wait_until="domcontentloaded")
                page.wait_for_timeout(_PLAYWRIGHT_SETTLE_MS)
                return page.content()
            finally:
                page.close()
        except Exception as exc:
            self._log.warning("Playwright fetch failed for %s: %s", url, exc)
            return None

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._browser = None
        self._playwright = None


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
                "pdfs_via_playwright": MetadataValue.int(0),
                "pdfs_new": MetadataValue.int(0),
                "pdfs_skipped_duplicate": MetadataValue.int(0),
                "pdfs_null_date": MetadataValue.int(0),
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
    pdfs_null_date = 0
    pdfs_archived = 0
    pdfs_via_playwright = 0
    errors = 0

    playwright_fetcher = _PlaywrightFetcher(log)

    for body_name, minutes_url, proceeding_type in municipality_websites:
        log.info("Scraping '%s' at %s", body_name, minutes_url)

        # --- Fetch the minutes listing page (simple HTTP first) ---
        html = None
        try:
            resp = requests.get(
                minutes_url,
                headers=_HEADERS,
                timeout=_REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:
            log.warning(
                "Simple HTTP fetch failed for '%s' (%s): %s — will try Playwright",
                body_name, minutes_url, exc,
            )

        # --- Parse PDF links ---
        pdf_links = extract_pdf_links(html or "", minutes_url)

        # --- Playwright fallback for sites that returned 0 PDFs ---
        if not pdf_links:
            log.info(
                "'%s': simple HTTP found 0 PDFs — trying Playwright fallback",
                body_name,
            )
            rendered_html = playwright_fetcher.fetch_html(minutes_url)
            if rendered_html:
                pdf_links = extract_pdf_links(rendered_html, minutes_url)
                if pdf_links:
                    pdfs_via_playwright += len(pdf_links)
                    log.info(
                        "'%s': Playwright fallback found %d PDFs",
                        body_name, len(pdf_links),
                    )

        if not pdf_links and html is None:
            # Both fetchers failed entirely
            errors += 1
            _throttle()
            continue

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
                log.info(
                    "'%s': no date parsed from '%s' (link_text=%r) — will insert with NULL date",
                    body_name, filename, link_text,
                )
                pdfs_null_date += 1

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

            # --- Content-hash dedup (catches same-URL overwrites) ---
            content_hash = hashlib.sha256(pdf_bytes).hexdigest()
            if _content_hash_exists(database, content_hash):
                log.debug(
                    "'%s': content hash match for '%s' — skipping",
                    body_name, filename,
                )
                pdfs_skipped_duplicate += 1
                continue

            # --- Archive to R2 ---
            safe_body = _safe_name(body_name)
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

            # --- Extract text for local Pass 0 use ---
            raw_text = None
            try:
                raw_text = extract_text_from_pdf_bytes(pdf_bytes) or None
            except Exception as exc:
                log.warning(
                    "'%s': PDF text extraction failed for '%s': %s",
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
                    content_hash=content_hash,
                    raw_text=raw_text,
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

    playwright_fetcher.close()

    log.info(
        "Scrape complete: %d PDFs found (%d via Playwright), %d new, %d duplicates, "
        "%d null date, %d archived, %d errors",
        pdfs_found, pdfs_via_playwright, pdfs_new, pdfs_skipped_duplicate,
        pdfs_null_date, pdfs_archived, errors,
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "municipalities_configured": MetadataValue.int(len(municipality_websites)),
            "pdfs_found": MetadataValue.int(pdfs_found),
            "pdfs_via_playwright": MetadataValue.int(pdfs_via_playwright),
            "pdfs_new": MetadataValue.int(pdfs_new),
            "pdfs_skipped_duplicate": MetadataValue.int(pdfs_skipped_duplicate),
            "pdfs_null_date": MetadataValue.int(pdfs_null_date),
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


def _content_hash_exists(database: DatabaseResource, content_hash: str) -> bool:
    """Return True if a PDF with this SHA-256 hash is already stored."""
    rows = database.execute(
        """
        SELECT 1
        FROM staging.public_proceedings
        WHERE content_hash = %s
          AND valid_to IS NULL
        LIMIT 1
        """,
        (content_hash,),
    )
    return bool(rows)


def _insert_proceeding(
    database: DatabaseResource,
    body_name: str,
    meeting_date: str | None,
    proceeding_type: str,
    source_url: str,
    document_url: str,
    content_hash: str | None = None,
    raw_text: str | None = None,
) -> None:
    """Insert a new public proceedings row with SCD2 valid_from."""
    database.execute(
        """
        INSERT INTO staging.public_proceedings
            (body_name, meeting_date, proceeding_type, source_url, document_url,
             content_hash, raw_text, valid_from)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        (body_name, meeting_date, proceeding_type, source_url, document_url,
         content_hash, raw_text),
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
