"""Parser for ArcGIS Municipal_Boundary FeatureServer response.

Maps ArcGIS field names to staging.municipalities column names.
"""


def parse_municipalities_features(raw_features: list[dict]) -> list[dict]:
    """Parse ArcGIS Municipal Boundary features into staging.municipalities records.

    Args:
        raw_features: ArcGIS feature dicts with 'attributes' key.

    Returns:
        List of flat dicts with staging.municipalities column names.
    """
    records = []
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        muni_name = attrs.get("MUNI_NAME")
        if not muni_name:
            continue

        record = {
            "name": str(muni_name),
            "muni_type": str(attrs["TYPE"]) if attrs.get("TYPE") else None,
            "county": "York",
        }
        records.append(record)

    return records
