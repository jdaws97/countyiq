"""GeoJSON layer endpoints for map rendering."""

from fastapi import APIRouter, HTTPException

from api.lib.database import get_cursor

router = APIRouter(tags=["layers"])

LAYER_CONFIG = {
    "municipalities": {
        "table": "staging.municipalities",
        "properties": ["name", "muni_type", "county"],
    },
    "flood_zones": {
        "table": "staging.flood_zones",
        "properties": ["fld_zone", "zone_subty", "sfha_tf", "fld_ar_id"],
    },
    "zoning": {
        "table": "staging.zoning",
        "properties": ["muni_name", "zcode", "zname", "ztype", "gen_zcode", "gen_zname"],
    },
    "penndot_projects": {
        "table": "staging.penndot_projects",
        "properties": ["project_id", "project_name", "description", "status", "municipality"],
    },
}


@router.get("/{layer_name}")
def get_layer(layer_name: str) -> dict:
    """Return a GeoJSON FeatureCollection for the requested layer."""
    config = LAYER_CONFIG.get(layer_name)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown layer: {layer_name}. Available: {list(LAYER_CONFIG.keys())}",
        )

    table = config["table"]
    props = config["properties"]
    prop_select = ", ".join(f"t.{p}" for p in props)

    with get_cursor() as cur:
        cur.execute(f"""
            SELECT
                ST_AsGeoJSON(t.geom)::json AS geometry,
                {prop_select}
            FROM {table} t
            WHERE t.valid_to IS NULL
              AND t.geom IS NOT NULL
        """)
        rows = cur.fetchall()

    features = []
    for row in rows:
        geom = row.pop("geometry")
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": dict(row),
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }
