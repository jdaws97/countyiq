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
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-76.38, 39.73],
                            [-76.37, 39.73],
                            [-76.37, 39.74],
                            [-76.38, 39.74],
                            [-76.38, 39.73],
                        ]
                    ],
                },
                "properties": {"FLD_ZONE": "AE", "SFHA_TF": "T"},
            }
        ],
    }
    records = parse_fema_geojson(geojson)
    assert records == []


def test_sentinel_value():
    assert FEMA_SENTINEL == -9999


def test_parse_arcgis_json_format():
    """Parser handles ArcGIS JSON (f=json) with attributes/rings format."""
    data = {
        "features": [
            {
                "attributes": {
                    "DFIRM_ID": "42133C",
                    "FLD_AR_ID": "42133C_7777",
                    "FLD_ZONE": "AE",
                    "ZONE_SUBTY": None,
                    "SFHA_TF": "T",
                    "STATIC_BFE": 300.0,
                    "V_DATUM": "NAVD88",
                    "DEPTH": -9999,
                    "STUDY_TYP": "SFHAs WITH HIGH FLOOD RISK",
                    "SOURCE_CIT": "42133C_STUDY1",
                },
                "geometry": {
                    "rings": [
                        [
                            [-76.38, 39.73],
                            [-76.37, 39.73],
                            [-76.37, 39.74],
                            [-76.38, 39.74],
                            [-76.38, 39.73],
                        ]
                    ]
                },
            }
        ]
    }
    records = parse_fema_geojson(data)
    assert len(records) == 1
    r = records[0]
    assert r["fld_ar_id"] == "42133C_7777"
    assert r["fld_zone"] == "AE"
    assert r["static_bfe"] == 300.0
    assert r["depth"] is None  # sentinel converted
    assert r["geojson"]["type"] == "MultiPolygon"
    assert r["geojson"]["coordinates"] == [
        [
            [
                [-76.38, 39.73],
                [-76.37, 39.73],
                [-76.37, 39.74],
                [-76.38, 39.74],
                [-76.38, 39.73],
            ]
        ]
    ]


def test_arcgis_preserves_separate_islands_and_interior_holes():
    first_exterior = [[0, 0], [0, 4], [4, 4], [4, 0], [0, 0]]
    interior_hole = [[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]]
    second_exterior = [[6, 0], [6, 4], [10, 4], [10, 0], [6, 0]]
    data = {
        "features": [
            {
                "attributes": {"FLD_AR_ID": "42133C_multipart"},
                "geometry": {"rings": [first_exterior, interior_hole, second_exterior]},
            }
        ]
    }

    record = parse_fema_geojson(data)[0]

    assert record["geojson"] == {
        "type": "MultiPolygon",
        "coordinates": [[first_exterior, interior_hole], [second_exterior]],
    }


def test_parse_arcgis_json_no_geometry():
    """ArcGIS JSON feature without geometry is parsed without geojson key."""
    data = {
        "features": [
            {
                "attributes": {
                    "DFIRM_ID": "42133C",
                    "FLD_AR_ID": "42133C_8888",
                    "FLD_ZONE": "X",
                    "SFHA_TF": "F",
                    "STATIC_BFE": -9999,
                    "DEPTH": -9999,
                },
            }
        ]
    }
    records = parse_fema_geojson(data)
    assert len(records) == 1
    assert "geojson" not in records[0]
