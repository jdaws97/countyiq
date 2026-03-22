"""Unit tests for assessment portal HTML parser."""

import os
import pytest

from countyiq.lib.parsers.assessment import (
    parid_to_pidn,
    parse_search_results_page,
    get_total_found,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestParidToPidn:
    def test_standard_conversion(self):
        assert parid_to_pidn("460000001000100000") == "4600001001000"

    def test_another_district(self):
        assert parid_to_pidn("010000023004500000") == "0100023045000"

    def test_parid_with_letters(self):
        assert parid_to_pidn("24000K0F0012A00000") == "2400KF012A000"

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
        assert row["parid"] == "460000001000100000"
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
