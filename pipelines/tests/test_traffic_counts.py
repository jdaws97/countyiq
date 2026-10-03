import copy

import pytest
from countyiq.assets.arcgis.traffic_counts import parse_traffic_features


def traffic_feature():
    return {
        "attributes": {
            "OBJECTID": 1,
            "ST_RT_NO": "30",
            "CUR_AADT": 12000,
            "ADTT_CUR": 900,
            "SEG_LNGTH_FEET": 800,
        },
        "geometry": {"paths": [[[-76.8, 39.9], [-76.7, 39.9]]]},
    }


def test_traffic_mapping_keeps_identity_and_source():
    records, geometries = parse_traffic_features(
        [traffic_feature()], "https://example.gov"
    )
    assert records[0]["objectid"] == 1
    assert records[0]["aadt"] == 12000
    assert records[0]["source_url"] == "https://example.gov"
    assert 1 in geometries


@pytest.mark.parametrize("defect", ["geometry", "field", "duplicate"])
def test_unusable_traffic_row_cannot_silently_expire_valid_history(defect):
    feature = traffic_feature()
    features = [feature]
    if defect == "geometry":
        feature["geometry"] = None
    elif defect == "field":
        del feature["attributes"]["CUR_AADT"]
    else:
        features.append(copy.deepcopy(feature))
    with pytest.raises(ValueError):
        parse_traffic_features(features, "https://example.gov")
