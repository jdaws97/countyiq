import json
from pathlib import Path

from countyiq.lib.parsers.arcgis_parcels import parse_parcels_features

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parse_parcels_returns_correct_count():
    raw = json.loads((FIXTURES_DIR / "parcels_sample.json").read_text())
    records = parse_parcels_features(raw)
    assert len(records) == 2


def test_parse_parcels_maps_pidn():
    raw = json.loads((FIXTURES_DIR / "parcels_sample.json").read_text())
    records = parse_parcels_features(raw)
    pidns = {r["pidn"] for r in records}
    assert pidns == {"4300006006500", "4300006007000"}


def test_parse_parcels_maps_fields():
    raw = json.loads((FIXTURES_DIR / "parcels_sample.json").read_text())
    records = parse_parcels_features(raw)
    r = next(r for r in records if r["pidn"] == "4300006006500")
    assert r["owner_full"] == "SMITH JOHN A"
    assert r["propadr"] == "123 MAIN ST"
    assert r["aprtotal"] == "110000.0"
    assert r["class"] == "R"
    assert r["municipality"] == "Conewago Twp"
    assert r["school_dis"] == "01402"
    assert r["acres"] == "1.24"


def test_parse_parcels_skips_no_pidn():
    raw = [{"attributes": {"OWNER_FULL": "NO PIDN"}}]
    records = parse_parcels_features(raw)
    assert len(records) == 0


def test_parse_parcels_handles_nulls():
    raw = json.loads((FIXTURES_DIR / "parcels_sample.json").read_text())
    records = parse_parcels_features(raw)
    r = next(r for r in records if r["pidn"] == "4300006007000")
    assert r["prev_owner"] is None
    assert r["prev_price"] is None
