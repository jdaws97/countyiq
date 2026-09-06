"""Parser for ArcGIS AddressPts FeatureServer response.

Maps ArcGIS field names to staging.address_points column names.
"""

FIELD_MAP = {
    "Site_NGUID": "site_nguid",
    "Add_Number": "add_number",
    "AddNum_Suf": "addnum_suf",
    "St_PreDir": "st_pre_dir",
    "St_PreTyp": "st_pre_typ",
    "StreetName": "street_name",
    "St_PosTyp": "st_pos_typ",
    "St_PosDir": "st_pos_dir",
    "Inc_Muni": "inc_muni",
    "Post_Comm": "post_comm",
    "Post_Code": "post_code",
    "Post_Code4": "post_code4",
    "Building": "building",
    "Floor": "floor",
    "Unit": "unit",
    "Place_Type": "place_type",
    "Long": "long",
    "Lat": "lat",
}

# Fields that should stay as their native type, not stringified
NUMERIC_FIELDS = {"add_number", "long", "lat"}


def parse_address_point_feature(raw_feature: dict) -> dict | None:
    """Parse one ArcGIS Address Point feature into a staging record."""
    attrs = raw_feature.get("attributes", {})
    site_nguid = attrs.get("Site_NGUID")
    if not site_nguid:
        return None

    record = {}
    for src, dest in FIELD_MAP.items():
        val = attrs.get(src)
        if val is None or val == "":
            record[dest] = None
        elif dest in NUMERIC_FIELDS:
            record[dest] = val
        else:
            record[dest] = str(val)
    return record


def parse_address_points_features(raw_features: list[dict]) -> list[dict]:
    """Parse ArcGIS Address Point features into staging.address_points records.

    Args:
        raw_features: ArcGIS feature dicts with 'attributes' key.

    Returns:
        List of flat dicts with staging.address_points column names.
    """
    records = []
    for feat in raw_features:
        record = parse_address_point_feature(feat)
        if record is not None:
            records.append(record)

    return records
