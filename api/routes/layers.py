"""GeoJSON layer endpoints for map rendering."""

from fastapi import APIRouter, HTTPException

from api.lib.database import get_cursor
from api.lib.response_types import LayerConfig
from api.lib.settings import open_data_source_key
from api.lib.source_policy import require_source_use

router = APIRouter(tags=["layers"])

LAYER_CONFIG: dict[str, LayerConfig] = {
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
        "properties": ["project_id", "project_name", "description", "status",
                        "start_date", "end_date", "cost", "project_type"],
        "extra_sql": (
            "t.data->>'PRJCT_GRPHY_DC' AS location_desc, "
            "t.data->>'UNDER_CONSTRUCTION' AS under_construction, "
            "t.data->>'ACT_89_BREAKDOWN' AS act89_status"
        ),
    },
}

_LAYER_SOURCE = {
    "municipalities": open_data_source_key(),
    "flood_zones": "fema_nfhl",
    "zoning": open_data_source_key(),
    "penndot_projects": "penndot_open_data",
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
    extra = config.get("extra_sql")
    if extra:
        prop_select += ", " + extra

    with get_cursor() as cur:
        require_source_use(
            cur, _LAYER_SOURCE[layer_name], "derived_product", conceal=False
        )
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
