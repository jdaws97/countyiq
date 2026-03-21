"""Tests for structures parser."""

import json
import pathlib

from countyiq.lib.parsers.structures import parse_structures_features

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "structures_sample.json"


def test_parse_structures_returns_records():
    raw = json.loads(FIXTURE.read_text())
    records = parse_structures_features(raw["features"])
    assert len(records) > 0


def test_parse_structures_field_mapping():
    raw = json.loads(FIXTURE.read_text())
    records = parse_structures_features(raw["features"])
    rec = records[0]
    assert "objectid" in rec
    assert "index_id" in rec
    assert "building_type" in rec
    assert "INDEX_" not in rec
    assert "OBJECTID" not in rec


def test_parse_structures_skips_missing_objectid():
    features = [{"attributes": {"INDEX_": "123", "BUILDING_TYPE": "Main Living Quarters"}}]
    records = parse_structures_features(features)
    assert len(records) == 0


def test_parse_structures_null_building_type():
    features = [{"attributes": {"OBJECTID": 1, "INDEX_": "123", "BUILDING_TYPE": None}}]
    records = parse_structures_features(features)
    assert records[0]["building_type"] is None
