from countyiq.assets.arcgis.environmental_diligence import (
    parse_cleanup_sites,
    parse_storage_tanks,
)


def test_storage_tank_parser_keeps_public_diligence_fields():
    rows = parse_storage_tanks(
        [
            {
                "attributes": {
                    "OBJECTID": 7,
                    "FACILITY_NAME": "Example Fuel",
                    "FACILITY_ADDRESS1": "1 Main St",
                    "FACILITY_COUNTY": "York",
                    "FACILITY_MUNICIPALITY": "York City",
                    "TANK_INFORMATION": "https://example.gov/tanks/7",
                },
                "geometry": {"x": -76.7, "y": 39.96},
            }
        ],
        "https://example.gov/FeatureServer/171",
    )

    assert rows[0]["source_layer"] == "active_storage_tank"
    assert rows[0]["site_name"] == "Example Fuel"
    assert rows[0]["_geom"] is not None


def test_cleanup_parser_labels_record_as_screening_source():
    rows = parse_cleanup_sites(
        [
            {
                "attributes": {
                    "SHAPE_FID": 9,
                    "SITE_NAME": "Former Works",
                    "SUB_FACILITY_TYPE": "SOIL MEDIA",
                    "SUB_FACILITY_STATUS": "ACTIVE",
                },
                "geometry": {"x": -76.71, "y": 39.97},
            }
        ],
        "https://example.gov/MapServer/5",
    )

    assert rows[0]["source_layer"] == "land_recycling_cleanup"
    assert rows[0]["facility_type"] == "SOIL MEDIA"
    assert rows[0]["source_url"].endswith("/5")
