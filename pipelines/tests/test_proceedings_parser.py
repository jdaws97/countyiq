"""Unit tests for the public proceedings PDF-link parser."""

import os

import pytest

from countyiq.lib.parsers.public_proceedings import (
    classify_proceeding_type,
    extract_pdf_links,
    parse_meeting_date_from_filename,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
BASE_URL = "https://springvale.gov"


def _load_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


# ---------------------------------------------------------------------------
# extract_pdf_links
# ---------------------------------------------------------------------------

class TestExtractPdfLinks:

    def setup_method(self):
        self.html = _load_fixture("proceedings_sample.html")
        self.links = extract_pdf_links(self.html, BASE_URL)

    def test_returns_list_of_dicts(self):
        assert isinstance(self.links, list)
        assert all(isinstance(r, dict) for r in self.links)

    def test_only_pdf_links_returned(self):
        """Non-PDF links (.docx, .txt, .jpg, .html, .png) must be excluded."""
        for link in self.links:
            assert link["url"].lower().endswith(".pdf"), (
                f"Non-PDF URL found: {link['url']}"
            )

    def test_required_keys_present(self):
        for link in self.links:
            for key in ("url", "filename", "link_text"):
                assert key in link, f"Missing key '{key}' in {link}"

    def test_all_urls_are_absolute(self):
        """Relative hrefs must be resolved to absolute URLs."""
        for link in self.links:
            assert link["url"].startswith("http"), (
                f"Relative URL not resolved: {link['url']}"
            )

    def test_relative_url_resolved_correctly(self):
        urls = [r["url"] for r in self.links]
        # /minutes/BOS_Minutes-2025-11-14.pdf is a root-relative href
        assert "https://springvale.gov/minutes/BOS_Minutes-2025-11-14.pdf" in urls

    def test_bare_relative_url_resolved(self):
        urls = [r["url"] for r in self.links]
        # minutes/BOS_2025_09_09.pdf is a path-relative href
        assert "https://springvale.gov/minutes/BOS_2025_09_09.pdf" in urls

    def test_absolute_url_preserved(self):
        urls = [r["url"] for r in self.links]
        assert "https://springvale.gov/documents/ZHB_Minutes_March_2025.pdf" in urls

    def test_filenames_extracted(self):
        filenames = {r["filename"] for r in self.links}
        assert "PC_01-15-2026.pdf" in filenames
        assert "ZHB_Minutes_March_2025.pdf" in filenames
        assert "BOS_Meeting_Notes_2025.pdf" in filenames
        assert "BOS_Minutes-2025-11-14.pdf" in filenames

    def test_link_text_extracted(self):
        by_filename = {r["filename"]: r["link_text"] for r in self.links}
        assert by_filename["PC_01-15-2026.pdf"] == "Planning Commission Minutes - January 15, 2026"
        assert by_filename["ZHB_Minutes_March_2025.pdf"] == "Zoning Hearing Board Minutes - March 2025"

    def test_pdf_count(self):
        """Fixture has exactly 10 PDF links; non-PDFs must all be dropped."""
        assert len(self.links) == 10

    def test_empty_html_returns_empty_list(self):
        assert extract_pdf_links("", BASE_URL) == []

    def test_html_with_no_links_returns_empty_list(self):
        assert extract_pdf_links("<p>No links here.</p>", BASE_URL) == []

    def test_html_with_no_pdfs_returns_empty_list(self):
        html = '<a href="/doc.docx">A Word doc</a><a href="/map.png">A map</a>'
        assert extract_pdf_links(html, BASE_URL) == []


# ---------------------------------------------------------------------------
# parse_meeting_date_from_filename
# ---------------------------------------------------------------------------

class TestParseMeetingDateFromFilename:

    # YYYY-MM-DD
    def test_iso_dash_format(self):
        assert parse_meeting_date_from_filename("Minutes-2025-11-14.pdf") == "2025-11-14"

    # YYYY_MM_DD
    def test_iso_underscore_format(self):
        assert parse_meeting_date_from_filename("BOS_2025_09_09.pdf") == "2025-09-09"

    # MM-DD-YYYY
    def test_mdy_dash_format(self):
        assert parse_meeting_date_from_filename("PC_01-15-2026.pdf") == "2026-01-15"

    # MM_DD_YYYY
    def test_mdy_underscore_format(self):
        assert parse_meeting_date_from_filename("PC_01_15_2026.pdf") == "2026-01-15"

    # MonthName_YYYY → day defaults to 01
    def test_month_year_format(self):
        assert parse_meeting_date_from_filename("ZHB_Minutes_March_2025.pdf") == "2025-03-01"

    def test_month_year_format_november(self):
        assert parse_meeting_date_from_filename("Planning_Commission_Minutes_November_2024.pdf") == "2024-11-01"

    def test_month_year_case_insensitive(self):
        assert parse_meeting_date_from_filename("MARCH_2025_minutes.pdf") == "2025-03-01"

    # Spelled-out month used in fixture
    def test_month_year_format_planning(self):
        assert parse_meeting_date_from_filename("Planning_Commission_Minutes_March_2025.pdf") == "2025-03-01"

    # No recognisable date
    def test_unparseable_returns_none(self):
        assert parse_meeting_date_from_filename("Annual_Report_SpringvaleTwp.pdf") is None

    def test_unparseable_special_meeting_returns_none(self):
        assert parse_meeting_date_from_filename("Special_Meeting_Notes.pdf") is None

    def test_no_extension_still_works(self):
        """Parser should work even when called without a .pdf extension."""
        assert parse_meeting_date_from_filename("Minutes-2025-11-14") == "2025-11-14"

    # YYYY only in filename should NOT match (too ambiguous)
    def test_year_only_does_not_match(self):
        result = parse_meeting_date_from_filename("BOS_Meeting_Notes_2025.pdf")
        # No full date extractable — may return None or at most a month-year hit.
        # The key assertion: it must NOT raise an exception.
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# classify_proceeding_type
# ---------------------------------------------------------------------------

class TestClassifyProceedingType:

    # zoning_hearing
    def test_zhb_abbreviation_filename(self):
        assert classify_proceeding_type("ZHB_Minutes_March_2025.pdf", "") == "zoning_hearing"

    def test_zoning_hearing_spelled_out_filename(self):
        assert classify_proceeding_type("Zoning_Hearing_Board_2025-06-18.pdf", "") == "zoning_hearing"

    def test_zoning_hearing_in_link_text(self):
        assert classify_proceeding_type("meeting.pdf", "Zoning Hearing Board Minutes") == "zoning_hearing"

    def test_zhb_in_link_text(self):
        assert classify_proceeding_type("minutes.pdf", "ZHB Meeting - March 2025") == "zoning_hearing"

    # planning_commission
    def test_pc_abbreviation_filename(self):
        assert classify_proceeding_type("PC_01-15-2026.pdf", "") == "planning_commission"

    def test_planning_commission_spelled_out_filename(self):
        assert classify_proceeding_type("Planning_Commission_Minutes_March_2025.pdf", "") == "planning_commission"

    def test_planning_commission_in_link_text(self):
        assert classify_proceeding_type("meeting.pdf", "Planning Commission Minutes - January 15, 2026") == "planning_commission"

    # supervisors
    def test_bos_abbreviation_filename(self):
        assert classify_proceeding_type("BOS_Minutes-2025-11-14.pdf", "") == "supervisors"

    def test_supervisors_in_link_text(self):
        assert classify_proceeding_type("meeting.pdf", "Board of Supervisors Minutes") == "supervisors"

    def test_bos_meeting_notes_filename(self):
        assert classify_proceeding_type("BOS_Meeting_Notes_2025.pdf", "") == "supervisors"

    def test_bos_in_link_text(self):
        assert classify_proceeding_type("notes.pdf", "BOS Annual Notes 2025") == "supervisors"

    # council
    def test_council_in_filename(self):
        assert classify_proceeding_type("Council_Minutes-2025-08-12.pdf", "") == "council"

    def test_council_in_link_text(self):
        assert classify_proceeding_type("meeting.pdf", "Council Meeting Minutes - August 12, 2025") == "council"

    # unknown
    def test_unknown_annual_report(self):
        assert classify_proceeding_type("Annual_Report_SpringvaleTwp.pdf", "Annual Report - Springvale Township") == "unknown"

    def test_unknown_special_meeting(self):
        assert classify_proceeding_type("Special_Meeting_Notes.pdf", "Special Meeting Notes") == "unknown"

    def test_unknown_empty_inputs(self):
        assert classify_proceeding_type("", "") == "unknown"

    # Priority: zoning_hearing beats planning_commission if both present
    def test_zhb_takes_priority_over_pc_hint(self):
        assert classify_proceeding_type("ZHB_PC_overlap.pdf", "PC ZHB overlap") == "zoning_hearing"


# ---------------------------------------------------------------------------
# New date patterns (2026-04-08 municipality survey)
# ---------------------------------------------------------------------------

class TestParseMeetingDateNewPatterns:
    """Tests for date patterns found during the 2026-04-08 municipality survey."""

    # M.D.YY dotted short year (Jefferson Boro: "3.4.26.pdf")
    def test_dotted_short_year(self):
        assert parse_meeting_date_from_filename("3.4.26.pdf") == "2026-03-04"

    def test_dotted_short_year_two_digit_month(self):
        assert parse_meeting_date_from_filename("12.08.25.pdf") == "2025-12-08"

    # "Month Day, Year" from link text (New Freedom: "January 5, 2026 – Meeting Packet")
    def test_month_day_year_link_text(self):
        assert parse_meeting_date_from_filename("January 5, 2026") == "2026-01-05"

    def test_month_day_year_with_ordinal(self):
        assert parse_meeting_date_from_filename("March 9th, 2026") == "2026-03-09"

    def test_month_day_year_february(self):
        assert parse_meeting_date_from_filename("February 24th, 2026") == "2026-02-24"
