"""County Scout falls back to manifest-derived seeds outside York."""

from countyiq.lib.county_config import COUNTY_CONFIGS, CountyConfig
from countyiq.lib.scout.seeds import get_scout_seeds


def test_non_york_scout_seeds_derive_from_county_manifest(monkeypatch):
    monkeypatch.setitem(
        COUNTY_CONFIGS,
        "adams_test",
        CountyConfig(
            name="Adams County",
            state="PA",
            open_data_source_key="adams_open_data",
            plcb_filter="Adams County",
            arcgis_parcels_url="https://gis.example.gov/parcels/FeatureServer/0",
            penndot_projects_url="https://gis.penndot.gov/projects/MapServer",
            municipality_websites=(
                (
                    "Gettysburg Planning Commission",
                    "https://gettysburg.example.gov/minutes",
                    "planning_commission",
                ),
            ),
            s3_prefix="adams",
        ),
    )

    seeds = get_scout_seeds("adams_test")

    assert seeds
    assert {seed.county_key for seed in seeds} == {"adams_test"}
    assert any(seed.name == "Adams County GIS parcel service" for seed in seeds)
    assert any(seed.name == "Gettysburg Planning Commission" for seed in seeds)
    assert all("York" not in seed.name for seed in seeds)
