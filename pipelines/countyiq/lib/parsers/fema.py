"""Parse FEMA NFHL features into staging.flood_zones records.

Supports both ArcGIS JSON (f=json, used in production — more reliable)
and GeoJSON (f=geojson) formats from the FEMA MapServer.
"""

from countyiq.lib.geometry import rings_to_multipolygon_geojson

FEMA_SENTINEL = -9999

# Feature attribute → staging column name
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


def _rings_to_geojson(geometry: dict) -> dict | None:
    """Preserve separate exterior rings and holes in ArcGIS flood polygons."""
    return rings_to_multipolygon_geojson(geometry.get("rings"))


def _extract_props_and_geom(feature: dict) -> tuple[dict, dict | None]:
    """Extract properties and GeoJSON geometry from either format.

    ArcGIS JSON: {"attributes": {...}, "geometry": {"rings": [...]}}
    GeoJSON:     {"properties": {...}, "geometry": {"type": "Polygon", ...}}
    """
    # ArcGIS JSON format (f=json)
    if "attributes" in feature:
        props = feature.get("attributes", {})
        raw_geom = feature.get("geometry")
        geojson_geom = _rings_to_geojson(raw_geom) if raw_geom else None
        return props, geojson_geom

    # GeoJSON format (f=geojson)
    props = feature.get("properties", {})
    geom = feature.get("geometry")
    return props, geom


def parse_fema_geojson(data: dict) -> list[dict]:
    """Parse FEMA NFHL features into staging records.

    Accepts both ArcGIS JSON and GeoJSON FeatureCollection formats.

    Args:
        data: Parsed JSON dict from FEMA MapServer (either format).

    Returns:
        List of dicts with staging column names + "geojson" key containing
        the geometry dict for PostGIS insertion via ST_GeomFromGeoJSON.
    """
    records = []
    for feature in data.get("features", []):
        props, geojson_geom = _extract_props_and_geom(feature)

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

        # Attach GeoJSON geometry for PostGIS insertion
        if geojson_geom:
            record["geojson"] = geojson_geom

        records.append(record)

    return records
