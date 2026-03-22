"""Unit tests for assessment portal HTML parser."""

import os
import pytest

from countyiq.lib.parsers.assessment import (
    parid_to_pidn,
    parse_search_results_page,
    parse_printable_summary,
    get_total_found,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestParidToPidn:
    def test_standard_conversion(self):
        # Real PARID from portal: 46-000-01-0001.00-00000
        assert parid_to_pidn("460000100010000000") == "4600000100000"

    def test_another_district(self):
        assert parid_to_pidn("010002300450000000") == "0100200500000"

    def test_parid_with_letters(self):
        assert parid_to_pidn("24000KF0012A000000") == "2400K002A0000"

    def test_short_input_returns_empty(self):
        assert parid_to_pidn("123") == ""

    def test_none_returns_empty(self):
        assert parid_to_pidn(None) == ""

    def test_empty_string_returns_empty(self):
        assert parid_to_pidn("") == ""


class TestGetTotalFound:
    def test_extracts_total(self):
        with open(os.path.join(FIXTURES, "assessment_search_results.html")) as f:
            html = f.read()
        assert get_total_found(html) == 9305

    def test_no_results_returns_zero(self):
        assert get_total_found("<html><body>No records found</body></html>") == 0


class TestParseSearchResults:
    def test_parses_three_rows(self):
        with open(os.path.join(FIXTURES, "assessment_search_results.html")) as f:
            html = f.read()
        results = parse_search_results_page(html)
        assert len(results) == 3

    def test_first_row_fields(self):
        with open(os.path.join(FIXTURES, "assessment_search_results.html")) as f:
            html = f.read()
        row = parse_search_results_page(html)[0]
        assert row["parid"] == "460000100010000000"
        assert row["owner_name"] == "PABON SOPHIA"
        assert row["address"] == "144 FINDLAY ST N"
        assert row["property_class"] == "R"

    def test_commercial_class(self):
        with open(os.path.join(FIXTURES, "assessment_search_results.html")) as f:
            html = f.read()
        row = parse_search_results_page(html)[2]
        assert row["property_class"] == "C"

    def test_html_entity_decoded(self):
        with open(os.path.join(FIXTURES, "assessment_search_results.html")) as f:
            html = f.read()
        row = parse_search_results_page(html)[1]
        assert row["owner_name"] == "GORDON GREGORY R & TAMMY J"


class TestParsePrintableSummary:
    @pytest.fixture
    def summary_html(self):
        with open(os.path.join(FIXTURES, "assessment_printable_summary.html")) as f:
            return f.read()

    def test_extracts_municipality(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert "SPRINGETTSBURY" in result["municipality"]

    def test_extracts_school_district(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert "YORK SUBURBAN" in result["school_district"]

    def test_extracts_assessed_values(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert result["assessed_land"] == 28530
        assert result["assessed_building"] == 79670
        assert result["assessed_total"] == 108200

    def test_extracts_land_use_code(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert result["land_use_code"] == "102"

    def test_extracts_sale_info(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert result["sale_date"] == "08-08-2018"
        assert result["sale_price"] == 160000

    def test_permits_is_list(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert isinstance(result["permits"], list)
        assert len(result["permits"]) >= 1
        assert "permit_date" in result["permits"][0]

    def test_delinquent_taxes_is_list(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert isinstance(result["delinquent_taxes"], list)

    def test_value_history_is_list(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert isinstance(result["value_history"], list)
        assert len(result["value_history"]) >= 1
