"""Operational health endpoint."""

from fastapi import APIRouter

from api.lib.database import get_cursor

router = APIRouter(tags=["ops"])


@router.get("/health")
def health() -> dict:
    """System health — source record counts and database connectivity."""
    sources = {}
    with get_cursor() as cur:
        tables = {
            "parcels": "staging.parcels",
            "municipalities": "staging.municipalities",
            "address_points": "staging.address_points",
            "structures": "staging.structures",
            "roads": "staging.roads",
            "zoning": "staging.zoning",
            "flood_zones": "staging.flood_zones",
            "plcb_licenses": "staging.plcb_licenses",
            "pa_open_data": "staging.pa_open_data",
            "penndot_roads": "staging.penndot_roads",
            "penndot_projects": "staging.penndot_projects",
            "tax_claims": "staging.tax_claims",
            "sheriff_sales": "staging.sheriff_sales",
            "traffic_counts": "staging.traffic_counts",
            "zipcodes": "staging.zipcodes",
        }
        for name, table in tables.items():
            try:
                cur.execute(f"SELECT COUNT(*) AS cnt FROM {table} WHERE valid_to IS NULL")
                row = cur.fetchone()
                count = row["cnt"]
                sources[name] = {
                    "status": "green" if count > 0 else "red",
                    "record_count": count,
                }
            except Exception:
                sources[name] = {"status": "red", "record_count": 0}

    green = sum(1 for s in sources.values() if s["status"] == "green")
    total = len(sources)

    return {
        "overall": "green" if green == total else "yellow" if green > total // 2 else "red",
        "sources": sources,
        "summary": f"{green}/{total} sources active",
    }
