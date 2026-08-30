"""Public proceedings scraper — downloads meeting minute PDFs from municipality websites.

Reworked 2026-08-02 for politeness-preserving parallelism:

  Phase 0 (main thread): preload known (body, url) pairs + content hashes in
      one query each (replaces the old one-query-per-PDF-link N+1), preload
      HTTP validators from meta.scraper_http_cache.
  Phase 1 (parallel across DOMAINS, sequential + throttled within a domain):
      robots.txt check, conditional GET of each minutes page
      (If-None-Match / If-Modified-Since -> 304 = whole listing unchanged),
      extract PDF links.
  Phase 1.5 (main thread): transparent Playwright rendering only for a
      successful static request whose document list is genuinely JS-rendered.
  Phase 2 (parallel across DOMAINS): download only NEW documents, body-scoped
      content-hash dedup, and enforce global/per-body request caps before
      extracting text and archiving to R2. Workers never touch the database.
  Phase 3 (main thread): insert rows and refresh HTTP validators — the
      shared DatabaseResource connection is not thread-safe. Validators are
      only stored after a fully clean pass over that listing, so a future
      304 can never hide PDFs a partially-failed run missed.

  Politeness invariants: one in-flight request per domain at a time,
  jittered 0.5-1s delay between same-domain requests, robots.txt honored
  (fail-closed when robots cannot be established),
  conditional requests wherever the server provides validators.
"""

import concurrent.futures
import hashlib
import os
import random
import re
import threading
import time
from datetime import date, timedelta
from urllib.parse import urlparse, urlsplit, urlunsplit

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)
from psycopg2.errors import UndefinedTable

from countyiq.lib.county_config import (
    get_county_config,
    municipality_name_from_body,
    municipality_source_key,
)
from countyiq.lib.doc_text import extract_text_from_docx_bytes, extract_text_from_pdf_bytes
from countyiq.lib.error_budget import check_error_budget
from countyiq.lib.parsers.public_proceedings import (
    classify_proceeding_type,
    extract_drive_folder_ids,
    extract_pdf_links,
    parse_drive_folder_listing,
    parse_meeting_date_from_filename,
)
from countyiq.lib.robots import (
    RobotsDeniedError,
    RobotsPolicy,
    SourceOriginDeniedError,
    get_with_robots,
    source_origin,
)
from countyiq.lib.source_rights import (
    authorize_municipality_sources,
    authorize_source,
    record_municipality_source_health,
    require_source_use,
)
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

# Seconds to wait between HTTP requests to the SAME domain (randomised in range)
_THROTTLE_MIN = 0.5
_THROTTLE_MAX = 1.0

# Timeout for individual HTTP requests
_REQUEST_TIMEOUT = 30

# Concurrent domains. Each domain is processed by exactly one worker, so
# per-domain request serialization (politeness) is structural.
_MAX_DOMAIN_WORKERS = 5

# Honest product identity used consistently for robots and document requests.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; CountyIQ/1.0; +https://countyiq.app)"
    )
}

# How long to wait for JS-rendered content before grabbing the DOM
_PLAYWRIGHT_NAV_TIMEOUT_MS = 20000
_PLAYWRIGHT_SETTLE_MS = 2000
# Second-chance settle for sites that load their document list via XHR after
# the DOM settles (eCode360's pub-doc API takes several seconds).
_PLAYWRIGHT_XHR_SETTLE_MS = 12000

# Finite scheduled-run defaults. Database dedup rows are the resume checkpoint,
# so a historical backlog drains across runs instead of one run crawling all
# available history.
_DEFAULT_MAX_DOCUMENT_REQUESTS = 250
_DEFAULT_MAX_DOCUMENTS_PER_BODY = 25
_DEFAULT_MAX_FUTURE_DAYS = 90

# Browser rendering is not permission to disguise the collector. Use the
# same honest CountyIQ identity as the direct HTTP path.
_BROWSER_UA = _HEADERS["User-Agent"]


def _positive_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


class _DocumentRequestBudget:
    """Thread-safe global and per-governing-body document request budget."""

    def __init__(self, total_limit: int, per_body_limit: int) -> None:
        self.total_limit = total_limit
        self.per_body_limit = per_body_limit
        self.claimed = 0
        self._by_body: dict[str, int] = {}
        self._lock = threading.Lock()

    def reserve(self, body_name: str) -> bool:
        with self._lock:
            body_claimed = self._by_body.get(body_name, 0)
            if self.claimed >= self.total_limit or body_claimed >= self.per_body_limit:
                return False
            self.claimed += 1
            self._by_body[body_name] = body_claimed + 1
            return True


def _document_priority(link: dict) -> tuple[str, str]:
    """Sort likely newer dated documents first; undated documents sort last."""
    parsed = parse_meeting_date_from_filename(link.get("filename") or "")
    if parsed is None:
        parsed = parse_meeting_date_from_filename(link.get("link_text") or "")
    return parsed or "", link.get("filename") or ""


def _sanitize_meeting_date(
    value: str | None,
    *,
    today: date | None = None,
    max_future_days: int = _DEFAULT_MAX_FUTURE_DAYS,
) -> tuple[str | None, bool]:
    """Null implausibly future dates while preserving the document itself."""
    if value is None:
        return None, False
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None, True
    cutoff = (today or date.today()) + timedelta(days=max_future_days)
    if parsed > cutoff:
        return None, True
    return value, False


def _clear_implausible_future_dates(
    database: DatabaseResource,
    *,
    max_future_days: int,
) -> int:
    """Repair parser false-positives already persisted by older scraper runs."""
    cur = database.cursor()
    try:
        cur.execute(
            """
            UPDATE staging.public_proceedings
            SET meeting_date = NULL
            WHERE valid_to IS NULL
              AND meeting_date > CURRENT_DATE + (%s * INTERVAL '1 day')
            RETURNING id
            """,
            (max_future_days,),
        )
        return len(cur.fetchall())
    finally:
        cur.close()


class _PlaywrightFetcher:
    """Lazy headless-browser fetcher for JS-rendered sites.

    Reuses a single Chromium instance across all municipalities to avoid
    the ~1s startup cost per page. Lazy-imports playwright so the scraper
    can run without it installed if every site uses static HTML.

    NOT thread-safe — only ever used from the main thread (phase 1.5).
    """

    def __init__(self, log, robots: RobotsPolicy):
        self._log = log
        self._robots = robots
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
                "Run: uv sync --locked && .venv/bin/playwright install chromium"
            )
            self._unavailable = True
            return False
        try:
            self._playwright = sync_playwright().start()
            launch_args = []
            try:
                self._browser = self._playwright.chromium.launch(
                    channel="chrome", headless=True, args=launch_args
                )
                self._log.info("Playwright launched real Chrome for JS fallback")
            except Exception:
                self._browser = self._playwright.chromium.launch(
                    headless=True, args=launch_args
                )
                self._log.info("Playwright Chromium launched for JS fallback")
            return True
        except Exception as exc:
            self._log.warning("Failed to launch Playwright browser: %s", exc)
            self._unavailable = True
            return False

    def fetch_html(
        self,
        url: str,
        allowed_origins: frozenset[str],
        settle_ms: int = _PLAYWRIGHT_SETTLE_MS,
    ) -> str | None:
        """Fetch the fully-rendered HTML for a URL, or None on failure."""
        if not self._ensure_browser():
            return None
        try:
            page = self._browser.new_page(user_agent=_BROWSER_UA)
            try:
                def authorize_request(route, request):
                    request_origin = source_origin(request.url)
                    carries_source_data = request.resource_type in {
                        "document",
                        "xhr",
                        "fetch",
                    }
                    if request_origin not in allowed_origins:
                        if carries_source_data:
                            self._log.warning(
                                "Blocked browser access to unreviewed origin %s",
                                request_origin,
                            )
                            route.abort()
                        else:
                            # Third-party scripts, styles, fonts, and images are
                            # render dependencies, not acquired source records.
                            route.continue_()
                        return
                    if not carries_source_data and not request.is_navigation_request():
                        route.continue_()
                        return
                    decision = self._robots.decision(request.url)
                    if decision.allowed:
                        route.continue_()
                    else:
                        self._log.warning(
                            "Blocked browser navigation to %s: %s",
                            request.url,
                            decision.reason,
                        )
                        route.abort()

                # Redirects, iframe documents, and XHR/fetch endpoints are
                # requests of their own. Intercept them before access so browser
                # rendering cannot leave the fail-closed robots boundary.
                page.route("**/*", authorize_request)
                page.goto(url, timeout=_PLAYWRIGHT_NAV_TIMEOUT_MS, wait_until="domcontentloaded")
                page.wait_for_timeout(settle_ms)
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


def _domain_of(url: str) -> str:
    return urlparse(url).netloc.lower()


def _upgrade_reviewed_document_url(
    url: str,
    allowed_origins: frozenset[str],
) -> str:
    """Upgrade legacy HTTP links when the matching HTTPS origin is reviewed."""

    parsed = urlsplit(url)
    if parsed.scheme.lower() != "http":
        return url
    candidate = urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
    return candidate if source_origin(candidate) in allowed_origins else url


def _filter_allowed_document_links(
    links: list[dict],
    allowed_origins: frozenset[str],
) -> tuple[list[dict], set[str]]:
    """Keep reviewed document origins without sacrificing same-page signal.

    Municipal archive pages can mix first-party records with unrelated links or
    vendor-hosted records whose terms have not been approved. Those unreviewed
    links are policy outcomes, not download failures: retain their URLs for
    audit metadata while allowing any approved documents on the same page to
    continue through the normal robots and content checks.
    """

    allowed: list[dict] = []
    blocked_urls: set[str] = set()
    for link in links:
        document_url = _upgrade_reviewed_document_url(
            link["url"],
            allowed_origins,
        )
        if source_origin(document_url) not in allowed_origins:
            blocked_urls.add(document_url)
            continue
        allowed.append({**link, "url": document_url})
    return allowed, blocked_urls


def group_by_domain(
    municipality_websites,
) -> dict[str, list[tuple[str, str, str]]]:
    """Group (body_name, minutes_url, proceeding_type) entries by domain.

    Each domain group is processed by a single worker so same-domain
    requests are strictly sequential regardless of the pool size.
    """
    groups: dict[str, list[tuple[str, str, str]]] = {}
    for entry in municipality_websites:
        groups.setdefault(_domain_of(entry[1]), []).append(entry)
    return groups


def conditional_headers(validators: dict | None) -> dict:
    """Build If-None-Match / If-Modified-Since headers from stored validators."""
    headers = dict(_HEADERS)
    if validators:
        if validators.get("etag"):
            headers["If-None-Match"] = validators["etag"]
        if validators.get("last_modified"):
            headers["If-Modified-Since"] = validators["last_modified"]
    return headers


@asset(
    group_name="scrapers",
    description="Download meeting minute PDFs from municipality websites (county-config driven)",
    kinds={"postgres", "scraper"},
)
def public_proceedings_scrape(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    county = get_county_config()
    log = context.log
    source_authorization = authorize_source(
        database,
        source_key="public_proceedings",
        acquisition_method="official_document_direct",
        asset_key="public_proceedings_scrape",
        dagster_run_id=context.run_id,
    )
    require_source_use(source_authorization, "derived_product")
    require_source_use(source_authorization, "raw_retention")

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
                "errors": MetadataValue.int(0),
            }
        )

    municipality_authorizations = authorize_municipality_sources(
        database,
        entries=municipality_websites,
        acquisition_method="official_document_direct",
        asset_key="public_proceedings_scrape",
        dagster_run_id=context.run_id,
    )

    # ------------------------------------------------------------------
    # Phase 0 — preload dedup sets + HTTP validators (main thread)
    # ------------------------------------------------------------------
    known_pairs: set[tuple[str, str]] = set()
    known_hashes: set[tuple[str, str]] = set()
    rows = database.execute(
        """
        SELECT body_name, document_url, content_hash
        FROM staging.public_proceedings
        WHERE valid_to IS NULL
        """
    )
    for row in rows or []:
        body, url, chash = (row["body_name"], row["document_url"], row["content_hash"]) \
            if isinstance(row, dict) else (row[0], row[1], row[2])
        if body and url:
            known_pairs.add((body, url))
        if body and chash:
            known_hashes.add((body, chash))

    validators_by_url: dict[str, dict] = {}
    http_cache_available = True
    try:
        cache_rows = database.execute(
            "SELECT url, etag, last_modified FROM meta.scraper_http_cache"
        )
        for row in cache_rows or []:
            url, etag, lm = (row["url"], row["etag"], row["last_modified"]) \
                if isinstance(row, dict) else (row[0], row[1], row[2])
            validators_by_url[url] = {"etag": etag, "last_modified": lm}
    except UndefinedTable:
        http_cache_available = False
        log.info("meta.scraper_http_cache missing (migration 024 not applied) — conditional GETs disabled")

    domains = group_by_domain(municipality_websites)
    log.info(
        "Scraping %d source entries across %d domains (%d workers); "
        "%d known documents, %d cached validators",
        len(municipality_websites), len(domains),
        min(_MAX_DOMAIN_WORKERS, len(domains)),
        len(known_pairs), len(validators_by_url),
    )

    robots = RobotsPolicy(_HEADERS["User-Agent"])
    claimed_lock = threading.Lock()
    claimed_pairs: set[tuple[str, str]] = set()
    claimed_hashes: set[tuple[str, str]] = set(known_hashes)
    max_document_requests = _positive_int_env(
        "COUNTYIQ_PROCEEDINGS_MAX_DOCUMENT_REQUESTS",
        _DEFAULT_MAX_DOCUMENT_REQUESTS,
    )
    max_documents_per_body = _positive_int_env(
        "COUNTYIQ_PROCEEDINGS_MAX_DOCUMENTS_PER_BODY",
        _DEFAULT_MAX_DOCUMENTS_PER_BODY,
    )
    max_future_days = _positive_int_env(
        "COUNTYIQ_PROCEEDINGS_MAX_FUTURE_DAYS",
        _DEFAULT_MAX_FUTURE_DAYS,
    )
    existing_future_dates_cleared = _clear_implausible_future_dates(
        database,
        max_future_days=max_future_days,
    )
    if existing_future_dates_cleared:
        log.warning(
            "Cleared %d previously stored implausible future meeting dates",
            existing_future_dates_cleared,
        )
    request_budget = _DocumentRequestBudget(
        max_document_requests,
        max_documents_per_body,
    )

    # ------------------------------------------------------------------
    # Phase 1 — parallel listing fetch (HTTP only, one worker per domain)
    # ------------------------------------------------------------------
    def fetch_listings_for_domain(entries):
        results = []
        for body_name, minutes_url, proceeding_type in entries:
            source_key = municipality_source_key(body_name)
            authorization = municipality_authorizations[source_key]
            entry_result = {
                "source_key": source_key,
                "body_name": body_name,
                "minutes_url": minutes_url,
                "proceeding_type": proceeding_type,
                "status": "ok",
                "links": [],
                "validators": None,
                "robots_allowed": None,
                "robots_reason": None,
                "http_status": None,
                "resolved_url": minutes_url,
                "last_error": None,
                "policy_blocked_document_urls": set(),
                "budget_deferred": 0,
            }
            robots_decision = robots.decision(minutes_url)
            entry_result["robots_allowed"] = robots_decision.allowed
            entry_result["robots_reason"] = robots_decision.reason
            if not robots_decision.allowed:
                entry_result["status"] = "robots_skipped"
                entry_result["last_error"] = robots_decision.reason
                results.append(entry_result)
                continue
            try:
                resp = get_with_robots(
                    minutes_url,
                    robots=robots,
                    allowed_origins=authorization.allowed_origins,
                    headers=conditional_headers(validators_by_url.get(minutes_url)),
                    timeout=_REQUEST_TIMEOUT,
                )
                entry_result["http_status"] = resp.status_code
                entry_result["resolved_url"] = resp.url
                if resp.status_code == 304:
                    entry_result["status"] = "not_modified"
                    results.append(entry_result)
                    _throttle()
                    continue
                resp.raise_for_status()
                html = resp.text
                entry_result["validators"] = {
                    "etag": resp.headers.get("ETag"),
                    "last_modified": resp.headers.get("Last-Modified"),
                }
            except RobotsDeniedError as exc:
                log.warning(
                    "Robots policy blocked '%s' after redirect to %s: %s",
                    body_name,
                    exc.url,
                    exc.reason,
                )
                html = None
                entry_result["status"] = "robots_skipped"
                entry_result["robots_allowed"] = False
                entry_result["robots_reason"] = f"redirect:{exc.reason}"
                entry_result["last_error"] = str(exc)[:500]
            except SourceOriginDeniedError as exc:
                log.warning(
                    "Source policy blocked '%s' redirect to unreviewed origin %s",
                    body_name,
                    source_origin(exc.url),
                )
                html = None
                entry_result["status"] = "policy_skipped"
                entry_result["last_error"] = str(exc)[:500]
            except Exception as exc:
                log.warning(
                    "Direct HTTP fetch failed for '%s' (%s): %s — not bypassing with a browser",
                    body_name, minutes_url, exc,
                )
                html = None
                entry_result["status"] = "access_error"
                entry_result["last_error"] = str(exc)[:500]
                response = getattr(exc, "response", None)
                if response is not None:
                    entry_result["http_status"] = response.status_code

            links = extract_pdf_links(html or "", entry_result["resolved_url"])
            if html:
                drive_records = _resolve_drive_folders(
                    html,
                    lambda url: _fetch_drive_listing(
                        url,
                        robots,
                        authorization.allowed_origins,
                    ),
                )
                if drive_records:
                    links.extend(drive_records)
                    # Folder contents change without the hub page changing, so
                    # a 304 on the hub would hide new files — never store
                    # validators for Drive-backed listings.
                    entry_result["validators"] = None
            links, blocked_urls = _filter_allowed_document_links(
                links,
                authorization.allowed_origins,
            )
            entry_result["policy_blocked_document_urls"].update(blocked_urls)
            if html and not links:
                entry_result["status"] = "needs_playwright"
            elif blocked_urls:
                entry_result["last_error"] = (
                    f"{len(blocked_urls)} document link(s) blocked by source-origin policy"
                )
            entry_result["links"] = links
            results.append(entry_result)
            _throttle()
        return results

    listing_results = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(_MAX_DOMAIN_WORKERS, len(domains))
    ) as pool:
        futures = [pool.submit(fetch_listings_for_domain, entries) for entries in domains.values()]
        for future in concurrent.futures.as_completed(futures):
            listing_results.extend(future.result())

    # ------------------------------------------------------------------
    # Phase 1.5 — Playwright fallback, main thread only
    # ------------------------------------------------------------------
    pdfs_via_playwright = 0
    playwright_fetcher = _PlaywrightFetcher(log, robots)
    try:
        for entry_result in listing_results:
            if entry_result["status"] != "needs_playwright":
                continue
            resolved_url = entry_result["resolved_url"]
            allowed_origins = municipality_authorizations[
                entry_result["source_key"]
            ].allowed_origins
            rendered = playwright_fetcher.fetch_html(resolved_url, allowed_origins)
            links = extract_pdf_links(rendered or "", resolved_url) if rendered else []
            links, blocked_urls = _filter_allowed_document_links(
                links,
                allowed_origins,
            )
            entry_result["policy_blocked_document_urls"].update(blocked_urls)
            if rendered and not links:
                # Some sites (eCode360) populate the document list via XHR
                # well after DOM settle — one slower retry before giving up.
                rendered = playwright_fetcher.fetch_html(
                    resolved_url,
                    allowed_origins,
                    settle_ms=_PLAYWRIGHT_XHR_SETTLE_MS,
                )
                links = extract_pdf_links(rendered or "", resolved_url) if rendered else []
                links, blocked_urls = _filter_allowed_document_links(
                    links,
                    allowed_origins,
                )
                entry_result["policy_blocked_document_urls"].update(blocked_urls)
            if links:
                pdfs_via_playwright += len(links)
                entry_result["links"] = links
                entry_result["status"] = "ok"
                blocked_count = len(entry_result["policy_blocked_document_urls"])
                if blocked_count:
                    entry_result["last_error"] = (
                        f"{blocked_count} document link(s) blocked by source-origin policy"
                    )
                # No validators for JS-rendered listings — always refetch.
                entry_result["validators"] = None
            elif rendered is None:
                entry_result["status"] = "render_error"
                entry_result["last_error"] = "browser rendering unavailable or failed"
            elif entry_result["policy_blocked_document_urls"]:
                entry_result["status"] = "policy_no_documents"
                entry_result["last_error"] = (
                    f"{len(entry_result['policy_blocked_document_urls'])} document link(s) "
                    "found, but none use an approved source origin"
                )
            else:
                entry_result["status"] = "no_documents"
                entry_result["last_error"] = "no supported documents discovered"
    finally:
        playwright_fetcher.close()

    listing_error_statuses = {
        "access_error",
        "no_documents",
        "render_error",
        "robots_skipped",
        "policy_skipped",
        "policy_no_documents",
    }
    listing_errors = sum(
        1 for result in listing_results if result["status"] in listing_error_statuses
    )

    # ------------------------------------------------------------------
    # Phase 2 — parallel downloads of NEW PDFs (one worker per domain)
    # ------------------------------------------------------------------
    pdfs_found = sum(len(r["links"]) for r in listing_results)
    policy_blocked_documents = sum(
        len(result["policy_blocked_document_urls"])
        for result in listing_results
    )

    def process_downloads_for_domain(entry_results):
        payloads = []
        stats = {
            "duplicates": 0,
            "null_date": 0,
            "future_date": 0,
            "archived": 0,
            "deferred": 0,
            "errors": 0,
        }
        for entry_result in entry_results:
            body_name = entry_result["body_name"]
            source_key = entry_result["source_key"]
            allowed_origins = municipality_authorizations[source_key].allowed_origins
            siblings = [
                result
                for result in entry_results
                if result["minutes_url"] == entry_result["minutes_url"]
            ]
            entry_result["download_errors"] = 0
            for link in sorted(
                entry_result["links"], key=_document_priority, reverse=True
            ):
                document_url = _upgrade_reviewed_document_url(
                    link["url"],
                    allowed_origins,
                )
                filename = link["filename"]
                link_text = link["link_text"]

                classified = classify_proceeding_type(filename, link_text)
                if not _link_belongs_to_entry(entry_result, siblings, classified):
                    continue

                with claimed_lock:
                    if (body_name, document_url) in known_pairs or \
                       (body_name, document_url) in claimed_pairs:
                        stats["duplicates"] += 1
                        continue
                    claimed_pairs.add((body_name, document_url))

                if source_origin(document_url) not in allowed_origins:
                    stats["errors"] += 1
                    entry_result["download_errors"] += 1
                    entry_result["last_error"] = (
                        "document origin is not approved by source policy"
                    )
                    continue
                if not robots.allowed(document_url):
                    stats["errors"] += 1
                    entry_result["download_errors"] += 1
                    entry_result["last_error"] = "document blocked by robots policy"
                    continue

                if not request_budget.reserve(body_name):
                    stats["deferred"] += 1
                    entry_result["budget_deferred"] += 1
                    continue

                meeting_date = parse_meeting_date_from_filename(filename)
                if meeting_date is None and link_text:
                    meeting_date = parse_meeting_date_from_filename(link_text)
                meeting_date, future_date = _sanitize_meeting_date(
                    meeting_date,
                    max_future_days=max_future_days,
                )
                if future_date:
                    stats["future_date"] += 1
                if meeting_date is None:
                    stats["null_date"] += 1

                resolved_type = (
                    classified if classified != "unknown" else entry_result["proceeding_type"]
                )

                try:
                    pdf_resp = get_with_robots(
                        document_url,
                        robots=robots,
                        allowed_origins=allowed_origins,
                        headers=_HEADERS,
                        timeout=_REQUEST_TIMEOUT,
                    )
                    pdf_resp.raise_for_status()
                    pdf_bytes = pdf_resp.content
                    if not _valid_document_content(filename, pdf_bytes):
                        raise ValueError("response content does not match document type")
                except Exception as exc:
                    log.warning("'%s': failed to download '%s': %s", body_name, document_url, exc)
                    stats["errors"] += 1
                    entry_result["download_errors"] += 1
                    entry_result["last_error"] = str(exc)[:500]
                    _throttle()
                    continue

                content_hash = hashlib.sha256(pdf_bytes).hexdigest()
                with claimed_lock:
                    body_hash = (body_name, content_hash)
                    if body_hash in claimed_hashes:
                        stats["duplicates"] += 1
                        _throttle()
                        continue
                    claimed_hashes.add(body_hash)

                safe_body = _safe_name(body_name)
                date_segment = meeting_date or "undated"
                try:
                    require_source_use(
                        municipality_authorizations[source_key], "raw_retention"
                    )
                    s3.archive(
                        f"{county.s3_prefix}/proceedings/{safe_body}/{date_segment}",
                        pdf_bytes,
                        filename=filename,
                    )
                    stats["archived"] += 1
                except Exception as exc:
                    if s3.strict:
                        raise
                    log.warning("'%s': R2 archive failed for '%s': %s", body_name, filename, exc)

                raw_text = _extract_raw_text(filename, pdf_bytes)
                if raw_text is None:
                    # Expected for legacy .doc and scanned PDFs; Pass 0 falls
                    # back to downloading the document itself (PDFs only).
                    log.info("'%s': no text extracted from '%s'", body_name, filename)

                payloads.append({
                    "body_name": body_name,
                    "meeting_date": meeting_date,
                    "proceeding_type": resolved_type,
                    "source_url": entry_result["minutes_url"],
                    "document_url": document_url,
                    "content_hash": content_hash,
                    "raw_text": raw_text,
                })
                _throttle()
        return entry_results, payloads, stats

    results_by_domain: dict[str, list[dict]] = {}
    for entry_result in listing_results:
        results_by_domain.setdefault(_domain_of(entry_result["minutes_url"]), []).append(entry_result)

    pdfs_new = 0
    pdfs_skipped_duplicate = 0
    pdfs_null_date = 0
    pdfs_future_date_rejected = 0
    pdfs_archived = 0
    pdfs_deferred = 0
    errors = listing_errors
    insert_failures_by_entry: dict[tuple[str, str], int] = {}

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(_MAX_DOMAIN_WORKERS, len(results_by_domain))
    ) as pool:
        futures = [
            pool.submit(process_downloads_for_domain, entry_results)
            for entry_results in results_by_domain.values()
        ]
        for future in concurrent.futures.as_completed(futures):
            entry_results, payloads, stats = future.result()
            pdfs_skipped_duplicate += stats["duplicates"]
            pdfs_null_date += stats["null_date"]
            pdfs_future_date_rejected += stats["future_date"]
            pdfs_archived += stats["archived"]
            pdfs_deferred += stats["deferred"]
            errors += stats["errors"]

            # Phase 3 — DB writes on the main thread as domains complete.
            for payload in payloads:
                try:
                    _insert_proceeding(database=database, **payload)
                    pdfs_new += 1
                except Exception as exc:
                    log.warning(
                        "'%s': DB insert failed for '%s': %s",
                        payload["body_name"], payload["document_url"], exc,
                    )
                    errors += 1
                    key = (payload["body_name"], payload["source_url"])
                    insert_failures_by_entry[key] = insert_failures_by_entry.get(key, 0) + 1

            if http_cache_available:
                for entry_result in entry_results:
                    key = (entry_result["body_name"], entry_result["minutes_url"])
                    clean = (
                        entry_result["status"] == "ok"
                        and entry_result.get("validators")
                        and entry_result.get("download_errors", 0) == 0
                        and entry_result.get("budget_deferred", 0) == 0
                        and insert_failures_by_entry.get(key, 0) == 0
                    )
                    if clean:
                        _upsert_validators(database, entry_result["minutes_url"], entry_result["validators"])

    for entry_result in listing_results:
        key = (entry_result["body_name"], entry_result["minutes_url"])
        insert_errors = insert_failures_by_entry.get(key, 0)
        item_errors = entry_result.get("download_errors", 0) + insert_errors
        health_status = entry_result["status"]
        if item_errors and health_status in {"ok", "not_modified"}:
            health_status = "partial_error"
        elif entry_result.get("budget_deferred", 0) and health_status == "ok":
            health_status = "budget_limited"
        if insert_errors:
            entry_result["last_error"] = f"{insert_errors} database insert(s) failed"
        record_municipality_source_health(
            database,
            source_key=entry_result["source_key"],
            listing_status=health_status,
            robots_allowed=entry_result["robots_allowed"],
            robots_reason=entry_result["robots_reason"],
            http_status=entry_result["http_status"],
            document_count=len(entry_result["links"]),
            last_error=entry_result["last_error"],
        )

    listings_not_modified = sum(1 for r in listing_results if r["status"] == "not_modified")
    robots_skipped = sum(1 for r in listing_results if r["status"] == "robots_skipped")

    log.info(
        "Scrape complete: %d PDFs found (%d via Playwright), %d new, %d duplicates, "
        "%d deferred, %d null date, %d future date rejected, %d archived, "
        "%d listings unchanged (304), %d robots-skipped, %d errors",
        pdfs_found, pdfs_via_playwright, pdfs_new, pdfs_skipped_duplicate,
        pdfs_deferred, pdfs_null_date, pdfs_future_date_rejected, pdfs_archived,
        listings_not_modified, robots_skipped, errors,
    )
    # Listing reachability and document processing have different
    # denominators. Keep both visible so zero discovered documents cannot turn
    # a broken municipal sweep green.
    check_error_budget(
        log,
        label="public_proceedings_listings",
        errors=listing_errors,
        total=len(listing_results),
    )
    downstream_errors = errors - listing_errors
    check_error_budget(
        log,
        label="public_proceedings_documents",
        errors=downstream_errors,
        total=max(pdfs_found, downstream_errors),
    )

    municipalities_with_any_source = {
        name
        for body_name, _, _ in municipality_websites
        if (name := municipality_name_from_body(body_name)) is not None
    }
    governing_body_municipalities = {
        municipality_name_from_body(body_name)
        for body_name, _, proceeding_type in municipality_websites
        if proceeding_type in {
            "board_of_commissioners",
            "board_of_supervisors",
            "borough_council",
            "city_council",
        }
    }
    listing_urls = {url for _, url, _ in municipality_websites}

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text(
                "complete_budget_limited" if pdfs_deferred else "complete"
            ),
            "municipalities_configured": MetadataValue.int(
                len(governing_body_municipalities)
            ),
            "municipalities_with_any_source": MetadataValue.int(
                len(municipalities_with_any_source)
            ),
            "source_entries_configured": MetadataValue.int(
                len(municipality_websites)
            ),
            "listing_urls_configured": MetadataValue.int(len(listing_urls)),
            "domains": MetadataValue.int(len(domains)),
            "pdfs_found": MetadataValue.int(pdfs_found),
            "pdfs_via_playwright": MetadataValue.int(pdfs_via_playwright),
            "pdfs_new": MetadataValue.int(pdfs_new),
            "pdfs_skipped_duplicate": MetadataValue.int(pdfs_skipped_duplicate),
            "pdfs_deferred": MetadataValue.int(pdfs_deferred),
            "document_requests_claimed": MetadataValue.int(request_budget.claimed),
            "document_request_limit": MetadataValue.int(max_document_requests),
            "document_per_body_limit": MetadataValue.int(max_documents_per_body),
            "pdfs_null_date": MetadataValue.int(pdfs_null_date),
            "pdfs_future_date_rejected": MetadataValue.int(
                pdfs_future_date_rejected
            ),
            "existing_future_dates_cleared": MetadataValue.int(
                existing_future_dates_cleared
            ),
            "pdfs_archived": MetadataValue.int(pdfs_archived),
            "policy_blocked_documents": MetadataValue.int(policy_blocked_documents),
            "listings_not_modified": MetadataValue.int(listings_not_modified),
            "robots_skipped": MetadataValue.int(robots_skipped),
            "errors": MetadataValue.int(errors),
        }
    )


def _upsert_validators(database: DatabaseResource, url: str, validators: dict) -> None:
    database.execute(
        """
        INSERT INTO meta.scraper_http_cache (url, etag, last_modified, fetched_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (url) DO UPDATE SET
            etag = EXCLUDED.etag,
            last_modified = EXCLUDED.last_modified,
            fetched_at = NOW()
        """,
        (url, validators.get("etag"), validators.get("last_modified")),
    )


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

# How many levels of Drive subfolders to descend (hub folder + one level of
# e.g. "Draft Minutes" subfolders covers the observed layouts).
_DRIVE_MAX_DEPTH = 2

_CLASSIFIED_TYPE_BY_CONFIG = {
    "board_of_supervisors": "supervisors",
    "borough_council": "council",
    "city_council": "council",
    "planning_commission": "planning_commission",
    "zoning_hearing": "zoning_hearing",
}


def _link_belongs_to_entry(
    entry_result: dict,
    siblings: list[dict],
    classified_type: str,
) -> bool:
    """Route one shared listing document to a single configured body.

    Three municipalities intentionally reuse one archive page for multiple
    boards. Known document classifications go only to the matching board;
    ambiguous documents go to the first configured entry so they are retained
    once without manufacturing several body attributions.
    """

    if len(siblings) <= 1:
        return True
    if classified_type != "unknown":
        expected = _CLASSIFIED_TYPE_BY_CONFIG.get(entry_result["proceeding_type"])
        return expected == classified_type
    return entry_result is siblings[0]


def _valid_document_content(filename: str, data: bytes) -> bool:
    """Reject HTML/error pages returned from document-looking URLs."""

    lower = filename.lower()
    if lower.endswith(".docx"):
        return data.startswith(b"PK\x03\x04")
    if lower.endswith(".doc"):
        return data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    return data.startswith(b"%PDF-")


def _fetch_drive_listing(
    url: str,
    robots: RobotsPolicy,
    allowed_origins: frozenset[str],
) -> str | None:
    """Fetch an embeddedfolderview page; None on any failure (fail soft)."""
    try:
        resp = get_with_robots(
            url,
            robots=robots,
            allowed_origins=allowed_origins,
            headers=_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None
    finally:
        _throttle()


def _resolve_drive_folders(html: str, fetch_fn) -> list[dict]:
    """Resolve Google Drive folder links on a minutes page to file records.

    Fetches each folder's embeddedfolderview page (static HTML — no browser
    needed) via fetch_fn(url) -> str | None, recursing one level into
    subfolders. Returns link records shaped like extract_pdf_links output,
    with uc?export=download URLs that serve raw bytes headlessly.
    """
    queue = [(fid, 1) for fid in extract_drive_folder_ids(html)]
    seen: set[str] = set(fid for fid, _ in queue)
    records: list[dict] = []
    while queue:
        folder_id, depth = queue.pop(0)
        listing_html = fetch_fn(
            f"https://drive.google.com/embeddedfolderview?id={folder_id}"
        )
        if not listing_html:
            continue
        listing = parse_drive_folder_listing(listing_html)
        records.extend(listing["files"])
        if depth < _DRIVE_MAX_DEPTH:
            for sub_id in listing["subfolder_ids"]:
                if sub_id not in seen:
                    seen.add(sub_id)
                    queue.append((sub_id, depth + 1))
    return records


def _extract_raw_text(filename: str, data: bytes) -> str | None:
    """Extract document text, dispatching on the filename extension.

    .docx uses the stdlib Word extractor; legacy .doc has no extractor and
    returns None (archived without text); everything else goes through
    pdfplumber. Pass 0 sends raw_text to the LLM when present — OpenRouter's
    file-parser only accepts PDFs, so Word docs MUST get their text here.
    """
    lower = filename.lower()
    try:
        if lower.endswith((".docx", ".doc")):
            return extract_text_from_docx_bytes(data) or None
        return extract_text_from_pdf_bytes(data) or None
    except Exception:
        return None


def _safe_name(name: str) -> str:
    """Convert a municipality/body name to a safe path segment."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _throttle() -> None:
    """Sleep for a random duration between same-domain requests."""
    time.sleep(random.uniform(_THROTTLE_MIN, _THROTTLE_MAX))
