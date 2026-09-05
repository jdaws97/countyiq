import os
from pathlib import Path
import subprocess
import sys

import pytest

from countyiq.lib.county_config import (
    COUNTY_CONFIGS,
    CountyConfig,
    county_open_data_source_key,
    county_prompt_context,
    get_county_config,
    load_county_manifests,
    municipality_name_from_body,
    municipality_source_key,
    municipality_name_from_body,
)


def test_york_config_exists():
    config = get_county_config("york")
    assert config.name == "York County"
    assert config.plcb_filter == "York County"
    assert config.plcb_min_records == 500
    assert "arcweb1.ycpc.org" in config.arcgis_parcels_url
    assert (
        "York Twp Board of Commissioners",
        "https://yorktownshippa.gov/boards-4/boc/",
        "board_of_commissioners",
    ) in config.municipality_websites


def test_hellam_sources_use_document_listing_pages():
    entries = set(get_county_config("york").municipality_websites)

    assert (
        "Hellam Twp Board of Supervisors",
        "https://www.hellamtownship.gov/board-of-supervisors-meetings/",
        "board_of_supervisors",
    ) in entries
    assert (
        "Hellam Twp Planning Commission",
        "https://www.hellamtownship.gov/planning-commission-meetings/",
        "planning_commission",
    ) in entries
    assert (
        "Hellam Twp Zoning Hearing Board",
        "https://www.hellamtownship.gov/zoning-hearing-board-meetings/",
        "zoning_hearing",
    ) in entries


def test_default_county_is_york():
    config = get_county_config()
    assert config.name == "York County"


def test_unknown_county_raises():
    with pytest.raises(KeyError):
        get_county_config("nonexistent")


@pytest.mark.parametrize(
    ("body_name", "expected"),
    [
        ("Hanover Borough Council", "HANOVER BORO"),
        ("York City Council", "YORK CITY"),
        ("Spring Grove Boro Planning Commission", "SPRING GROVE BORO"),
        ("Dover Twp Zoning Hearing Board", "DOVER TWP"),
        ("York County Planning Commission", None),
    ],
)
def test_municipality_body_names_use_boundary_layer_convention(body_name, expected):
    assert municipality_name_from_body(body_name) == expected


def test_municipality_source_key_is_stable():
    assert (
        municipality_source_key("Dover Twp Board of Supervisors")
        == "dover_twp_board_of_supervisors"
    )
    assert (
        municipality_source_key("Washington Twp Planning Commission", "adams")
        == "adams:washington_twp_planning_commission"
    )


def test_york_proceeding_coverage_counts_sources_not_municipalities():
    entries = get_county_config("york").municipality_websites
    municipalities_with_any_source = {
        name
        for body_name, _, _ in entries
        if (name := municipality_name_from_body(body_name)) is not None
    }
    governing_body_municipalities = {
        municipality_name_from_body(body_name)
        for body_name, _, proceeding_type in entries
        if proceeding_type in {
            "board_of_commissioners",
            "board_of_supervisors",
            "borough_council",
            "city_council",
        }
    }

    assert len(entries) == 104
    assert len({url for _, url, _ in entries}) == 102
    assert len(municipalities_with_any_source) == 64
    assert len(governing_body_municipalities) == 62


def test_all_configs_have_required_fields():
    for key, config in COUNTY_CONFIGS.items():
        assert config.name, f"{key} missing name"
        assert config.plcb_filter, f"{key} missing plcb_filter"
        assert config.arcgis_parcels_url, f"{key} missing arcgis_parcels_url"


def test_county_manifest_loads_without_python_registry_edit(tmp_path: Path):
    (tmp_path / "adams.toml").write_text(
        """
name = "Adams County"
state = "PA"
open_data_source_key = "adams_open_data"
plcb_filter = "Adams County"
arcgis_parcels_url = "https://gis.adams.example/Parcels/FeatureServer/0"
s3_prefix = "adams"
penndot_projects_layers = [1, 4]
soda_datasets = [["xvd7-5r2c", "shortcountyname", "Adams", ":id"]]
municipality_websites = [
  ["Gettysburg Planning Commission", "https://gettysburg.example/minutes", "planning_commission"]
]
""".strip(),
        encoding="utf-8",
    )

    loaded = load_county_manifests(tmp_path, existing=COUNTY_CONFIGS)

    assert loaded["adams"].name == "Adams County"
    assert loaded["adams"].penndot_projects_layers == (1, 4)
    assert loaded["adams"].soda_datasets[0][2] == "Adams"
    assert loaded["adams"].municipality_websites[0][0] == "Gettysburg Planning Commission"


def test_county_manifest_rejects_unknown_fields(tmp_path: Path):
    (tmp_path / "bad.toml").write_text(
        """
name = "Bad County"
open_data_source_key = "bad_open_data"
plcb_filter = "Bad County"
arcgis_parcels_url = "https://example.gov/parcels"
s3_prefix = "bad"
invented_source = "nope"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown CountyConfig field"):
        load_county_manifests(tmp_path)


@pytest.mark.parametrize("directory", [None, "", "  "])
def test_optional_manifest_directory_does_not_scan_working_directory(tmp_path: Path, directory):
    # Compose supplies an empty value for this optional setting. An unrelated
    # TOML file in the process directory must not prevent Dagster startup.
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "not-a-county"\n')
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    environment.pop("COUNTYIQ_COUNTY_CONFIG_DIR", None)
    if directory is not None:
        environment["COUNTYIQ_COUNTY_CONFIG_DIR"] = directory
    result = subprocess.run(
        [sys.executable, "-c",
         "from countyiq.lib.county_config import get_county_config; "
         "assert get_county_config('york').name == 'York County'"],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_county_identity_helpers_are_not_york_specific():
    adams = CountyConfig(
        name="Adams County",
        state="PA",
        open_data_source_key="adams_open_data",
        plcb_filter="Adams County",
        arcgis_parcels_url="https://example.gov/parcels",
        s3_prefix="adams",
    )

    assert county_prompt_context(adams) == "Adams County, PA"
    assert county_open_data_source_key(adams) == "adams_open_data"
    assert municipality_name_from_body(
        "Adams County Commissioners", county=adams
    ) is None
    assert municipality_name_from_body(
        "Gettysburg Borough Council", county=adams
    ) == "GETTYSBURG BORO"


def test_york_sources_exclude_verified_other_counties():
    from urllib.parse import urlsplit
    hosts = {urlsplit(url).hostname for _, url, _ in get_county_config("york").municipality_websites}
    assert not hosts.intersection({"penntownship.org", "paradisetownship.org", "windsortownship.com", "jackson-township.org"})
