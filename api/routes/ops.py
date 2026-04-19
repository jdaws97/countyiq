"""Operational health endpoint."""

import logging

from fastapi import APIRouter
from psycopg2 import Error as PsycopgError
from psycopg2.errors import UndefinedTable

from api.lib.database import get_cursor
from api.lib.response_types import OpsHealthResponse, SourceStatus

router = APIRouter(tags=["ops"])
logger = logging.getLogger(__name__)


def _get_source_status(cur, source_name: str, table: str) -> SourceStatus:
    try:
        cur.execute(f"SELECT COUNT(*) AS cnt FROM {table} WHERE valid_to IS NULL")
        row = cur.fetchone()
        count = row["cnt"]
        return {
            "status": "green" if count > 0 else "red",
            "record_count": count,
        }
    except UndefinedTable:
        cur.connection.rollback()
        logger.info("Ops health source missing table for %s: %s", source_name, table)
        return {"status": "red", "record_count": 0, "error": "missing_table"}
    except PsycopgError as exc:
        cur.connection.rollback()
        logger.warning("Ops health query failed for %s (%s): %s", source_name, table, exc)
        return {"status": "red", "record_count": 0, "error": "query_failed"}


@router.get("/health")
def health() -> OpsHealthResponse:
    """System health — source record counts and database connectivity."""
    sources: dict[str, SourceStatus] = {}
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
            sources[name] = _get_source_status(cur, name, table)

    green = sum(1 for s in sources.values() if s["status"] == "green")
    total = len(sources)

    return {
        "overall": "green" if green == total else "yellow" if green > total // 2 else "red",
        "sources": sources,
        "summary": f"{green}/{total} sources active",
    }
