"""Tests for roads parser."""

import json
import pathlib

from countyiq.lib.parsers.roads import parse_roads_features

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "roads_sample.json"


def test_parse_roads_returns_records():
    raw = json.loads(FIXTURE.read_text())
    records = parse_roads_features(raw["features"])
    assert len(records) > 0


def test_parse_roads_field_mapping():
    raw = json.loads(FIXTURE.read_text())
    records = parse_roads_features(raw["features"])
    rec = records[0]
    assert "rcl_nguid" in rec
    assert "street_name" in rec
    assert "road_class" in rec
    assert "speed_limit" in rec
    assert "inc_muni_l" in rec
    assert "RCL_NGUID" not in rec
    assert "StreetName" not in rec


def test_parse_roads_skips_missing_key():
    features = [{"attributes": {"StreetName": "MAIN"}}]
    records = parse_roads_features(features)
    assert len(records) == 0


def test_parse_roads_preserves_int_fields():
    features = [
        {"attributes": {"RCL_NGUID": "abc-123", "SpeedLimit": 35, "FromAddr_L": 100}}
    ]
    records = parse_roads_features(features)
    assert records[0]["speed_limit"] == 35
    assert records[0]["from_addr_l"] == 100
