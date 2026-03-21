"""Parser for ArcGIS BLDG_Footprint FeatureServer response.

Maps ArcGIS field names to staging.structures column names.
"""


def parse_structures_features(raw_features: list[dict]) -> list[dict]:
    """Parse ArcGIS Building Footprint features into staging.structures records.

    Args:
        raw_features: ArcGIS feature dicts with 'attributes' key.

    Returns:
        List of flat dicts with staging.structures column names.
    """
    records = []
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        objectid = attrs.get("OBJECTID")
        if objectid is None:
            continue

        record = {
            "objectid": objectid,
            "index_id": str(attrs["INDEX_"]) if attrs.get("INDEX_") else None,
            "building_type": str(attrs["BUILDING_TYPE"]) if attrs.get("BUILDING_TYPE") else None,
        }
        records.append(record)

    return records
