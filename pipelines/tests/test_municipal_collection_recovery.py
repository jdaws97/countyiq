"""Exercise collection boundaries and HTML evidence through the full asset."""

from types import SimpleNamespace

import pytest
from countyiq.assets.scrapers import public_proceedings as scraper
from countyiq.lib.county_config import CountyConfig, municipality_source_key

BODY = "Fixture Borough Council"
LISTING = "https://fixture.example/meeting-minutes/"
DOCUMENT = "https://fixture.example/meeting-minutes-june-2026/"
LISTING_HTML = """
<a href="/meeting-minutes-may-2026/">May 2026 minutes</a>
<a href="/meeting-minutes-june-2026/">June 2026 minutes</a>
"""
DOCUMENT_HTML = """
<nav>Unrelated navigation text</nav>
<div id="primary"><div class="post">
<h1>Meeting minutes June 2026</h1>
<div class="published-time">August 7, 2026</div>
<p>Monday June 8, 2026</p>
<p>The Borough Council met at the municipal building. The council approved
its previous meeting minutes and discussed the published public works agenda.</p>
</div></div>
"""


@pytest.fixture
def collection(monkeypatch):
    county = CountyConfig(
        name="Fixture County",
        municipality_websites=((BODY, LISTING, "borough_council"),),
        proceeding_browser_sources=(BODY,),
        proceeding_html_sources=((BODY, "/meeting-minutes-", "#primary .post"),),
    )
    authorization = SimpleNamespace(
        allowed_origins=frozenset({"https://fixture.example"}),
        robots_unavailable_risk_accepted=False,
        browser_transport_reviewed=True,
    )
    receipt = SimpleNamespace(
        inserted=[],
        archived=[],
        health=[],
        document_requests=[],
        authorization=authorization,
    )
    monkeypatch.setattr(scraper, "get_county_config", lambda: county)
    monkeypatch.setattr(
        scraper, "authorize_source", lambda *args, **kwargs: authorization
    )
    monkeypatch.setattr(
        scraper,
        "authorize_municipality_sources",
        lambda *args, **kwargs: {municipality_source_key(BODY): authorization},
    )
    monkeypatch.setattr(scraper, "require_source_use", lambda *args: None)
    monkeypatch.setattr(
        scraper, "_insert_proceeding", lambda **row: receipt.inserted.append(row)
    )
    monkeypatch.setattr(
        scraper, "_get_current_count", lambda database: len(receipt.inserted)
    )
    monkeypatch.setattr(
        scraper,
        "record_municipality_source_health",
        lambda *args, **row: receipt.health.append(row),
    )
    monkeypatch.setattr(scraper.time, "sleep", lambda seconds: None)
    monkeypatch.delenv("COUNTYIQ_PROCEEDINGS_SOURCE_KEYS", raising=False)
    monkeypatch.setenv("COUNTYIQ_PROCEEDINGS_MAX_DOCUMENTS_PER_BODY", "1")
    monkeypatch.setenv("COUNTYIQ_PROCEEDINGS_MAX_DOCUMENT_REQUESTS", "1")

    class Robots:
        def __init__(self, *args, **kwargs):
            pass

        def decision(self, url):
            return SimpleNamespace(allowed=True, reason="allowed")

        def allowed(self, url):
            return True

    class Browser:
        def __init__(self, *args):
            pass

        def fetch_robots(self, *args):
            return True

        def fetch_html(self, *args, **kwargs):
            return LISTING_HTML

        def fetch_document(self, url, *args, **kwargs):
            receipt.document_requests.append(url)
            if getattr(receipt, "download_error", False):
                raise RuntimeError("HTTP 403 from fixture publisher")
            return SimpleNamespace(content=DOCUMENT_HTML.encode(), headers={}, url=url)

        def close(self):
            pass

    def forbidden_http(*args, **kwargs):
        pytest.fail("Reviewed browser documents must not be downloaded again via HTTP")

    monkeypatch.setattr(scraper, "RobotsPolicy", Robots)
    monkeypatch.setattr(scraper, "_PlaywrightFetcher", Browser)
    monkeypatch.setattr(scraper, "get_with_robots", forbidden_http)
    log = SimpleNamespace(info=lambda *args: None, warning=lambda *args: None)
    context = SimpleNamespace(log=log, run_id="fixture")
    database = SimpleNamespace(execute=lambda *args: [])
    storage = SimpleNamespace(
        strict=True, archive=lambda *args, **kwargs: receipt.archived.append(args)
    )
    receipt.run = lambda: scraper.public_proceedings_scrape.op.compute_fn.decorated_fn(
        context, database, storage
    )
    return receipt


def test_browser_html_archive_and_meeting_date_share_one_request_budget(collection):
    result = collection.run()
    assert collection.document_requests == [DOCUMENT]
    assert len(collection.inserted) == 1
    record = collection.inserted[0]
    assert record["document_url"] == DOCUMENT
    assert record["meeting_date"] == "2026-06-08"
    assert "Borough Council" in record["raw_text"]
    assert "August 7" not in record["raw_text"]
    assert "navigation" not in record["raw_text"]
    assert collection.archived[0][1] == DOCUMENT_HTML.encode()
    assert collection.health[0]["listing_status"] == "budget_limited"
    assert result.metadata["document_requests_claimed"].value == 1


def test_browser_download_failure_remains_visible_without_transport_retry(collection):
    collection.download_error = True
    collection.run()
    assert collection.document_requests == [DOCUMENT]
    assert not collection.inserted
    assert not collection.archived
    assert collection.health[0]["listing_status"] == "partial_error"
    assert DOCUMENT in collection.health[0]["last_error"]
    assert "403" in collection.health[0]["last_error"]


def test_unreviewed_browser_profile_stops_before_network(collection):
    collection.authorization.browser_transport_reviewed = False
    with pytest.raises(RuntimeError, match="Browser transport is not reviewed"):
        collection.run()
    assert not collection.document_requests


def test_document_landing_page_resolves_attachment_before_download(
    collection, monkeypatch
):
    landing = "https://fixture.example/document/council-minutes-2026-06-08/"
    attachment = "https://fixture.example/uploads/Council-Minutes-2026-06-08.pdf"
    county = CountyConfig(
        name="Fixture County",
        municipality_websites=((BODY, LISTING, "borough_council"),),
        proceeding_browser_sources=(BODY,),
        proceeding_detail_sources=((BODY, "/document/"),),
    )
    monkeypatch.setattr(scraper, "get_county_config", lambda: county)

    def fetch_html(self, url, *args, **kwargs):
        if url == LISTING:
            return f'<a href="{landing}">Council Minutes 2026-06-08</a>'
        assert url == landing
        return f'<a href="{attachment}">Download</a>'

    def fetch_document(self, url, *args, **kwargs):
        collection.document_requests.append(url)
        return SimpleNamespace(content=b"%PDF-fixture", headers={}, url=url)

    monkeypatch.setattr(scraper._PlaywrightFetcher, "fetch_html", fetch_html)
    monkeypatch.setattr(scraper._PlaywrightFetcher, "fetch_document", fetch_document)
    monkeypatch.setattr(
        scraper,
        "_extract_raw_text",
        lambda *args: (
            "Council minutes: the council approved its previous minutes and reviewed public works."
        ),
    )
    collection.run()
    assert collection.document_requests == [attachment]
    assert collection.inserted[0]["document_url"] == attachment
    assert collection.health[0]["listing_status"] == "ok"
