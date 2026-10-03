"""Complete direct acquisitions must be validated before source replacement."""

from unittest.mock import Mock

import pytest
from countyiq.lib import arcgis_snapshot

URL = "https://gis.example/MapServer/0"
METADATA = {"fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}]}


def features(*identifiers):
    return [{"attributes": {"OBJECTID": identifier}} for identifier in identifiers]


def mock_source(monkeypatch, *, metadata=None, rows=None, counts=(2, 2)):
    responses = [METADATA if metadata is None else metadata]
    responses.extend({"count": count} for count in counts)
    request = Mock(
        side_effect=[Mock(json=Mock(return_value=value)) for value in responses]
    )
    query = Mock(return_value=features(1, 2) if rows is None else rows)
    monkeypatch.setattr(arcgis_snapshot.requests, "get", request)
    monkeypatch.setattr(arcgis_snapshot, "query_all_features", query)
    return request, query


def test_direct_snapshot_preserves_filters_and_validates_counts(monkeypatch):
    request, query = mock_source(monkeypatch)
    spatial_filter = {
        "geometry": "-77,39,-76,40",
        "geometryType": "esriGeometryEnvelope",
    }

    assert arcgis_snapshot.fetch_arcgis_snapshot(
        URL, where="CTY_CODE='67'", spatial_filter=spatial_filter
    ) == features(1, 2)

    assert request.call_args_list[0].args == (URL,)
    for call in request.call_args_list[1:]:
        assert call.args == (f"{URL}/query",)
        assert call.kwargs["params"] == {
            **spatial_filter,
            "where": "CTY_CODE='67'",
            "f": "json",
            "returnCountOnly": "true",
        }
    query.assert_called_once_with(
        URL,
        where="CTY_CODE='67'",
        out_fields="*",
        out_sr=4326,
        batch_size=1000,
        extra_params=spatial_filter,
    )


@pytest.mark.parametrize("counts", [(3, 3), (2, 3)])
def test_incomplete_or_changing_source_count_is_rejected(monkeypatch, counts):
    mock_source(monkeypatch, counts=counts)
    with pytest.raises(ValueError):
        arcgis_snapshot.fetch_arcgis_snapshot(URL)


@pytest.mark.parametrize("count", [None, -1, True, "2"])
def test_invalid_count_stops_before_feature_query(monkeypatch, count):
    _, query = mock_source(monkeypatch, counts=(count,))
    with pytest.raises(ValueError, match="invalid source count"):
        arcgis_snapshot.fetch_arcgis_snapshot(URL)
    query.assert_not_called()


def test_duplicate_object_ids_cannot_hide_missing_features(monkeypatch):
    mock_source(monkeypatch, rows=features(1, 1))
    with pytest.raises(ValueError, match="duplicate object IDs"):
        arcgis_snapshot.fetch_arcgis_snapshot(URL)


@pytest.mark.parametrize("identifier", [None, "1", True])
def test_object_ids_must_be_numeric(monkeypatch, identifier):
    mock_source(monkeypatch, rows=features(identifier, 2))
    with pytest.raises(ValueError, match="numeric object ID"):
        arcgis_snapshot.fetch_arcgis_snapshot(URL)


@pytest.mark.parametrize("metadata", [{}, [], {"error": {}}, {"fields": [None]}])
def test_invalid_metadata_stops_before_feature_query(monkeypatch, metadata):
    _, query = mock_source(monkeypatch, metadata=metadata)
    with pytest.raises(ValueError, match="invalid layer"):
        arcgis_snapshot.fetch_arcgis_snapshot(URL)
    query.assert_not_called()


def test_declared_object_id_field_is_supported(monkeypatch):
    metadata = {"objectIdField": "ID", "fields": [{"name": "ID"}]}
    rows = [{"attributes": {"ID": 1}}, {"attributes": {"ID": 2}}]
    mock_source(monkeypatch, metadata=metadata, rows=rows)
    assert arcgis_snapshot.fetch_arcgis_snapshot(URL) == rows


def test_missing_object_id_metadata_is_rejected(monkeypatch):
    mock_source(monkeypatch, metadata={"fields": [{"name": "OBJECTID"}]})
    with pytest.raises(ValueError, match="identify its object ID"):
        arcgis_snapshot.fetch_arcgis_snapshot(URL)
