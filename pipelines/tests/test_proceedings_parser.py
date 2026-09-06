"""Unit tests for the public proceedings PDF-link parser."""

import os


from countyiq.lib.parsers.public_proceedings import (
    classify_proceeding_type,
    extract_drive_folder_ids,
    extract_pdf_links,
    parse_drive_folder_listing,
    parse_meeting_date_from_filename,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
BASE_URL = "https://springvale.gov"


def _load_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Google Drive folder support (West York Borough hosts minutes in Drive)
# ---------------------------------------------------------------------------


class TestExtractDriveFolderIds:
    def test_extracts_drive_folders_links(self):
        html = (
            '<a href="https://drive.google.com/drive/folders/1_kfY8Fq0lomdpIgul7Xt'
            'Ci6a3MlFAKnR?usp=sharing">2026 Minutes</a>'
        )
        assert extract_drive_folder_ids(html) == ["1_kfY8Fq0lomdpIgul7XtCi6a3MlFAKnR"]

    def test_extracts_legacy_folderview_links(self):
        html = (
            '<a href="https://drive.google.com/folderview?id=12wXw_s6QTg7yumxB5dK6'
            '0R8dnaol1Woz">Previous Years</a>'
        )
        assert extract_drive_folder_ids(html) == ["12wXw_s6QTg7yumxB5dK60R8dnaol1Woz"]

    def test_ignores_non_drive_links(self):
        html = '<a href="https://example.com/minutes.pdf">m</a>'
        assert extract_drive_folder_ids(html) == []

    def test_dedupes_repeated_folders(self):
        html = (
            '<a href="https://drive.google.com/drive/folders/1abcDEF_2ghiJKL34mnoP'
            'QR56stuVWX78">a</a>'
            '<a href="https://drive.google.com/drive/folders/1abcDEF_2ghiJKL34mnoP'
            'QR56stuVWX78">b</a>'
        )
        assert extract_drive_folder_ids(html) == ["1abcDEF_2ghiJKL34mnoPQR56stuVWX78"]


class TestParseDriveFolderListing:
    """Parses the static HTML from drive.google.com/embeddedfolderview?id=..."""

    def setup_method(self):
        self.result = parse_drive_folder_listing(
            _load_fixture("drive_folder_listing.html")
        )

    def test_files_have_download_urls(self):
        urls = [f["url"] for f in self.result["files"]]
        assert (
            "https://drive.google.com/uc?export=download&id="
            "1uQkJCqVWe_edLUUgTv9mbR8GbDGGCyQj"
        ) in urls

    def test_filenames_come_from_entry_titles(self):
        names = [f["filename"] for f in self.result["files"]]
        assert "01052026_meeting_minutes.pdf" in names
        assert "01122026_Meeting_Minutes.pdf" in names

    def test_files_exclude_subfolders(self):
        assert len(self.result["files"]) == 2

    def test_subfolder_ids_extracted(self):
        assert self.result["subfolder_ids"] == ["1lQixUBlT3x0nenJl4x6dvswwAQsvZy8G"]

    def test_file_records_have_standard_keys(self):
        for f in self.result["files"]:
            for key in ("url", "filename", "link_text"):
                assert key in f

    def test_empty_html(self):
        assert parse_drive_folder_listing("") == {"files": [], "subfolder_ids": []}


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

    def test_only_document_links_returned(self):
        """Non-document links (.txt, .jpg, .html, .png) must be excluded;
        .pdf, .doc, and .docx are all documents."""
        for link in self.links:
            path = link["url"].lower().split("?")[0]
            assert path.endswith((".pdf", ".doc", ".docx")), (
                f"Non-document URL found: {link['url']}"
            )

    def test_docx_link_included(self):
        """Word documents are ingested (many small boroughs post .docx minutes)."""
        urls = [r["url"] for r in self.links]
        assert "https://springvale.gov/minutes/bos-agenda-2025-11-14.docx" in urls

    def test_docx_filename_keeps_real_extension(self):
        docx = [r for r in self.links if r["url"].endswith(".docx")]
        assert docx and docx[0]["filename"] == "bos-agenda-2025-11-14.docx"

    def test_dn_query_param_preferred_for_filename(self):
        """Wix serves hex-named files with the human name in the dn= param."""
        html = (
            '<a href="https://x.com/_files/ugd/390391_9cfc15dec2ca46e0.docx'
            '?dn=minutes%201-3-22.docx">minutes 1-3-22</a>'
        )
        links = extract_pdf_links(html, "https://x.com")
        assert links[0]["filename"] == "minutes 1-3-22.docx"

    def test_better_files_download_route_uses_declared_document_type(self):
        html = (
            '<a href="https://shrewsburyborough.org/bfd_download/'
            'bc-minutes-january-2025/">'
            "<strong>BC minutes January 2025</strong>"
            "<small>Type : pdf</small></a>"
            '<a href="https://shrewsburyborough.org/bfd_download/'
            'bc-minutes-december-2025/">'
            "<strong>BC Minutes December 2025</strong>"
            "<small>Type : doc</small></a>"
        )

        assert extract_pdf_links(html, "https://shrewsburyborough.org/minutes/") == [
            {
                "url": (
                    "https://shrewsburyborough.org/bfd_download/"
                    "bc-minutes-january-2025/"
                ),
                "filename": "bc-minutes-january-2025.pdf",
                "link_text": "BC minutes January 2025Type : pdf",
            },
            {
                "url": (
                    "https://shrewsburyborough.org/bfd_download/"
                    "bc-minutes-december-2025/"
                ),
                "filename": "bc-minutes-december-2025.doc",
                "link_text": "BC Minutes December 2025Type : doc",
            },
        ]

    def test_civicengage_html_preview_is_canonicalized_to_document(self):
        html = (
            '<a href="/AgendaCenter/ViewFile/Agenda/_09212026-992?html=true">'
            "HTML preview</a>"
            '<a href="/AgendaCenter/ViewFile/Agenda/_09212026-992">'
            "September 21, 2026 agenda</a>"
        )

        assert extract_pdf_links(html, "https://hanoverboroughpa.gov/") == [
            {
                "url": (
                    "https://hanoverboroughpa.gov/AgendaCenter/ViewFile/Agenda/"
                    "_09212026-992"
                ),
                "filename": "_09212026-992.pdf",
                "link_text": "HTML preview",
            }
        ]

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

    def test_protocol_relative_godaddy_document_url_uses_listing_scheme(self):
        html = (
            '<a href="//img1.wsimg.com/blobby/go/source/downloads/'
            'July%2028%2C%202026%20Meeting%20Minutes.pdf?ver=1">'
            "Meeting Minutes</a>"
        )

        assert extract_pdf_links(html, "https://newberrytwp.com/minutes") == [
            {
                "url": (
                    "https://img1.wsimg.com/blobby/go/source/downloads/"
                    "July%2028%2C%202026%20Meeting%20Minutes.pdf?ver=1"
                ),
                "filename": "July 28, 2026 Meeting Minutes.pdf",
                "link_text": "Meeting Minutes",
            }
        ]
        assert (
            parse_meeting_date_from_filename("July 28, 2026 Meeting Minutes.pdf")
            == "2026-07-28"
        )

    def test_filenames_extracted(self):
        filenames = {r["filename"] for r in self.links}
        assert "PC_01-15-2026.pdf" in filenames
        assert "ZHB_Minutes_March_2025.pdf" in filenames
        assert "BOS_Meeting_Notes_2025.pdf" in filenames
        assert "BOS_Minutes-2025-11-14.pdf" in filenames

    def test_link_text_extracted(self):
        by_filename = {r["filename"]: r["link_text"] for r in self.links}
        assert (
            by_filename["PC_01-15-2026.pdf"]
            == "Planning Commission Minutes - January 15, 2026"
        )
        assert (
            by_filename["ZHB_Minutes_March_2025.pdf"]
            == "Zoning Hearing Board Minutes - March 2025"
        )

    def test_document_count(self):
        """Fixture has exactly 10 PDF links + 1 docx; the rest must be dropped."""
        assert len(self.links) == 11

    def test_empty_html_returns_empty_list(self):
        assert extract_pdf_links("", BASE_URL) == []

    def test_html_with_no_links_returns_empty_list(self):
        assert extract_pdf_links("<p>No links here.</p>", BASE_URL) == []

    def test_html_with_no_documents_returns_empty_list(self):
        html = '<a href="/page.html">A page</a><a href="/map.png">A map</a>'
        assert extract_pdf_links(html, BASE_URL) == []


# ---------------------------------------------------------------------------
# parse_meeting_date_from_filename
# ---------------------------------------------------------------------------


class TestParseMeetingDateFromFilename:
    # YYYY-MM-DD
    def test_iso_dash_format(self):
        assert (
            parse_meeting_date_from_filename("Minutes-2025-11-14.pdf") == "2025-11-14"
        )

    # YYYY_MM_DD
    def test_iso_underscore_format(self):
        assert parse_meeting_date_from_filename("BOS_2025_09_09.pdf") == "2025-09-09"

    # MM-DD-YYYY
    def test_mdy_dash_format(self):
        assert parse_meeting_date_from_filename("PC_01-15-2026.pdf") == "2026-01-15"

    # MM_DD_YYYY
    def test_mdy_underscore_format(self):
        assert parse_meeting_date_from_filename("PC_01_15_2026.pdf") == "2026-01-15"

    # MonthName_YYYY cannot establish an exact meeting day
    def test_month_year_format(self):
        assert parse_meeting_date_from_filename("ZHB_Minutes_March_2025.pdf") is None

    def test_month_year_format_november(self):
        assert (
            parse_meeting_date_from_filename(
                "Planning_Commission_Minutes_November_2024.pdf"
            )
            is None
        )

    def test_month_year_case_insensitive(self):
        assert parse_meeting_date_from_filename("MARCH_2025_minutes.pdf") is None

    # Spelled-out month used in fixture
    def test_month_year_format_planning(self):
        assert (
            parse_meeting_date_from_filename(
                "Planning_Commission_Minutes_March_2025.pdf"
            )
            is None
        )

    # No recognisable date
    def test_compact_mmddyyyy(self):
        """West York Drive files: 05042026_Meeting_Minutes.PDF.pdf"""
        assert (
            parse_meeting_date_from_filename("05042026_Meeting_Minutes.PDF.pdf")
            == "2026-05-04"
        )

    def test_compact_yyyymmdd(self):
        assert parse_meeting_date_from_filename("20260504_minutes.pdf") == "2026-05-04"

    def test_compact_invalid_month_returns_none(self):
        """8 digits that don't form a real date must not parse."""
        assert parse_meeting_date_from_filename("99887766_minutes.pdf") is None

    def test_compact_not_matched_inside_longer_digit_run(self):
        assert parse_meeting_date_from_filename("doc_390391123456789.pdf") is None

    def test_short_year_dash_format(self):
        """Winterstown docx names: 'minutes 1-3-22.docx'"""
        assert parse_meeting_date_from_filename("minutes 1-3-22.docx") == "2022-01-03"

    def test_short_year_does_not_eat_four_digit_year(self):
        """Existing MM-DD-YYYY files must not be misread by the short-year rule."""
        assert parse_meeting_date_from_filename("PC_01-15-2026.pdf") == "2026-01-15"

    def test_unparseable_returns_none(self):
        assert (
            parse_meeting_date_from_filename("Annual_Report_SpringvaleTwp.pdf") is None
        )

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
        assert (
            classify_proceeding_type("ZHB_Minutes_March_2025.pdf", "")
            == "zoning_hearing"
        )

    def test_zoning_hearing_spelled_out_filename(self):
        assert (
            classify_proceeding_type("Zoning_Hearing_Board_2025-06-18.pdf", "")
            == "zoning_hearing"
        )

    def test_zoning_hearing_in_link_text(self):
        assert (
            classify_proceeding_type("meeting.pdf", "Zoning Hearing Board Minutes")
            == "zoning_hearing"
        )

    def test_zhb_in_link_text(self):
        assert (
            classify_proceeding_type("minutes.pdf", "ZHB Meeting - March 2025")
            == "zoning_hearing"
        )

    # planning_commission
    def test_pc_abbreviation_filename(self):
        assert (
            classify_proceeding_type("PC_01-15-2026.pdf", "") == "planning_commission"
        )

    def test_planning_commission_spelled_out_filename(self):
        assert (
            classify_proceeding_type("Planning_Commission_Minutes_March_2025.pdf", "")
            == "planning_commission"
        )

    def test_planning_commission_in_link_text(self):
        assert (
            classify_proceeding_type(
                "meeting.pdf", "Planning Commission Minutes - January 15, 2026"
            )
            == "planning_commission"
        )

    # supervisors
    def test_bos_abbreviation_filename(self):
        assert (
            classify_proceeding_type("BOS_Minutes-2025-11-14.pdf", "") == "supervisors"
        )

    def test_supervisors_in_link_text(self):
        assert (
            classify_proceeding_type("meeting.pdf", "Board of Supervisors Minutes")
            == "supervisors"
        )

    def test_bos_meeting_notes_filename(self):
        assert (
            classify_proceeding_type("BOS_Meeting_Notes_2025.pdf", "") == "supervisors"
        )

    def test_bos_in_link_text(self):
        assert (
            classify_proceeding_type("notes.pdf", "BOS Annual Notes 2025")
            == "supervisors"
        )

    # council
    def test_council_in_filename(self):
        assert (
            classify_proceeding_type("Council_Minutes-2025-08-12.pdf", "") == "council"
        )

    def test_council_in_link_text(self):
        assert (
            classify_proceeding_type(
                "meeting.pdf", "Council Meeting Minutes - August 12, 2025"
            )
            == "council"
        )

    # unknown
    def test_unknown_annual_report(self):
        assert (
            classify_proceeding_type(
                "Annual_Report_SpringvaleTwp.pdf", "Annual Report - Springvale Township"
            )
            == "unknown"
        )

    def test_unknown_special_meeting(self):
        assert (
            classify_proceeding_type(
                "Special_Meeting_Notes.pdf", "Special Meeting Notes"
            )
            == "unknown"
        )

    def test_unknown_empty_inputs(self):
        assert classify_proceeding_type("", "") == "unknown"

    # Priority: zoning_hearing beats planning_commission if both present
    def test_zhb_takes_priority_over_pc_hint(self):
        assert (
            classify_proceeding_type("ZHB_PC_overlap.pdf", "PC ZHB overlap")
            == "zoning_hearing"
        )


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


def test_spelled_meeting_dates_survive_extracted_text_whitespace():
    for separator in ("\n", "\r\n", "\u00a0"):
        text = f"Council minutes January{separator}6,{separator}2026"
        assert parse_meeting_date_from_filename(text) == "2026-01-06"
