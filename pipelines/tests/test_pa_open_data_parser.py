import json
from pathlib import Path

from countyiq.lib.parsers.pa_open_data import parse_soda_records

FIXTURES_DIR = Path(__file__).parent / "fixtures"
DATASET_ID = "xvd7-5r2c"


def _load_sample():
    return json.loads((FIXTURES_DIR / "pa_open_data_sample.json").read_text())


def test_parse_returns_correct_count():
    """Records with :id are included; the one without :id is skipped."""
    records = _load_sample()
    parsed = parse_soda_records(records, DATASET_ID)
    assert len(parsed) == 4  # 5 raw records, 1 missing :id


def test_parse_sets_dataset_id():
    records = _load_sample()
    parsed = parse_soda_records(records, DATASET_ID)
    assert all(r["dataset_id"] == DATASET_ID for r in parsed)


def test_parse_extracts_record_id():
    records = _load_sample()
    parsed = parse_soda_records(records, DATASET_ID)
    ids = [r["record_id"] for r in parsed]
    assert "row-abc1-2345-6789" in ids
    assert "row-def2-3456-7890" in ids


def test_parse_stores_full_record_as_data():
    records = _load_sample()
    parsed = parse_soda_records(records, DATASET_ID)
    r = next(r for r in parsed if r["record_id"] == "row-abc1-2345-6789")
    assert r["data"]["business_name"] == "Acme Widgets Llc"
    assert r["data"]["shortcountyname"] == "York"
    assert r["data"]["filing_number"] == "0001234567"


def test_parse_skips_records_without_id():
    records = _load_sample()
    parsed = parse_soda_records(records, DATASET_ID)
    names = [r["data"]["business_name"] for r in parsed]
    assert "No Id Business Llc" not in names


def test_parse_empty_list():
    parsed = parse_soda_records([], DATASET_ID)
    assert parsed == []


def test_parse_custom_record_id_field():
    """Use filing_number as record_id instead of :id."""
    records = _load_sample()
    parsed = parse_soda_records(records, DATASET_ID, record_id_field="filing_number")
    assert len(parsed) == 5  # All records have filing_number
    ids = [r["record_id"] for r in parsed]
    assert "0001234567" in ids
    assert "0002345678" in ids


def test_parse_record_id_is_string():
    """record_id should always be a string even if source field is numeric."""
    records = [{"filing_number": 12345, "shortcountyname": "York"}]
    parsed = parse_soda_records(records, DATASET_ID, record_id_field="filing_number")
    assert len(parsed) == 1
    assert parsed[0]["record_id"] == "12345"
    assert isinstance(parsed[0]["record_id"], str)


def test_parse_includes_all_counties():
    """Parser doesn't filter by county — that's the API's job via query param."""
    records = _load_sample()
    parsed = parse_soda_records(records, DATASET_ID)
    counties = [r["data"]["shortcountyname"] for r in parsed]
    assert "Lancaster" in counties
