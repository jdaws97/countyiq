"""Unit tests for public proceedings scraper helper functions.

Tests the pure helpers without requiring a database connection.
The _already_exists and _content_hash_exists functions require DB
and are integration-tested separately.
"""

import hashlib
import io
import os
import zipfile
from datetime import date

import pytest
import requests

from countyiq.assets.scrapers.public_proceedings import (
    _DocumentRequestBudget,
    _clear_implausible_future_dates,
    _document_priority,
    _extract_raw_text,
    _filter_allowed_document_links,
    _link_belongs_to_entry,
    _resolve_drive_folders,
    _resolved_document_filename,
    _safe_name,
    _sanitize_meeting_date,
    _upgrade_reviewed_document_url,
    _valid_document_content,
)
from countyiq.lib.robots import (
    RobotsDeniedError,
    RobotsPolicy,
    SourceOriginDeniedError,
    get_with_robots,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


class TestSafeName:
    def test_simple_name(self):
        assert _safe_name("Carroll Twp Board of Supervisors") == "carroll_twp_board_of_supervisors"

    def test_special_characters(self):
        assert _safe_name("York City Zoning Hearing Board") == "york_city_zoning_hearing_board"

    def test_strips_leading_trailing(self):
        result = _safe_name("  Hellam Twp  ")
        assert not result.startswith("_")
        assert not result.endswith("_")


class TestContentHash:
    """Verify that our SHA-256 approach produces deterministic, distinct hashes."""

    def test_same_content_same_hash(self):
        data = b"Hello World PDF Content"
        h1 = hashlib.sha256(data).hexdigest()
        h2 = hashlib.sha256(data).hexdigest()
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = hashlib.sha256(b"January 2026 Minutes").hexdigest()
        h2 = hashlib.sha256(b"February 2026 Minutes").hexdigest()
        assert h1 != h2

    def test_hash_is_64_char_hex(self):
        h = hashlib.sha256(b"test").hexdigest()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestDocumentBudget:
    def test_enforces_total_and_per_body_caps(self):
        budget = _DocumentRequestBudget(total_limit=3, per_body_limit=2)

        assert budget.reserve("York City")
        assert budget.reserve("York City")
        assert not budget.reserve("York City")
        assert budget.reserve("Dover Township")
        assert not budget.reserve("Hanover Borough")
        assert budget.claimed == 3

    def test_newer_documents_sort_first(self):
        links = [
            {"filename": "minutes-2024-01-02.pdf", "link_text": ""},
            {"filename": "minutes-2026-02-03.pdf", "link_text": ""},
            {"filename": "minutes-undated.pdf", "link_text": ""},
        ]
        ordered = sorted(links, key=_document_priority, reverse=True)
        assert [link["filename"] for link in ordered] == [
            "minutes-2026-02-03.pdf",
            "minutes-2024-01-02.pdf",
            "minutes-undated.pdf",
        ]


class TestMeetingDateSanitization:
    def test_rejects_implausibly_future_date(self):
        value, rejected = _sanitize_meeting_date(
            "2030-05-11", today=date(2026, 8, 30), max_future_days=90
        )
        assert value is None
        assert rejected is True

    def test_keeps_plausible_date(self):
        value, rejected = _sanitize_meeting_date(
            "2026-09-15", today=date(2026, 8, 30), max_future_days=90
        )
        assert value == "2026-09-15"
        assert rejected is False

    def test_existing_future_dates_are_repaired_with_same_cutoff(self):
        class Cursor:
            def __init__(self):
                self.params = None
                self.closed = False

            def execute(self, _query, params):
                self.params = params

            def fetchall(self):
                return [(1,), (2,)]

            def close(self):
                self.closed = True

        cursor = Cursor()

        class Database:
            def cursor(self):
                return cursor

        assert _clear_implausible_future_dates(
            Database(), max_future_days=90
        ) == 2
        assert cursor.params == (90,)
        assert cursor.closed is True


class _Log:
    def warning(self, *_args, **_kwargs):
        pass


@pytest.fixture(autouse=True)
def _allow_reserved_example_domains(monkeypatch):
    """HTTP behavior tests mock transport; URL-safety tests live separately."""
    monkeypatch.setattr("countyiq.lib.robots.assert_public_http_url", lambda _url: None)


class _Response:
    def __init__(
        self,
        status_code: int,
        text: str = "",
        *,
        headers: dict | None = None,
        url: str = "https://example.gov/robots.txt",
    ):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.url = url

    def close(self):
        pass


class TestRobotsPolicy:
    """robots.txt decisions allow an explicit/missing policy and fail closed
    when access rules cannot be established."""

    def test_missing_robots_allows(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: _Response(404))
        assert RobotsPolicy("CountyIQ/1.0").allowed("https://example.gov/minutes.pdf")

    def test_explicit_disallow_blocks(self, monkeypatch):
        monkeypatch.setattr(
            requests,
            "get",
            lambda *_args, **_kwargs: _Response(200, "User-agent: *\nDisallow: /private"),
        )
        assert not RobotsPolicy("CountyIQ/1.0").allowed(
            "https://example.gov/private/minutes.pdf"
        )

    def test_named_product_token_matches_honest_browser_user_agent(self, monkeypatch):
        requested_headers = []

        def respond(_url, **kwargs):
            requested_headers.append(kwargs.get("headers"))
            return _Response(
                200,
                "User-agent: CountyIQ\nDisallow: /private\n"
                "User-agent: *\nAllow: /",
            )

        monkeypatch.setattr(requests, "get", respond)
        user_agent = (
            "Mozilla/5.0 (compatible; CountyIQ/1.0; +https://countyiq.app)"
        )
        policy = RobotsPolicy(user_agent, product_token="CountyIQ")

        assert not policy.allowed("https://example.gov/private/minutes.pdf")
        assert requested_headers == [{"User-Agent": user_agent}]

    def test_wildcard_and_end_anchor_rules_are_enforced(self, monkeypatch):
        monkeypatch.setattr(
            requests,
            "get",
            lambda *_args, **_kwargs: _Response(
                200,
                "User-agent: *\n"
                "Disallow: /*.pdf$\n"
                "Allow: /public/*.pdf$",
            ),
        )
        policy = RobotsPolicy("CountyIQ/1.0", product_token="CountyIQ")

        assert not policy.allowed("https://example.gov/private/minutes.pdf")
        assert policy.allowed("https://example.gov/public/minutes.pdf")
        assert policy.allowed("https://example.gov/private/minutes.pdf?download=1")

    def test_network_error_fails_closed(self, monkeypatch):
        def fail(*_args, **_kwargs):
            raise requests.RequestException("offline")

        monkeypatch.setattr(requests, "get", fail)
        assert not RobotsPolicy("CountyIQ/1.0").allowed(
            "https://example.gov/minutes.pdf"
        )

    def test_empty_policy_fails_closed(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: _Response(200, ""))
        assert not RobotsPolicy("CountyIQ/1.0").allowed(
            "https://example.gov/minutes.pdf"
        )

    def test_browser_response_can_replace_cached_network_failure(self, monkeypatch):
        def fail(*_args, **_kwargs):
            raise requests.RequestException("direct transport unavailable")

        monkeypatch.setattr(requests, "get", fail)
        policy = RobotsPolicy("CountyIQ/1.0")
        url = "https://example.gov/minutes.pdf"
        assert not policy.allowed(url)

        policy.cache_browser_response(
            "https://example.gov/robots.txt",
            text="User-agent: *\nAllow: /",
            status_code=200,
        )

        assert policy.allowed(url)

    def test_browser_response_remains_fail_closed_for_disallow(self, monkeypatch):
        def fail(*_args, **_kwargs):
            raise requests.RequestException("direct transport unavailable")

        monkeypatch.setattr(requests, "get", fail)
        policy = RobotsPolicy("CountyIQ/1.0")
        policy.cache_browser_response(
            "https://example.gov/robots.txt",
            text="User-agent: *\nDisallow: /private",
            status_code=200,
        )

        assert not policy.allowed("https://example.gov/private/minutes.pdf")

    def test_redirect_target_is_checked_before_fetch(self, monkeypatch):
        requested = []

        def fake_get(url, *_args, **_kwargs):
            requested.append(url)
            if url == "https://example.gov/robots.txt":
                return _Response(404, url=url)
            if url == "https://example.gov/minutes":
                return _Response(
                    302,
                    headers={"Location": "https://vendor.example/private/minutes"},
                    url=url,
                )
            if url == "https://vendor.example/robots.txt":
                return _Response(
                    200,
                    "User-agent: *\nDisallow: /private",
                    url=url,
                )
            raise AssertionError(f"unexpected access to {url}")

        monkeypatch.setattr(requests, "get", fake_get)

        with pytest.raises(RobotsDeniedError, match="explicit_disallow"):
            get_with_robots(
                "https://example.gov/minutes",
                robots=RobotsPolicy("CountyIQ/1.0"),
            )

        assert "https://vendor.example/private/minutes" not in requested

    def test_redirect_drops_origin_scoped_validators(self, monkeypatch):
        request_headers = []

        def fake_get(url, *args, **kwargs):
            request_headers.append((url, kwargs.get("headers")))
            if url.endswith("/robots.txt"):
                return _Response(404, url=url)
            if url == "https://example.gov/minutes":
                return _Response(
                    302,
                    headers={"Location": "https://vendor.example/minutes"},
                    url=url,
                )
            return _Response(200, "ok", url=url)

        monkeypatch.setattr(requests, "get", fake_get)
        response = get_with_robots(
            "https://example.gov/minutes",
            robots=RobotsPolicy("CountyIQ/1.0"),
            headers={"User-Agent": "CountyIQ/1.0", "If-None-Match": '"abc"'},
        )

        assert response.url == "https://vendor.example/minutes"
        final_headers = next(
            headers
            for url, headers in request_headers
            if url == "https://vendor.example/minutes"
        )
        assert final_headers == {"User-Agent": "CountyIQ/1.0"}

    def test_unreviewed_redirect_origin_is_blocked_before_access(self, monkeypatch):
        requested = []

        def fake_get(url, *_args, **_kwargs):
            requested.append(url)
            if url == "https://example.gov/robots.txt":
                return _Response(404, url=url)
            if url == "https://example.gov/minutes":
                return _Response(
                    302,
                    headers={"Location": "https://vendor.example/minutes"},
                    url=url,
                )
            raise AssertionError(f"unexpected access to {url}")

        monkeypatch.setattr(requests, "get", fake_get)

        with pytest.raises(SourceOriginDeniedError, match="vendor.example"):
            get_with_robots(
                "https://example.gov/minutes",
                robots=RobotsPolicy("CountyIQ/1.0"),
                allowed_origins={"https://example.gov"},
            )

        assert "https://vendor.example/minutes" not in requested


class TestSharedListingAttribution:
    def test_classified_document_routes_to_matching_body(self):
        supervisor = {"proceeding_type": "board_of_supervisors"}
        zoning = {"proceeding_type": "zoning_hearing"}
        siblings = [supervisor, zoning]

        assert _link_belongs_to_entry(zoning, siblings, "zoning_hearing")
        assert not _link_belongs_to_entry(supervisor, siblings, "zoning_hearing")

    def test_unknown_document_routes_once(self):
        first = {"proceeding_type": "board_of_supervisors"}
        second = {"proceeding_type": "planning_commission"}
        siblings = [first, second]

        assert _link_belongs_to_entry(first, siblings, "unknown")
        assert not _link_belongs_to_entry(second, siblings, "unknown")


class TestDocumentValidation:
    def test_accepts_expected_magic_bytes(self):
        assert _valid_document_content("minutes.pdf", b"%PDF-1.7")
        assert _valid_document_content("minutes.docx", b"PK\x03\x04zip")
        assert _valid_document_content(
            "minutes.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1binary"
        )

    def test_rejects_html_error_page(self):
        assert not _valid_document_content("minutes.pdf", b"<html>blocked</html>")

    @pytest.mark.parametrize(
        ("content_type", "content", "expected"),
        [
            ("application/pdf", b"%PDF-1.7", "meeting.pdf"),
            ("application/msword", b"legacy", "meeting.doc"),
            (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                b"PK\x03\x04zip",
                "meeting.docx",
            ),
            ("application/octet-stream", b"%PDF-1.7", "meeting.pdf"),
        ],
    )
    def test_extensionless_route_uses_response_document_type(
        self, content_type, content, expected
    ):
        response = requests.Response()
        response.headers["Content-Type"] = content_type
        response._content = content
        response.url = "https://example.gov/document/meeting/"

        assert _resolved_document_filename("meeting.pdf", response) == expected

    def test_legacy_http_link_upgrades_only_to_reviewed_https_origin(self):
        url = "http://minutes.example.gov/files/january.pdf"
        assert _upgrade_reviewed_document_url(
            url,
            frozenset({"https://minutes.example.gov"}),
        ) == "https://minutes.example.gov/files/january.pdf"
        assert _upgrade_reviewed_document_url(
            url,
            frozenset({"https://other.example.gov"}),
        ) == url

    def test_mixed_origin_listing_preserves_approved_documents(self):
        links = [
            {
                "url": "http://minutes.example.gov/files/january.pdf",
                "filename": "january.pdf",
                "link_text": "January minutes",
            },
            {
                "url": "https://vendor.example/files/february.pdf",
                "filename": "february.pdf",
                "link_text": "February minutes",
            },
        ]

        allowed, blocked = _filter_allowed_document_links(
            links,
            frozenset({"https://minutes.example.gov"}),
        )

        assert [link["url"] for link in allowed] == [
            "https://minutes.example.gov/files/january.pdf"
        ]
        assert blocked == {"https://vendor.example/files/february.pdf"}


class TestResolveDriveFolders:
    """Drive folder links on a minutes page resolve to downloadable files via
    the embeddedfolderview endpoint (static HTML, fetched with the injected
    fetcher so tests stay offline)."""

    def setup_method(self):
        self.listing = _load_fixture("drive_folder_listing.html")

    def test_no_drive_links_returns_empty(self):
        assert _resolve_drive_folders("<a href='/m.pdf'>m</a>", lambda url: "") == []

    def test_resolves_folder_to_file_records(self):
        html = (
            '<a href="https://drive.google.com/drive/folders/1AAA_rootFolder'
            'IdXXXXXXXXXXXXXXXX">2026 Minutes</a>'
        )
        fetched = []

        def fake_fetch(url):
            fetched.append(url)
            # Root folder returns the fixture; its subfolder returns nothing.
            return self.listing if "1AAA_rootFolderIdXXXXXXXXXXXXXXXX" in url else ""

        links = _resolve_drive_folders(html, fake_fetch)
        urls = [rec["url"] for rec in links]
        assert (
            "https://drive.google.com/uc?export=download&id="
            "1uQkJCqVWe_edLUUgTv9mbR8GbDGGCyQj"
        ) in urls
        assert fetched[0] == (
            "https://drive.google.com/embeddedfolderview"
            "?id=1AAA_rootFolderIdXXXXXXXXXXXXXXXX"
        )

    def test_recurses_into_subfolders(self):
        html = (
            '<a href="https://drive.google.com/drive/folders/1AAA_rootFolder'
            'IdXXXXXXXXXXXXXXXX">2026</a>'
        )
        fetched = []

        def fake_fetch(url):
            fetched.append(url)
            return self.listing if "1AAA_rootFolderIdXXXXXXXXXXXXXXXX" in url else ""

        _resolve_drive_folders(html, fake_fetch)
        # Fixture's subfolder (Draft Minutes) must also be listed.
        assert any("1lQixUBlT3x0nenJl4x6dvswwAQsvZy8G" in u for u in fetched)

    def test_does_not_refetch_seen_folders(self):
        html = (
            '<a href="https://drive.google.com/drive/folders/1AAA_rootFolder'
            'IdXXXXXXXXXXXXXXXX">a</a>'
            '<a href="https://drive.google.com/drive/folders/1AAA_rootFolder'
            'IdXXXXXXXXXXXXXXXX">b</a>'
        )
        fetched = []

        def fake_fetch(url):
            fetched.append(url)
            return ""

        _resolve_drive_folders(html, fake_fetch)
        assert len(fetched) == 1

    def test_fetch_failure_is_soft(self):
        html = (
            '<a href="https://drive.google.com/drive/folders/1AAA_rootFolder'
            'IdXXXXXXXXXXXXXXXX">a</a>'
        )
        assert _resolve_drive_folders(html, lambda url: None) == []


class TestExtractRawText:
    """Text extraction dispatches on filename extension."""

    def test_docx_uses_word_extractor(self):
        xml = (
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxml'
            'formats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
            'Motion approved.</w:t></w:r></w:p></w:body></w:document>'
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml", xml)
        assert _extract_raw_text("minutes 1-3-22.docx", buf.getvalue()) == "Motion approved."

    def test_legacy_doc_returns_none(self):
        assert _extract_raw_text("080326agenda-.doc", b"\xd0\xcf\x11\xe0 binary") is None

    def test_corrupt_pdf_returns_none(self):
        assert _extract_raw_text("minutes.pdf", b"not a real pdf") is None

    def test_nul_characters_are_removed_before_database_storage(self, monkeypatch):
        monkeypatch.setattr(
            "countyiq.assets.scrapers.public_proceedings.extract_text_from_pdf_bytes",
            lambda _data: "Applicant\x00Procedure",
        )

        assert _extract_raw_text("application.pdf", b"pdf") == "ApplicantProcedure"
