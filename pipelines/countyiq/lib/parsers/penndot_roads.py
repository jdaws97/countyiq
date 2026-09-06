"""Parser for PennDOT roadway segments MapServer response.

Maps ArcGIS field names to staging.penndot_roads column names.
"""

FIELD_MAP = {
    "ST_RT_NO": "route_number",
    "STREET_NAME": "road_name",
    "FAC_TYPE": "road_class",
    "SURF_TYPE": "surface_type",
}

# Extra fields stored in the record but not in FIELD_MAP
# (used for composite key generation)
KEY_FIELDS = {"ST_RT_NO", "SEG_NO"}


def parse_penndot_roads_features(raw_features: list[dict]) -> list[dict]:
    """Parse PennDOT roadway segment features into staging.penndot_roads records.

    Args:
        raw_features: ArcGIS feature dicts with 'attributes' key.

    Returns:
        List of flat dicts with staging.penndot_roads column names.
    """
    records = []
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        st_rt_no = attrs.get("ST_RT_NO")
        seg_no = attrs.get("SEG_NO")
        if not st_rt_no or not seg_no:
            continue

        record = {
            "road_id": f"{st_rt_no}-{seg_no}",
        }
        for src, dest in FIELD_MAP.items():
            val = attrs.get(src)
            if val is None or val == "":
                record[dest] = None
            else:
                record[dest] = str(val)

        # municipality and speed_limit not available from this source
        record["municipality"] = None
        record["speed_limit"] = None

        records.append(record)

    return records
