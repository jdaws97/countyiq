import json
from pathlib import Path

from countyiq.lib.parsers.fema import parse_fema_geojson, FEMA_SENTINEL

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parse_returns_all_features():
    geojson = json.loads((FIXTURES_DIR / "fema_flood_sample.geojson").read_text())
    records = parse_fema_geojson(geojson)
    assert len(records) == 5


def test_parse_maps_columns_correctly():
    geojson = json.loads((FIXTURES_DIR / "fema_flood_sample.geojson").read_text())
    records = parse_fema_geojson(geojson)
    r = next(r for r in records if r["fld_ar_id"] == "42133C_5239")
    assert r["fld_zone"] == "AE"
    assert r["sfha_tf"] == "T"
    assert r["study_typ"] == "SFHAs WITH HIGH FLOOD RISK"
    assert r["source_cit"] == "42133C_STUDY1"
    assert r["static_bfe"] == 450.5
    assert r["v_datum"] == "NAVD88"
    assert r["dfirm_id"] == "42133C"


def test_parse_converts_sentinels_to_none():
    geojson = json.loads((FIXTURES_DIR / "fema_flood_sample.geojson").read_text())
    records = parse_fema_geojson(geojson)
    r = next(r for r in records if r["fld_ar_id"] == "42133C_5240")
    assert r["static_bfe"] is None
    assert r["depth"] is None
    assert r["fld_zone"] == "X"
    assert r["sfha_tf"] == "F"


def test_parse_preserves_valid_numeric_values():
    geojson = json.loads((FIXTURES_DIR / "fema_flood_sample.geojson").read_text())
    records = parse_fema_geojson(geojson)
    r = next(r for r in records if r["fld_ar_id"] == "42133C_2001")
    assert r["static_bfe"] == 15.0
    assert r["depth"] == 3.5
    assert r["fld_zone"] == "VE"


def test_parse_includes_geojson_geometry():
    geojson = json.loads((FIXTURES_DIR / "fema_flood_sample.geojson").read_text())
    records = parse_fema_geojson(geojson)
    r = next(r for r in records if r["fld_ar_id"] == "42133C_5239")
    assert "geojson" in r
    assert r["geojson"]["type"] == "Polygon"


def test_parse_handles_null_geometry():
    geojson = json.loads((FIXTURES_DIR / "fema_flood_sample.geojson").read_text())
    records = parse_fema_geojson(geojson)
    r = next(r for r in records if r["fld_ar_id"] == "42133C_9999")
    assert "geojson" not in r
    assert r["fld_zone"] == "X"


def test_parse_empty_feature_collection():
    geojson = {"type": "FeatureCollection", "features": []}
    records = parse_fema_geojson(geojson)
    assert records == []


def test_parse_skips_features_without_fld_ar_id():
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[-76.38, 39.73], [-76.37, 39.73], [-76.37, 39.74], [-76.38, 39.74], [-76.38, 39.73]]]},
                "properties": {"FLD_ZONE": "AE", "SFHA_TF": "T"},
            }
        ],
    }
    records = parse_fema_geojson(geojson)
    assert records == []


def test_sentinel_value():
    assert FEMA_SENTINEL == -9999
