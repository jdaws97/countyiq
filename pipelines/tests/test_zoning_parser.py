"""Tests for zoning parser."""

import json
import pathlib

from countyiq.lib.parsers.zoning import parse_zoning_features

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "zoning_sample.json"


def test_parse_zoning_returns_records():
    raw = json.loads(FIXTURE.read_text())
    records = parse_zoning_features(raw["features"])
    assert len(records) > 0


def test_parse_zoning_field_mapping():
    raw = json.loads(FIXTURE.read_text())
    records = parse_zoning_features(raw["features"])
    rec = records[0]
    assert "zrecid" in rec
    assert "muni_name" in rec
    assert "zcode" in rec
    assert "zname" in rec
    assert "ztype" in rec
    assert "gen_zcode" in rec
    # Should not contain raw ArcGIS field names
    assert "ZRECID" not in rec
    assert "MUNI_NAME" not in rec


def test_parse_zoning_skips_missing_key():
    features = [{"attributes": {"ZCODE": "R1"}}]
    records = parse_zoning_features(features)
    assert len(records) == 0


def test_parse_zoning_empty_string_to_none():
    features = [{"attributes": {"ZRECID": 1, "ZCODE": ""}}]
    records = parse_zoning_features(features)
    assert records[0]["zcode"] is None
