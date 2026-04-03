"""Unit tests for PA DOS corporate entity parser."""

import json
import os

from countyiq.lib.parsers.pa_dos_entities import (
    parse_filing_detail,
    parse_search_results,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name: str) -> dict:
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# parse_search_results
# ---------------------------------------------------------------------------

class TestParseSearchResults:

    def test_returns_list_of_dicts(self):
        data = _load_fixture("pa_dos_search_response.json")
        results = parse_search_results(data)
        assert isinstance(results, list)
        assert all(isinstance(r, dict) for r in results)

    def test_correct_count(self):
        data = _load_fixture("pa_dos_search_response.json")
        results = parse_search_results(data)
        assert len(results) == 3

    def test_required_fields_present(self):
        data = _load_fixture("pa_dos_search_response.json")
        required = [
            "entity_name",
            "entity_number",
            "entity_type",
            "status",
            "formation_date",
            "registered_agent_name",
            "registered_agent_address",
            "office_address",
            "officers",
            "source_url",
        ]
        for record in parse_search_results(data):
            for field in required:
                assert field in record, f"Missing field: {field}"

    def test_first_record_values(self):
        data = _load_fixture("pa_dos_search_response.json")
        first = parse_search_results(data)[0]
        assert first["entity_name"] == "Smith Holdings Company, LLC"
        assert first["entity_number"] == "4346768"
        assert first["entity_type"] == "Domestic Limited Liability Company"
        assert first["status"] == "Active"
        assert first["office_address"] == "6224 THOMAN DRIVE, SPRING GROVE, PA 17362"

    def test_formation_date_parsed(self):
        data = _load_fixture("pa_dos_search_response.json")
        results = parse_search_results(data)
        from datetime import date
        assert results[0]["formation_date"] == date(2015, 4, 10)
        assert results[1]["formation_date"] == date(2019, 11, 22)

    def test_inactive_status_preserved(self):
        data = _load_fixture("pa_dos_search_response.json")
        results = parse_search_results(data)
        assert results[2]["status"] == "Inactive"

    def test_source_url_format(self):
        data = _load_fixture("pa_dos_search_response.json")
        results = parse_search_results(data)
        for record in results:
            assert record["source_url"].startswith(
                "https://file.dos.pa.gov/search/business#"
            )
            assert record["entity_number"] in record["source_url"]

    def test_empty_results_returns_empty_list(self):
        assert parse_search_results({"results": []}) == []

    def test_missing_results_key_returns_empty_list(self):
        assert parse_search_results({}) == []

    def test_agents_and_officers_empty(self):
        """Registered agent and officers are unavailable from public search."""
        data = _load_fixture("pa_dos_search_response.json")
        for record in parse_search_results(data):
            assert record["registered_agent_name"] == ""
            assert record["registered_agent_address"] == ""
            assert record["officers"] == []


# ---------------------------------------------------------------------------
# parse_filing_detail
# ---------------------------------------------------------------------------

class TestParseFilingDetail:

    def test_returns_dict(self):
        data = _load_fixture("pa_dos_detail_response.json")
        result = parse_filing_detail(data, entity_name="Smith Holdings Company, LLC")
        assert isinstance(result, dict)

    def test_required_fields_present(self):
        data = _load_fixture("pa_dos_detail_response.json")
        required = [
            "entity_name",
            "entity_number",
            "entity_type",
            "status",
            "formation_date",
            "registered_agent_name",
            "registered_agent_address",
            "office_address",
            "officers",
            "source_url",
        ]
        result = parse_filing_detail(data, entity_name="fallback")
        for field in required:
            assert field in result, f"Missing field: {field}"

    def test_office_address_assembled(self):
        data = _load_fixture("pa_dos_detail_response.json")
        result = parse_filing_detail(data, entity_name="fallback")
        assert "6224 THOMAN DRIVE" in result["office_address"]
        assert "SPRING GROVE" in result["office_address"]
        assert "PA" in result["office_address"]
        assert "17362" in result["office_address"]

    def test_formation_date_parsed(self):
        data = _load_fixture("pa_dos_detail_response.json")
        from datetime import date
        result = parse_filing_detail(data, entity_name="fallback")
        assert result["formation_date"] == date(2015, 4, 10)

    def test_entity_type_uses_filing_type(self):
        """Detail view has filingType which is more specific than entityType."""
        data = _load_fixture("pa_dos_detail_response.json")
        result = parse_filing_detail(data, entity_name="fallback")
        assert result["entity_type"] == "Domestic Limited Liability Company"

    def test_source_url_contains_entity_number(self):
        data = _load_fixture("pa_dos_detail_response.json")
        result = parse_filing_detail(data, entity_name="fallback")
        assert "4346768" in result["source_url"]

    def test_entity_name_from_response(self):
        data = _load_fixture("pa_dos_detail_response.json")
        result = parse_filing_detail(data, entity_name="should not use this")
        assert result["entity_name"] == "Smith Holdings Company, LLC"

    def test_entity_name_fallback(self):
        data = _load_fixture("pa_dos_detail_response.json")
        data_no_name = {k: v for k, v in data.items() if k != "entityName"}
        result = parse_filing_detail(data_no_name, entity_name="Fallback Name")
        assert result["entity_name"] == "Fallback Name"

    def test_missing_registered_office(self):
        data = _load_fixture("pa_dos_detail_response.json")
        data_no_office = {k: v for k, v in data.items() if k != "registeredOffice"}
        result = parse_filing_detail(data_no_office, entity_name="test")
        assert result["office_address"] == ""
