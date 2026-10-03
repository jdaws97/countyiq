"""Fetch complete ArcGIS layers before replacing a source snapshot in staging."""

import requests

from countyiq.lib.arcgis_client import query_all_features

REQUEST_TIMEOUT = 60


def fetch_metadata(url: str) -> dict:
    """Read live layer metadata after the caller authorizes source access."""
    response = requests.get(url, params={"f": "json"}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    metadata = response.json()
    if not isinstance(metadata, dict) or "error" in metadata:
        raise ValueError("ArcGIS returned invalid layer metadata")
    fields = metadata.get("fields")
    if (
        not isinstance(fields, list)
        or not fields
        or any(not isinstance(field, dict) or not field.get("name") for field in fields)
    ):
        raise ValueError("ArcGIS returned invalid layer fields")
    return metadata


def _validate_features(features: list[dict], metadata: dict, count: int) -> None:
    if not isinstance(features, list) or count != len(features):
        raise ValueError("ArcGIS source count disagrees with its complete feature list")
    oid_field = metadata.get("objectIdField") or next(
        (
            field["name"]
            for field in metadata["fields"]
            if field.get("type") == "esriFieldTypeOID"
        ),
        None,
    )
    if not oid_field:
        raise ValueError("ArcGIS metadata must identify its object ID field")

    identifiers = set()
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(
            feature.get("attributes"), dict
        ):
            raise TypeError("ArcGIS feature is missing its attributes")
        identifier = feature["attributes"].get(oid_field)
        if type(identifier) is not int:
            raise ValueError("ArcGIS feature is missing a numeric object ID")
        if identifier in identifiers:
            raise ValueError("ArcGIS snapshot contains duplicate object IDs")
        identifiers.add(identifier)


def fetch_arcgis_snapshot(
    url: str,
    *,
    where: str = "1=1",
    spatial_filter: dict[str, object] | None = None,
) -> list[dict]:
    """Require stable source counts and unique IDs across the complete acquisition."""
    metadata = fetch_metadata(url)
    spatial_filter = spatial_filter or {}
    count_params = {
        **spatial_filter,
        "where": where,
        "f": "json",
        "returnCountOnly": "true",
    }

    def fetch_count() -> int:
        response = requests.get(
            f"{url}/query", params=count_params, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        result = response.json()
        if (
            not isinstance(result, dict)
            or "error" in result
            or type(result.get("count")) is not int
            or result["count"] < 0
        ):
            raise ValueError("ArcGIS returned an invalid source count")
        return result["count"]

    before = fetch_count()
    features = query_all_features(
        url,
        where=where,
        out_fields="*",
        out_sr=4326,
        batch_size=1000,
        extra_params=spatial_filter,
    )
    after = fetch_count()
    if before != after:
        raise ValueError("ArcGIS count changed during acquisition; retry the snapshot")
    _validate_features(features, metadata, after)
    return features
