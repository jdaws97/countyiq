"""Unit tests for the SODA registered-business parser (data.pa.gov xvd7-5r2c)."""

from datetime import date

from countyiq.lib.parsers.pa_dos_entities import (
    STATUS_NOT_FOUND,
    STATUS_PRESENT,
    make_not_found_record,
    parse_soda_business_rows,
)
from countyiq.assets.scrapers.pa_dos_entities import (
    _get_pending_entity_names,
    _positive_int_env,
)


def _row(**overrides) -> dict:
    row = {
        "business_name": "York Holdings, LLC",
        "filing_number": "0007123456",
        "address_line1": "10 Main Street",
        "city": "York",
        "state": "PA",
        "zip": "17401",
        "typeofbusinessregistration": "Domestic Limited Liability Company",
        "creationdate": "2019-05-01T00:00:00.000",
        "party_type": "President",
        "first_name": "JANE",
        "middle_name": "Q",
        "last_name": "DOE",
        "shortcountyname": "York",
        "county_code": "67",
    }
    row.update(overrides)
    return row


class TestParseSodaBusinessRows:

    def test_matches_despite_case_and_punctuation_drift(self):
        record = parse_soda_business_rows([_row()], "YORK HOLDINGS LLC")
        assert record is not None
        assert record["entity_name"] == "YORK HOLDINGS LLC"  # search key preserved
        assert record["matched_name"] == "York Holdings, LLC"  # as published
        assert record["entity_number"] == "0007123456"
        assert record["entity_type"] == "Domestic Limited Liability Company"
        assert record["status"] == STATUS_PRESENT
        assert record["formation_date"] == date(2019, 5, 1)
        assert record["office_address"] == "10 Main Street, York, PA, 17401"

    def test_llc_dot_variants_match(self):
        rows = [_row(business_name="York Holdings, L.L.C.")]
        assert parse_soda_business_rows(rows, "YORK HOLDINGS LLC") is not None

    def test_officer_rows_group_into_one_record(self):
        rows = [
            _row(),
            _row(party_type="Secretary", first_name="JOHN", middle_name=None, last_name="SMITH"),
        ]
        record = parse_soda_business_rows(rows, "YORK HOLDINGS LLC")
        assert record["officers"] == [
            {"party_type": "President", "name": "JANE Q DOE"},
            {"party_type": "Secretary", "name": "JOHN SMITH"},
        ]

    def test_duplicate_officer_rows_dedupe(self):
        record = parse_soda_business_rows([_row(), _row()], "YORK HOLDINGS LLC")
        assert len(record["officers"]) == 1

    def test_unrelated_fulltext_hits_do_not_match(self):
        rows = [_row(business_name="York Holdings of Ohio LLC")]
        assert parse_soda_business_rows(rows, "YORK HOLDINGS LLC") is None

    def test_multiple_filings_take_most_recent(self):
        rows = [
            _row(filing_number="0001", creationdate="2005-01-01T00:00:00.000"),
            _row(filing_number="0002", creationdate="2021-03-15T00:00:00.000"),
        ]
        record = parse_soda_business_rows(rows, "YORK HOLDINGS LLC")
        assert record["entity_number"] == "0002"

    def test_empty_rows_return_none(self):
        assert parse_soda_business_rows([], "YORK HOLDINGS LLC") is None

    def test_missing_creationdate_still_parses(self):
        record = parse_soda_business_rows([_row(creationdate=None)], "YORK HOLDINGS LLC")
        assert record is not None
        assert record["formation_date"] is None


class TestMakeNotFoundRecord:

    def test_negative_cache_record(self):
        record = make_not_found_record("GHOST VENTURES LP")
        assert record["entity_name"] == "GHOST VENTURES LP"
        assert record["status"] == STATUS_NOT_FOUND
        assert record["matched_name"] == ""
        assert record["officers"] == []
        assert record["formation_date"] is None


class _RecordingDatabase:
    def __init__(self):
        self.query = ""
        self.params = ()

    def execute(self, query, params=()):
        self.query = query
        self.params = params
        return [("ALPHA HOLDINGS LLC",), ("BETA PROPERTIES LP",)]


def test_pending_entity_batch_has_limit_and_differentiated_ttls():
    database = _RecordingDatabase()

    names = _get_pending_entity_names(
        database,
        limit=25,
        found_ttl_days=30,
        not_found_ttl_days=180,
    )

    assert names == ["ALPHA HOLDINGS LLC", "BETA PROPERTIES LP"]
    assert "LIMIT %s" in database.query
    assert database.params[-4:] == (STATUS_NOT_FOUND, 180, 30, 25)


def test_positive_int_env_never_turns_zero_into_unbounded(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_TEST_LIMIT", "0")
    assert _positive_int_env("COUNTYIQ_TEST_LIMIT", 500) == 500
