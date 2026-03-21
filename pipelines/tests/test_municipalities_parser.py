"""Tests for municipalities parser."""

import json
import pathlib

from countyiq.lib.parsers.municipalities import parse_municipalities_features

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "municipalities_sample.json"


def test_parse_municipalities_returns_records():
    raw = json.loads(FIXTURE.read_text())
    records = parse_municipalities_features(raw["features"])
    assert len(records) > 0


def test_parse_municipalities_field_mapping():
    raw = json.loads(FIXTURE.read_text())
    records = parse_municipalities_features(raw["features"])
    rec = records[0]
    assert "name" in rec
    assert "muni_type" in rec
    assert "county" in rec
    assert "MUNI_NAME" not in rec


def test_parse_municipalities_skips_missing_name():
    features = [{"attributes": {"TYPE": "Borough"}}]
    records = parse_municipalities_features(features)
    assert len(records) == 0


def test_parse_municipalities_null_type():
    features = [{"attributes": {"MUNI_NAME": "York", "TYPE": None}}]
    records = parse_municipalities_features(features)
    assert records[0]["muni_type"] is None
