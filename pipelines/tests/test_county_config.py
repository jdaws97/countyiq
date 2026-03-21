from countyiq.lib.county_config import CountyConfig, get_county_config, COUNTY_CONFIGS


def test_york_config_exists():
    config = get_county_config("york")
    assert config.name == "York County"
    assert config.plcb_filter == "York County"
    assert config.plcb_min_records == 500
    assert "arcweb1.ycpc.org" in config.arcgis_parcels_url


def test_default_county_is_york():
    config = get_county_config()
    assert config.name == "York County"


def test_unknown_county_raises():
    import pytest
    with pytest.raises(KeyError):
        get_county_config("nonexistent")


def test_all_configs_have_required_fields():
    for key, config in COUNTY_CONFIGS.items():
        assert config.name, f"{key} missing name"
        assert config.plcb_filter, f"{key} missing plcb_filter"
        assert config.arcgis_parcels_url, f"{key} missing arcgis_parcels_url"
