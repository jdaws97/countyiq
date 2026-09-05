"""Produce a retained, policy-authorized static audit of municipal sources.

This command intentionally stops before downloading documents or retaining
source HTML. It records only operational facts needed to prove which reviewed
listing pages were reachable, robots-allowed, and statically discoverable.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from countyiq.assets.scrapers.public_proceedings import (
    _PLAYWRIGHT_XHR_SETTLE_MS,
    _PlaywrightFetcher,
    _resolve_drive_folders,
    _upgrade_reviewed_document_url,
)
from countyiq.lib.county_config import get_county_config, municipality_source_key
from countyiq.lib.parsers.public_proceedings import (
    extract_drive_folder_ids,
    extract_pdf_links,
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
from countyiq.resources.database import make_database_resource


_USER_AGENT = "Mozilla/5.0 (compatible; CountyIQ/1.0; +https://countyiq.app)"
_HEADERS = {"User-Agent": _USER_AGENT}
_TIMEOUT_SECONDS = 30
_MAX_DOMAIN_WORKERS = 5
_DOMAIN_DELAY_SECONDS = 0.5
_DRIVE_LOCK = threading.Lock()


class _AuditLog:
    def info(self, message: str, *args) -> None:
        print("INFO " + (message % args if args else message))

    def warning(self, message: str, *args) -> None:
        print("WARNING " + (message % args if args else message))


def _fetch_drive_listing(
    url: str,
    robots: RobotsPolicy,
    allowed_origins: frozenset[str],
) -> str | None:
    """Fetch one Drive folder listing under the same redirect/robots rules."""

    with _DRIVE_LOCK:
        try:
            response = get_with_robots(
                url,
                robots=robots,
                allowed_origins=allowed_origins,
                headers=_HEADERS,
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.text
        except (requests.RequestException, RobotsDeniedError):
            return None
        finally:
            time.sleep(_DOMAIN_DELAY_SECONDS)


def audit_listing_url(
    url: str,
    robots: RobotsPolicy,
    allowed_origins: frozenset[str],
) -> dict:
    """Return non-content health facts for one unique reviewed listing URL."""

    initial_decision = robots.decision(url)
    result = {
        "listing_url": url,
        "resolved_url": url,
        "status": "robots_skipped",
        "robots_allowed": initial_decision.allowed,
        "robots_reason": initial_decision.reason,
        "robots_url": initial_decision.robots_url,
        "robots_http_status": initial_decision.status_code,
        "http_status": None,
        "content_type": None,
        "document_count": 0,
        "discovered_document_count": 0,
        "document_origins": [],
        "document_origin_counts": {},
        "blocked_document_origin_counts": {},
        "last_error": None,
    }
    if not initial_decision.allowed:
        result["last_error"] = initial_decision.reason
        return result

    try:
        response = get_with_robots(
            url,
            robots=robots,
            allowed_origins=allowed_origins,
            headers=_HEADERS,
            timeout=_TIMEOUT_SECONDS,
        )
        result["resolved_url"] = response.url
        result["http_status"] = response.status_code
        result["content_type"] = response.headers.get("Content-Type")
        response.raise_for_status()
    except RobotsDeniedError as exc:
        result["robots_allowed"] = False
        result["robots_reason"] = f"redirect:{exc.reason}"
        result["last_error"] = str(exc)[:500]
        return result
    except SourceOriginDeniedError as exc:
        result["status"] = "policy_skipped"
        result["last_error"] = str(exc)[:500]
        return result
    except requests.RequestException as exc:
        result["status"] = "access_error"
        result["last_error"] = str(exc)[:500]
        response = getattr(exc, "response", None)
        if response is not None:
            result["http_status"] = response.status_code
            result["resolved_url"] = response.url
        return result

    content_type = (result["content_type"] or "").lower()
    if "application/pdf" in content_type or response.content.startswith(b"%PDF-"):
        result["document_count"] = 1
        result["discovered_document_count"] = 1
        result["document_origins"] = [source_origin(response.url)]
        result["document_origin_counts"] = {source_origin(response.url): 1}
        result["status"] = "ok"
        return result

    links = extract_pdf_links(response.text, response.url)
    drive_links = []
    if extract_drive_folder_ids(response.text):
        result["document_origins"].append("https://drive.google.com")
        if "https://drive.google.com" in allowed_origins:
            drive_links = _resolve_drive_folders(
                response.text,
                lambda drive_url: _fetch_drive_listing(
                    drive_url,
                    robots,
                    allowed_origins,
                ),
            )
    unique_links = {item["url"] for item in [*links, *drive_links]}
    normalized_links = {
        _upgrade_reviewed_document_url(link, allowed_origins)
        for link in unique_links
    }
    collectable_links = {
        link
        for link in normalized_links
        if source_origin(link) in allowed_origins
    }
    blocked_links = normalized_links - collectable_links
    result["document_origins"] = sorted(
        {
            *result["document_origins"],
            *(source_origin(link) for link in unique_links),
        }
    )
    result["document_origin_counts"] = dict(
        sorted(Counter(source_origin(link) for link in unique_links).items())
    )
    result["blocked_document_origin_counts"] = dict(
        sorted(Counter(source_origin(link) for link in blocked_links).items())
    )
    result["discovered_document_count"] = len(unique_links)
    result["document_count"] = len(collectable_links)
    result["status"] = "ok" if collectable_links else "needs_playwright"
    return result


def _audit_domain(
    sources: list[tuple[str, frozenset[str]]],
    robots: RobotsPolicy,
) -> list[dict]:
    results = []
    for url, allowed_origins in sources:
        results.append(audit_listing_url(url, robots, allowed_origins))
        time.sleep(_DOMAIN_DELAY_SECONDS)
    return results


def _load_municipality_policies(database) -> list[dict]:
    columns = (
        "source_key",
        "municipality_name",
        "body_name",
        "listing_url",
        "proceeding_type",
        "rights_status",
        "terms_review_status",
        "acquisition_allowed",
        "raw_retention_allowed",
        "derived_product_allowed",
        "raw_export_allowed",
        "allowed_origins",
        "reviewed_on",
        "review_due_on",
        "notes",
    )
    rows = database.execute(
        """
        SELECT
            source_key, municipality_name, body_name, listing_url,
            proceeding_type, rights_status, terms_review_status,
            acquisition_allowed, raw_retention_allowed,
            derived_product_allowed, raw_export_allowed,
            allowed_origins, reviewed_on,
            review_due_on, notes
        FROM meta.municipality_source_rights
        ORDER BY municipality_name NULLS LAST, body_name
        """
    )
    return [dict(zip(columns, row, strict=True)) for row in rows or []]


def build_report(database, *, with_browser: bool = False) -> dict:
    county = get_county_config()
    entries = county.municipality_websites
    run_id = f"static-audit-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    parent_authorization = authorize_source(
        database,
        source_key="public_proceedings",
        acquisition_method="official_document_direct",
        asset_key="municipality_source_static_audit",
        dagster_run_id=run_id,
    )
    require_source_use(parent_authorization, "derived_product")
    authorizations = authorize_municipality_sources(
        database,
        entries=entries,
        acquisition_method="official_document_direct",
        asset_key="municipality_source_static_audit",
        dagster_run_id=run_id,
    )

    policies = _load_municipality_policies(database)
    policies_by_key = {policy["source_key"]: policy for policy in policies}
    configured_keys = {
        municipality_source_key(body_name) for body_name, _, _ in entries
    }
    if configured_keys != set(authorizations):
        raise RuntimeError("authorized municipality set does not match configuration")

    permissions_by_url: dict[str, frozenset[str]] = {}
    for body_name, url, _ in entries:
        allowed_origins = authorizations[
            municipality_source_key(body_name)
        ].allowed_origins
        if url in permissions_by_url and permissions_by_url[url] != allowed_origins:
            raise RuntimeError(f"shared listing URL has inconsistent origins: {url}")
        permissions_by_url[url] = allowed_origins
    urls_by_domain: dict[str, list[tuple[str, frozenset[str]]]] = defaultdict(list)
    for url, allowed_origins in sorted(permissions_by_url.items()):
        urls_by_domain[urlparse(url).netloc.lower()].append(
            (url, allowed_origins)
        )

    robots = RobotsPolicy(_USER_AGENT)
    url_results = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(_MAX_DOMAIN_WORKERS, len(urls_by_domain))
    ) as pool:
        futures = [
            pool.submit(_audit_domain, urls, robots)
            for urls in urls_by_domain.values()
        ]
        for future in concurrent.futures.as_completed(futures):
            url_results.extend(future.result())

    for result in url_results:
        result["browser_attempted"] = False
        result["browser_document_count"] = 0
    if with_browser:
        browser = _PlaywrightFetcher(_AuditLog(), robots)
        try:
            for result in url_results:
                if result["status"] != "needs_playwright":
                    continue
                result["browser_attempted"] = True
                resolved_url = result["resolved_url"]
                allowed_origins = permissions_by_url[result["listing_url"]]
                rendered = browser.fetch_html(resolved_url, allowed_origins)
                links = extract_pdf_links(rendered or "", resolved_url) if rendered else []
                if rendered and not links:
                    rendered = browser.fetch_html(
                        resolved_url,
                        allowed_origins,
                        settle_ms=_PLAYWRIGHT_XHR_SETTLE_MS,
                    )
                    links = (
                        extract_pdf_links(rendered or "", resolved_url)
                        if rendered
                        else []
                    )
                if rendered:
                    if (
                        extract_drive_folder_ids(rendered)
                        and "https://drive.google.com" in allowed_origins
                    ):
                        links.extend(
                            _resolve_drive_folders(
                                rendered,
                                lambda drive_url: _fetch_drive_listing(
                                    drive_url,
                                    robots,
                                    allowed_origins,
                                ),
                            )
                        )
                unique_links = {item["url"] for item in links}
                normalized_links = {
                    _upgrade_reviewed_document_url(link, allowed_origins)
                    for link in unique_links
                }
                collectable_links = {
                    link
                    for link in normalized_links
                    if source_origin(link) in allowed_origins
                }
                blocked_links = normalized_links - collectable_links
                result["document_origins"] = sorted(
                    {
                        *result["document_origins"],
                        *(source_origin(link) for link in unique_links),
                    }
                )
                result["document_origin_counts"] = dict(
                    sorted(Counter(source_origin(link) for link in unique_links).items())
                )
                result["blocked_document_origin_counts"] = dict(
                    sorted(Counter(source_origin(link) for link in blocked_links).items())
                )
                result["browser_document_count"] = len(collectable_links)
                result["discovered_document_count"] = len(unique_links)
                if collectable_links:
                    result["status"] = "ok"
                    result["document_count"] = len(collectable_links)
                elif rendered is None:
                    result["status"] = "render_error"
                    result["last_error"] = "browser rendering unavailable or failed"
                else:
                    result["status"] = "no_documents"
                    result["last_error"] = "no supported documents discovered"
        finally:
            browser.close()
    results_by_url = {result["listing_url"]: result for result in url_results}

    results = []
    for policy in policies:
        result = {**policy}
        listing_url = policy["listing_url"]
        if policy["source_key"] in configured_keys:
            result.update(results_by_url[listing_url])
            record_municipality_source_health(
                database,
                source_key=policy["source_key"],
                listing_status=result["status"],
                robots_allowed=result["robots_allowed"],
                robots_reason=result["robots_reason"],
                http_status=result["http_status"],
                document_count=result["document_count"],
                last_error=result["last_error"],
            )
        else:
            result.update(
                {
                    "resolved_url": None,
                    "status": "paused",
                    "robots_allowed": None,
                    "robots_reason": None,
                    "robots_url": None,
                    "robots_http_status": None,
                    "http_status": None,
                    "content_type": None,
                    "document_count": 0,
                    "discovered_document_count": 0,
                    "document_origins": [],
                    "document_origin_counts": {},
                    "blocked_document_origin_counts": {},
                    "browser_attempted": False,
                    "browser_document_count": 0,
                    "last_error": policy["notes"],
                }
            )
        results.append(result)

    status_counts = Counter(result["status"] for result in results)
    rights_counts = Counter(policy["rights_status"] for policy in policies)
    terms_counts = Counter(policy["terms_review_status"] for policy in policies)
    municipalities = {
        policy["municipality_name"]
        for policy in policies
        if policy["municipality_name"] is not None
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_run_id": run_id,
        "county": county.name,
        "state": county.state,
        "method": (
            "Policy-authorized static GET"
            + (" with robots-gated browser fallback" if with_browser else "")
            + "; every redirect target is robots-checked before access; no listing "
            "HTML or document bodies retained."
        ),
        "summary": {
            "policy_rows": len(policies),
            "configured_sources": len(entries),
            "distinct_listing_urls": len(results_by_url),
            "municipalities_represented": len(municipalities),
            "rights_status": dict(sorted(rights_counts.items())),
            "terms_review_status": dict(sorted(terms_counts.items())),
            "listing_status": dict(sorted(status_counts.items())),
            "documents_discovered_across_policy_rows": sum(
                result["discovered_document_count"] for result in results
            ),
            "documents_collectable_across_policy_rows": sum(
                result["document_count"] for result in results
            ),
        },
        "results": results,
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            repo_root
            / "docs"
            / "research"
            / "york-pa-municipal-source-static-audit-2026-08-27.json"
        ),
        help="JSON artifact path",
    )
    parser.add_argument(
        "--with-browser",
        action="store_true",
        help="Use the production Playwright fallback only after a successful static GET",
    )
    args = parser.parse_args()

    database = make_database_resource()
    database.setup_for_execution(None)
    try:
        report = build_report(database, with_browser=args.with_browser)
    finally:
        database.teardown_after_execution(None)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], indent=2))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
