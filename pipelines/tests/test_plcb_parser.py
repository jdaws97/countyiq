from pathlib import Path

from york_county.lib.parsers.plcb import parse_plcb_csv

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parse_filters_to_york_county():
    csv_text = (FIXTURES_DIR / "plcb_sample.csv").read_text()
    records = parse_plcb_csv(csv_text)
    assert len(records) == 4  # 4 York County rows, 1 non-York excluded


def test_parse_maps_columns_correctly():
    csv_text = (FIXTURES_DIR / "plcb_sample.csv").read_text()
    records = parse_plcb_csv(csv_text)
    r = next(r for r in records if r["lid"] == "54316")
    assert r["license_number"] == "C5721"
    assert r["license_type"] == "Club (Liquor)"
    assert r["status"] == "Active"
    assert r["licensee"] == "SUSQUEHANNA FISH AND GAME ASSOCIATION INC"
    assert r["premises_name"] == "SUSQUEHANNA FISH AND GAME ASSOCIATION INC"
    assert r["premises_address"] == "7084 ROUND TOP LANE, WRIGHTSVILLE PA 17368"
    assert r["municipality"] == "Hellam Twp"


def test_parse_includes_expired_york_county():
    csv_text = (FIXTURES_DIR / "plcb_sample.csv").read_text()
    records = parse_plcb_csv(csv_text)
    expired = next(r for r in records if r["lid"] == "100809")
    assert expired["status"] == "Expired"
    assert expired["license_type"] == "Limited Distillery"


def test_parse_converts_empty_fields_to_none():
    csv_text = (FIXTURES_DIR / "plcb_sample.csv").read_text()
    records = parse_plcb_csv(csv_text)
    r = next(r for r in records if r["lid"] == "99999")
    assert r["premises_mailing_address"] is None
    assert r["premises_owner"] is None
    assert r["premises_manager"] is None
    # Non-empty fields still populated
    assert r["licensee"] == "TEST EMPTY FIELDS LLC"


def test_parse_empty_csv_returns_empty():
    csv_text = "LID,License Number,License Type,Status,Licensee,Premises,Premises Address,Premises Mailing Address,Premises Owner,Premises Manager,County,Municipality,Last Issue Date,Expiration Date\n"
    records = parse_plcb_csv(csv_text)
    assert records == []


def test_parse_handles_completely_wrong_headers():
    csv_text = "BAD_COL,Other Column\nfoo,bar\n"
    records = parse_plcb_csv(csv_text)
    assert records == []


def test_parse_handles_bom_prefix():
    csv_text = (FIXTURES_DIR / "plcb_sample.csv").read_text()
    bom_text = "\ufeff" + csv_text
    records = parse_plcb_csv(bom_text)
    assert len(records) == 4
    assert records[0]["lid"] is not None
