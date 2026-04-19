"""Development Radar — momentum (where IS activity) and opportunity (where SHOULD it happen next)."""

from typing import cast

from fastapi import APIRouter, Query

from api.lib.database import get_cursor
from api.lib.development_radar import build_reason_signals, compute_headline_signal
from api.lib.response_types import (
    RadarBboxItem,
    RadarBboxResponse,
    RadarMunicipalitiesResponse,
    RadarParcelListResponse,
    RadarParcelPayload,
)

router = APIRouter(tags=["radar"])


def _serialize_radar_row(row: dict) -> RadarParcelPayload:
    d = dict(row)
    for key in ("acres", "aprtotal"):
        if d.get(key) is not None:
            try:
                d[key] = float(d[key])
            except (TypeError, ValueError):
                pass

    d["reason_signals"] = build_reason_signals(d.get("signals"))
    d["top_signal"] = compute_headline_signal(d.get("signals"), fallback=d.get("top_signal"))
    return cast(RadarParcelPayload, d)


@router.get("/municipalities")
def radar_municipalities(
    view: str = Query(default="opportunity", pattern="^(opportunity|momentum)$"),
    min_score: int | None = Query(default=None, ge=0, le=100),
) -> RadarMunicipalitiesResponse:
    """Distinct municipalities available for the current radar cohort."""
    threshold = min_score if min_score is not None else (30 if view == "opportunity" else 50)

    with get_cursor() as cur:
        if view == "opportunity":
            cur.execute("""
                SELECT DISTINCT p.municipality
                FROM public.development_momentum dm
                JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
                WHERE dm.eligible = TRUE
                  AND dm.has_active_plan = FALSE
                  AND dm.opportunity_score >= %(min_score)s
                  AND p.municipality IS NOT NULL
                ORDER BY p.municipality
            """, {"min_score": threshold})
        else:
            cur.execute("""
                SELECT DISTINCT p.municipality
                FROM public.development_momentum dm
                JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
                WHERE dm.eligible = TRUE
                  AND dm.score >= %(min_score)s
                  AND p.municipality IS NOT NULL
                ORDER BY p.municipality
            """, {"min_score": threshold})
        rows = cur.fetchall()

    return {"municipalities": [r["municipality"] for r in rows]}


@router.get("/development")
def development_scores(
    min_score: int = Query(default=50, ge=0, le=100),
    municipality: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> RadarParcelListResponse:
    """Ranked parcels by development momentum score."""
    params: dict = {"min_score": min_score, "limit": limit, "offset": offset}

    extra_where = ""
    if municipality:
        extra_where += " AND p.municipality ILIKE %(municipality)s"
        params["municipality"] = municipality

    with get_cursor() as cur:
        cur.execute(f"""
            SELECT dm.pidn, dm.score, dm.top_signal, dm.signal_count,
                   dm.signals, dm.eligible, dm.score_version, dm.computed_at,
                   p.owner_full, p.propadr, p.municipality, p.acres,
                   p.aprtotal, p.class
            FROM public.development_momentum dm
            JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
            WHERE dm.eligible = TRUE
              AND dm.score >= %(min_score)s
              {extra_where}
            ORDER BY dm.score DESC, dm.signal_count DESC
            LIMIT %(limit)s OFFSET %(offset)s
        """, params)
        rows = cur.fetchall()

    return {"count": len(rows), "parcels": [_serialize_radar_row(r) for r in rows]}


@router.get("/development/bbox", response_model=None)
def development_bbox(
    west: float = Query(...),
    south: float = Query(...),
    east: float = Query(...),
    north: float = Query(...),
    min_score: int = Query(default=0, ge=0, le=100),
) -> RadarBboxResponse:
    """Map layer for parcel coloring by development momentum score."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT dm.pidn, dm.score, dm.eligible, dm.top_signal,
                   ST_X(ST_Centroid(p.geom)) AS lng,
                   ST_Y(ST_Centroid(p.geom)) AS lat
            FROM public.development_momentum dm
            JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
            WHERE dm.score >= %(min_score)s
              AND p.geom && ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)
        """, {"min_score": min_score, "west": west, "south": south, "east": east, "north": north})
        rows = cur.fetchall()

    return {"count": len(rows), "parcels": [cast(RadarBboxItem, dict(r)) for r in rows]}


@router.get("/opportunity")
def opportunity_scores(
    min_score: int = Query(default=30, ge=0, le=100),
    municipality: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> RadarParcelListResponse:
    """Parcels with strong fundamentals but NO active development plan yet.

    These are the 'buy before everyone notices' parcels — high supporting
    signals (growth area, zoning mismatch, infrastructure, ownership change)
    but no subdivision/land-dev plan filed.
    """
    params: dict = {"min_score": min_score, "limit": limit, "offset": offset}

    extra_where = ""
    if municipality:
        extra_where += " AND p.municipality ILIKE %(municipality)s"
        params["municipality"] = municipality

    with get_cursor() as cur:
        cur.execute(f"""
            SELECT dm.pidn, dm.opportunity_score AS score, dm.top_signal,
                   dm.signal_count, dm.signals, dm.eligible, dm.has_active_plan,
                   dm.score_version, dm.computed_at,
                   p.owner_full, p.propadr, p.municipality, p.acres,
                   p.aprtotal, p.class
            FROM public.development_momentum dm
            JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
            WHERE dm.eligible = TRUE
              AND dm.has_active_plan = FALSE
              AND dm.opportunity_score >= %(min_score)s
              {extra_where}
            ORDER BY dm.opportunity_score DESC, dm.signal_count DESC
            LIMIT %(limit)s OFFSET %(offset)s
        """, params)
        rows = cur.fetchall()

    return {"count": len(rows), "parcels": [_serialize_radar_row(r) for r in rows]}
