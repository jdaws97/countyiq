"""Bounded official review snapshots, without project or approval inference."""

import hashlib
import re
import time
from datetime import UTC, date, datetime
from urllib.parse import unquote, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from countyiq.lib.parsers.yccd_plan_reviews import parse_plan_review_pdf
from countyiq.lib.robots import RobotsPolicy, get_with_robots, source_origin

USER_AGENT = "CountyIQ/1.0 (+https://countyiq.app)"
DOCUMENT_LINK = re.compile(
    r"^Plan-Review-Status-(\d{1,2})-(\d{1,2})-(\d{4})\.pdf$", re.IGNORECASE
)
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024


class _PoliteSession(requests.Session):
    def __init__(self, delay_seconds: float):
        super().__init__()
        self.delay_seconds = delay_seconds
        self.previous_request = time.monotonic()

    def get(self, *args, **kwargs):
        time.sleep(
            max(0.0, self.delay_seconds - (time.monotonic() - self.previous_request))
        )
        try:
            return super().get(*args, **kwargs)
        finally:
            self.previous_request = time.monotonic()


def select_latest_document(html: str, listing_url: str) -> tuple[str, str]:
    candidates = set()
    for anchor in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        url = urljoin(listing_url, anchor["href"])
        parsed = urlsplit(url)
        match = DOCUMENT_LINK.fullmatch(unquote(parsed.path).rsplit("/", 1)[-1])
        if not match:
            continue
        if source_origin(url) != source_origin(listing_url):
            raise ValueError("Review document link left the configured publisher")
        if not parsed.path.startswith("/wp-content/uploads/") or parsed.query:
            raise ValueError("Review document link changed its expected delivery path")
        month, day, year = (int(value) for value in match.groups())
        document_date = date(year, month, day)
        if document_date > datetime.now(UTC).date():
            raise ValueError("Review document date is in the future")
        candidates.add((document_date.isoformat(), url))
    if not candidates:
        raise ValueError("No dated review PDF was found on the configured listing")
    latest_date = max(item[0] for item in candidates)
    latest_urls = {url for stamp, url in candidates if stamp == latest_date}
    if len(latest_urls) != 1:
        raise ValueError("Multiple different review PDFs share the newest date")
    return latest_urls.pop(), latest_date


def make_snapshot(content: bytes, *, document_url: str, expected_date: str) -> dict:
    parsed = parse_plan_review_pdf(content)
    if parsed["document_date"] != expected_date:
        raise ValueError("PDF header date does not match the linked document date")
    digest = hashlib.sha256(content).hexdigest()
    rows = [
        {
            **row,
            "receipt_key": f"yccd:{digest}:{row['row_ordinal']}",
            "project_match": None,
        }
        for row in parsed["rows"]
    ]
    return {
        "schema_version": 1,
        "source_key": "yccd_plan_reviews",
        "document_url": document_url,
        "document_date": parsed["document_date"],
        "source_sha256": digest,
        "observed_at": datetime.now(UTC).isoformat(),
        "date_meaning": "submission_resubmission_or_complete_date_as_printed",
        "publication": "private_source_pilot",
        "rows": rows,
    }


def collect_snapshot(
    listing_url: str, *, delay_seconds: float = 5.0
) -> tuple[bytes, dict]:
    if urlsplit(listing_url).scheme != "https":
        raise ValueError("Review listing must use HTTPS")
    robots = RobotsPolicy(USER_AGENT, product_token="CountyIQ", timeout=20)
    # Prime the robots request before the session's first pacing interval.
    decision = robots.decision(listing_url)
    if not decision.allowed:
        raise ValueError(
            f"Publisher robots policy blocks review collection: {decision.reason}"
        )
    with _PoliteSession(max(5.0, delay_seconds)) as session:
        listing = _fetch_bytes(session, robots, listing_url, source_origin(listing_url))
        document_url, expected_date = select_latest_document(
            listing.decode("utf-8"), listing_url
        )
        content = _fetch_bytes(
            session, robots, document_url, source_origin(listing_url)
        )
    snapshot = make_snapshot(
        content, document_url=document_url, expected_date=expected_date
    )
    snapshot["listing_url"] = listing_url
    snapshot["listing_sha256"] = hashlib.sha256(listing).hexdigest()
    snapshot["robots"] = {
        "url": decision.robots_url,
        "status_code": decision.status_code,
        "reason": decision.reason,
    }
    return content, snapshot


def _fetch_bytes(session, robots, url: str, origin: str) -> bytes:
    with get_with_robots(
        url,
        robots=robots,
        requester=session,
        allowed_origins={origin},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
        stream=True,
        max_redirects=2,
    ) as response:
        response.raise_for_status()
        chunks = []
        size = 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > MAX_DOCUMENT_BYTES:
                raise ValueError("Review source exceeds the bounded download size")
            chunks.append(chunk)
        return b"".join(chunks)


def compare_snapshots(previous: dict, current: dict) -> dict:
    """Report membership changes; removal never implies a regulatory outcome."""
    if previous["source_key"] != current["source_key"]:
        raise ValueError("Cannot compare snapshots from different publishers")
    if current["document_date"] <= previous["document_date"]:
        raise ValueError("Comparison requires a later dated snapshot")

    def index(snapshot):
        indexed = {}
        for row in snapshot["rows"]:
            key = (
                row["municipality_as_printed"],
                row["permit_number"] or row["plan_name"],
            )
            if key in indexed:
                raise ValueError("Duplicate review identifiers need manual comparison")
            indexed[key] = row
        return indexed

    before, after = index(previous), index(current)
    return {
        "added": [after[key] for key in sorted(after.keys() - before.keys())],
        "removed_outcome_unknown": [
            before[key] for key in sorted(before.keys() - after.keys())
        ],
        "changed": [
            {"before": before[key], "after": after[key]}
            for key in sorted(before.keys() & after.keys())
            if any(
                before[key][field] != after[key][field]
                for field in ("plan_name", "administrative_date", "status")
            )
        ],
    }
