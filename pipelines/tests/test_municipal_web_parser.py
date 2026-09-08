"""Unit tests for bounded municipal HTML meeting-page helpers."""

from countyiq.lib.parsers.municipal_web import (
    extract_html_record_text,
    extract_meeting_page_links,
    select_listing_region,
)


class TestExtractMeetingPageLinks:
    def test_extracts_yorkana_article_with_safe_base_and_deduplication(self):
        html = """
        <base href="/">
        <a href="meetings/2026/january-minutes#top">January Minutes</a>
        <a href="/meetings/2026/january-minutes">Duplicate</a>
        <a href="/notices/roadwork">Roadwork</a>
        """

        assert extract_meeting_page_links(
            html,
            "https://yorkana.example/news/",
            path_prefixes=("/meetings/",),
        ) == [
            {
                "url": "https://yorkana.example/meetings/2026/january-minutes",
                "filename": "january-minutes.html",
                "link_text": "January Minutes",
                "format": "html",
            }
        ]

    def test_keeps_nested_proudcity_meeting_paths_and_queries(self):
        html = (
            '<a href="/meetings/council/2026-01-12/?view=full#minutes">'
            "Council meeting</a>"
        )

        records = extract_meeting_page_links(
            html,
            "https://springettsbury.example/meetings/",
            path_prefixes=("/meetings/",),
        )

        assert records[0]["url"] == (
            "https://springettsbury.example/meetings/council/2026-01-12/?view=full"
        )
        assert records[0]["filename"] == "2026-01-12.html"

    def test_rejects_other_origins_unsafe_base_and_unapproved_paths(self):
        html = """
        <base href="https://untrusted.example/meetings/">
        <a href="/meetings/local">Local</a>
        <a href="https://other.example/meetings/remote">Remote</a>
        <a href="javascript:alert(1)">Script</a>
        <a href="#section">Fragment</a>
        <a href="/news/update">News</a>
        """

        assert extract_meeting_page_links(
            html,
            "https://borough.example/current/",
            path_prefixes=("/meetings/",),
        ) == [
            {
                "url": "https://borough.example/meetings/local",
                "filename": "local.html",
                "link_text": "Local",
                "format": "html",
            }
        ]


class TestExtractHtmlRecordText:
    def test_extracts_springettsbury_main_content_without_hidden_chrome(self):
        html = """
        <main id="main-content">
          <nav>Navigation</nav>
          <h1>January 12 Council Meeting</h1>
          <p>Called to order at 7:00 p.m.</p>
          <ul><li>Approved minutes</li><li>Adjourned</li></ul>
          <table><tr><th>Vote</th><td>5-0</td></tr></table>
          <p hidden>Hidden draft</p>
          <span class="sr-only">Screen reader control</span>
          <button>Print</button>
          <footer>Footer text</footer>
        </main>
        """

        assert extract_html_record_text(html, content_selector="#main-content") == (
            "January 12 Council Meeting\n"
            "Called to order at 7:00 p.m.\n"
            "Approved minutes\n"
            "Adjourned\n"
            "Vote\n"
            "5-0"
        )

    def test_returns_none_for_missing_or_empty_selected_content(self):
        assert (
            extract_html_record_text("<main></main>", content_selector="#missing")
            is None
        )
        assert (
            extract_html_record_text(
                "<main id='main'><script>x</script></main>", content_selector="#main"
            )
            is None
        )


def test_heading_region_excludes_adjacent_municipal_bodies():
    html = """
    <h2>Planning Commission Minutes</h2><p><a href="planning.pdf">June</a></p>
    <h2>Supervisors Minutes</h2><p><a href="supervisors.pdf">June</a></p>
    <h2>Zoning Hearing Board</h2><p><a href="zoning.pdf">June</a></p>
    """
    selected = select_listing_region(html, heading="Supervisors Minutes")
    assert "supervisors.pdf" in selected
    assert "planning.pdf" not in selected
    assert "zoning.pdf" not in selected


def test_archive_article_selector_excludes_ambiguous_other_body_filenames():
    html = """
    <main>
      <article><h2><a href="/planning-commission-2025/">Planning Commission</a></h2>
        <a href="12.17.25.pdf">December</a></article>
      <article><h2><a href="/board-of-supervisors-2025/">Board of Supervisors</a></h2>
        <a href="January-Minutes.pdf">January</a></article>
    </main>
    """
    selected = select_listing_region(
        html, selector="main article:has(h2 a[href*='/board-of-supervisors-'])"
    )
    assert "January-Minutes.pdf" in selected
    assert "12.17.25.pdf" not in selected


def test_peach_bottom_wrapped_headings_select_only_supervisor_column():
    from countyiq.lib.county_config import get_county_config

    html = """
    <div class="et_pb_row">
      <div class="et_pb_column"><div><div><h2>Planning Commission Minutes</h2></div></div>
        <div><a href="Planning-12-2024.pdf">December</a></div></div>
      <div class="et_pb_column"><div><div><h2>Supervisors Minutes</h2></div></div>
        <div><a href="Supervisor-1-5-2026.pdf">January</a></div></div>
    </div>
    """
    selector = next(
        selector
        for body, selector, _ in get_county_config("york").proceeding_listing_regions
        if body == "Peach Bottom Twp Board of Supervisors"
    )
    selected = select_listing_region(html, selector=selector)
    assert "Supervisor-1-5-2026.pdf" in selected
    assert "Planning-12-2024.pdf" not in selected
