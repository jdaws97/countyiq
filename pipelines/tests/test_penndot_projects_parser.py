"""Tests for PennDOT projects parser."""

import json
import pathlib

from countyiq.lib.parsers.penndot_projects import (
    parse_penndot_projects_features,
    _parse_date,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "penndot_projects_sample.json"


def test_parse_projects_returns_records():
    raw = json.loads(FIXTURE.read_text())
    records = parse_penndot_projects_features(raw["features"])
    assert len(records) == 2  # skips null PROJ_ID + deduplicates


def test_parse_projects_field_mapping():
    raw = json.loads(FIXTURE.read_text())
    records = parse_penndot_projects_features(raw["features"])
    rec = records[0]
    assert rec["project_id"] == "98765"
    assert rec["project_name"] == "Forrest Ave Resurface"
    assert rec["description"] == "Resurface"
    assert rec["status"] == "Underway"
    assert rec["project_type"] == "Highway"
    assert rec["cost"] == 3080000.0
    assert rec["municipality"] == "YORK CITY"
    assert rec["county"] == "YORK"
    assert "PROJ_ID" not in rec
    assert "PROJECT_TITLE" not in rec


def test_parse_projects_date_parsing():
    raw = json.loads(FIXTURE.read_text())
    records = parse_penndot_projects_features(raw["features"])
    rec = records[0]
    assert rec["start_date"] is not None
    assert rec["start_date"].year == 2025
    assert rec["start_date"].month == 3
    assert rec["start_date"].day == 17
    assert rec["end_date"] is not None
    assert rec["end_date"].year == 2025


def test_parse_projects_empty_date():
    raw = json.loads(FIXTURE.read_text())
    records = parse_penndot_projects_features(raw["features"])
    rec = records[1]  # Wago Road Bridge — empty COMPLETION_DATE
    assert rec["end_date"] is None


def test_parse_projects_skips_null_id():
    features = [{"attributes": {"PROJECT_TITLE": "Test", "PROJ_ID": None}}]
    records = parse_penndot_projects_features(features)
    assert len(records) == 0


def test_parse_projects_deduplicates():
    features = [
        {"attributes": {"PROJ_ID": 123, "PROJECT_TITLE": "A"}},
        {"attributes": {"PROJ_ID": 123, "PROJECT_TITLE": "A"}},
    ]
    records = parse_penndot_projects_features(features)
    assert len(records) == 1


def test_parse_projects_overflow_data():
    raw = json.loads(FIXTURE.read_text())
    records = parse_penndot_projects_features(raw["features"])
    rec = records[0]
    assert rec["data"] is not None
    assert "PROJ_MANAGER" in rec["data"]
    assert rec["data"]["PROJ_MANAGER"] == "John Smith"
    # Mapped fields should NOT be in data
    assert "PROJECT_TITLE" not in rec["data"]
    assert "PROJ_ID" not in rec["data"]


def test_under_construction_ids_and_geometry_survive_without_relabeling_contract_amount():
    from countyiq.assets.arcgis.penndot_projects import _build_geom_lookup

    features = [
        {
            "attributes": {
                "PROJECT_ID": 456,
                "PROJECT_CLASS": "Highway",
                "PROJECT_TITLE": "Construction project",
                "PROJ_STATUS_DESC": "Construction",
                "COUNTY_NAME": "YORK",
                "CRNT_CNTRCT_AM": 9000000,
            },
            "geometry": {"x": -76.7, "y": 39.9},
        }
    ]
    record = parse_penndot_projects_features(features)[0]
    assert record["project_id"] == "456"
    assert record["project_type"] == "Highway"
    assert record["cost"] is None
    assert record["data"]["CRNT_CNTRCT_AM"] == 9000000
    assert "456" in _build_geom_lookup(features)


def test_parse_date_formats():
    assert _parse_date("03/17/2025").month == 3
    assert _parse_date("20250317").month == 3
    assert _parse_date("") is None
    assert _parse_date(None) is None
