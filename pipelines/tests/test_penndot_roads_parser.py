"""Tests for PennDOT roads parser."""

import json
import pathlib

from countyiq.lib.parsers.penndot_roads import parse_penndot_roads_features

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "penndot_roads_sample.json"


def test_parse_penndot_roads_returns_records():
    raw = json.loads(FIXTURE.read_text())
    records = parse_penndot_roads_features(raw["features"])
    assert len(records) == 2  # third feature has null keys, should be skipped


def test_parse_penndot_roads_field_mapping():
    raw = json.loads(FIXTURE.read_text())
    records = parse_penndot_roads_features(raw["features"])
    rec = records[0]
    assert rec["road_id"] == "0001-0010"
    assert rec["route_number"] == "0001"
    assert rec["road_name"] == "CITY AV"
    assert rec["road_class"] == "1"
    assert rec["surface_type"] == "62"
    assert rec["municipality"] is None
    assert rec["speed_limit"] is None
    assert "ST_RT_NO" not in rec
    assert "STREET_NAME" not in rec


def test_parse_penndot_roads_skips_missing_key():
    features = [{"attributes": {"STREET_NAME": "MAIN ST"}}]
    records = parse_penndot_roads_features(features)
    assert len(records) == 0


def test_parse_penndot_roads_composite_key():
    features = [
        {
            "attributes": {
                "ST_RT_NO": "0030",
                "SEG_NO": "0220",
                "STREET_NAME": "MARKET ST",
            }
        }
    ]
    records = parse_penndot_roads_features(features)
    assert records[0]["road_id"] == "0030-0220"
