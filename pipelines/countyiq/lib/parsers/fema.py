"""Parse FEMA NFHL GeoJSON features into staging.flood_zones records."""

FEMA_SENTINEL = -9999

# GeoJSON property → staging column name
COLUMN_MAP = {
    "DFIRM_ID": "dfirm_id",
    "FLD_AR_ID": "fld_ar_id",
    "FLD_ZONE": "fld_zone",
    "ZONE_SUBTY": "zone_subty",
    "SFHA_TF": "sfha_tf",
    "STATIC_BFE": "static_bfe",
    "V_DATUM": "v_datum",
    "DEPTH": "depth",
    "STUDY_TYP": "study_typ",
    "SOURCE_CIT": "source_cit",
}

# Numeric fields that use -9999 as "no data" sentinel
SENTINEL_FIELDS = {"STATIC_BFE", "DEPTH"}


def parse_fema_geojson(geojson: dict) -> list[dict]:
    """Parse a FEMA NFHL GeoJSON FeatureCollection into staging records.

    Args:
        geojson: Parsed GeoJSON dict (FeatureCollection from FEMA MapServer).

    Returns:
        List of dicts with staging column names + "geojson" key containing
        the raw geometry dict for PostGIS insertion via ST_GeomFromGeoJSON.
    """
    records = []
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})

        # FLD_AR_ID is the primary key — skip if missing
        if not props.get("FLD_AR_ID"):
            continue

        record = {}
        for src_col, db_col in COLUMN_MAP.items():
            val = props.get(src_col)
            # Convert sentinel values to None
            if src_col in SENTINEL_FIELDS and val == FEMA_SENTINEL:
                val = None
            # Convert empty strings to None
            if isinstance(val, str) and not val.strip():
                val = None
            record[db_col] = val

        # Attach raw geometry for PostGIS insertion
        geom = feature.get("geometry")
        if geom:
            record["geojson"] = geom

        records.append(record)

    return records
