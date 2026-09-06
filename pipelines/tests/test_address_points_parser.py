"""Tests for address points parser."""

import json
import inspect
import pathlib

from countyiq.lib.parsers.address_points import parse_address_points_features
from countyiq.assets.arcgis.address_points import _geom_scd2_upsert_streaming

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "address_points_sample.json"


def test_parse_address_points_returns_records():
    raw = json.loads(FIXTURE.read_text())
    records = parse_address_points_features(raw["features"])
    assert len(records) > 0


def test_parse_address_points_field_mapping():
    raw = json.loads(FIXTURE.read_text())
    records = parse_address_points_features(raw["features"])
    rec = records[0]
    assert "site_nguid" in rec
    assert "add_number" in rec
    assert "street_name" in rec
    assert "inc_muni" in rec
    assert "post_code" in rec
    assert "Site_NGUID" not in rec
    assert "StreetName" not in rec


def test_parse_address_points_skips_missing_key():
    features = [{"attributes": {"StreetName": "MAIN"}}]
    records = parse_address_points_features(features)
    assert len(records) == 0


def test_parse_address_points_preserves_numeric_fields():
    features = [
        {
            "attributes": {
                "Site_NGUID": "abc",
                "Add_Number": 123,
                "Long": -76.7,
                "Lat": 39.9,
            }
        }
    ]
    records = parse_address_points_features(features)
    assert records[0]["add_number"] == 123
    assert records[0]["long"] == -76.7
    assert records[0]["lat"] == 39.9


def test_county_sized_streaming_upsert_indexes_staged_source_key():
    source = inspect.getsource(_geom_scd2_upsert_streaming)

    index_position = source.index("idx_tmp_address_points_site_nguid")
    update_position = source.index("UPDATE {fqn}")
    assert index_position < update_position
    assert "ANALYZE _tmp_address_points" in source
