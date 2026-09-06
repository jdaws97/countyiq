import pytest

from countyiq.assets.arcgis import site_readiness
from countyiq.assets.arcgis.site_readiness import (
    parse_economic_parks,
    parse_local_traffic_counts,
    parse_soils,
    parse_zoning_overlays,
)


def test_prewrite_guard_rejects_truncated_source_before_archive(monkeypatch):
    class _Log:
        def info(self, *_args):
            pass

    class _Context:
        log = _Log()

    class _Archive:
        called = False

        def archive(self, *_args):
            self.called = True

    archive = _Archive()
    monkeypatch.setattr(
        site_readiness, "query_all_features", lambda **_kwargs: [{}, {}]
    )

    with pytest.raises(RuntimeError, match="Refusing to alter staging data"):
        site_readiness._fetch_archive(
            _Context(),
            archive,
            url="https://example.test/layer",
            archive_path="test/layer",
            minimum_records=3,
        )

    assert archive.called is False


def test_parse_zoning_overlay_maps_governance_fields():
    rows = parse_zoning_overlays(
        [
            {
                "attributes": {
                    "GlobalID": " g-1 ",
                    "OBJECTID": 1,
                    "MUNI_NAME": "York",
                    "ZN_OV_TYPE": "STEEP SLOPES",
                    "ZN_OV_NAME": "Steep Slope Overlay",
                    "DESCRIPTION": "Constraint",
                    "PRJ_NUM": "P-1",
                    "CREATE_DATE": 1_700_000_000_000,
                    "MODIFY_DATE": None,
                }
            }
        ],
        "https://example.test/overlay",
    )
    assert rows[0]["globalid"] == "g-1"
    assert rows[0]["overlay_type"] == "STEEP SLOPES"
    assert rows[0]["source_url"].endswith("overlay")


def test_parse_economic_parks_requires_pidn_and_sets_type():
    rows = parse_economic_parks(
        [
            {"attributes": {"PIDN": " 67001 ", "OBJECTID": 8, "NAME": "Commerce Park"}},
            {"attributes": {"PIDN": None, "OBJECTID": 9}},
        ],
        "https://example.test/parks",
        "business",
    )
    assert rows == [
        {
            "park_type": "business",
            "pidn": "67001",
            "source_objectid": 8,
            "name": "Commerce Park",
            "website_url": None,
            "create_date": None,
            "modify_date": None,
            "source_url": "https://example.test/parks",
        }
    ]


def test_parse_soils_preserves_site_constraint_attributes():
    rows = parse_soils(
        [
            {
                "attributes": {
                    "OBJECTID_1": 44,
                    "MUSYM": "AbC",
                    "MUNAME": "Sample",
                    "MU_KEY": "123",
                    "DRAINAGE": "Poorly drained",
                    "SEPTIC": "Very limited",
                    "REP_SLOPE": 17.5,
                    "HYR_GRP": "D",
                }
            }
        ],
        "https://example.test/soils",
    )
    assert rows[0]["objectid"] == 44
    assert rows[0]["representative_slope"] == 17.5
    assert rows[0]["hydrologic_group"] == "D"


def test_parse_local_traffic_falls_back_to_objectid_key():
    rows = parse_local_traffic_counts(
        [
            {
                "attributes": {
                    "OBJECTID": 12,
                    "GlobalID": None,
                    "COUNTER_ID": "C-12",
                    "COUNT_TYPE": "VOLUME",
                    "PURPOSE": "HPMS",
                    "VOLUME": 9000,
                    "YEAR": 2026,
                }
            }
        ],
        "https://example.test/traffic",
    )
    assert rows[0]["globalid"] == "objectid:12"
    assert rows[0]["count_year"] == 2026
    assert rows[0]["volume"] == 9000
