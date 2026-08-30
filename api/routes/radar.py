"""Development Radar — momentum (where IS activity) and opportunity (where SHOULD it happen next)."""

from typing import cast

from fastapi import APIRouter, Query

from api.lib.database import get_cursor
from api.lib.development_radar import (
    build_reason_signals,
    compute_headline_signal,
    sanitize_signals_for_public,
)
from api.lib.response_types import (
    RadarBboxItem,
    RadarBboxResponse,
    RadarMunicipalitiesResponse,
    RadarParcelListResponse,
    RadarParcelPayload,
)
from api.lib.serialization import serialize_temporal_fields
from api.lib.settings import open_data_source_key
from api.lib.source_policy import require_source_use, source_use_allowed

router = APIRouter(tags=["radar"])

READINESS_SIGNAL_KEYS = {
    "economic_development_park",
    "development_overlay",
    "local_traffic_activity",
    "growth_area",
    "penndot_project",
    "vacancy",
    "soil_constraint",
    "zoning_constraint",
    "flood_zone",
    "environmental_diligence",
}


def _require_radar_sources(cur, *, include_tax_claims: bool = True) -> None:
    source_keys = [
        open_data_source_key(),
        "penndot_open_data",
        "fema_nfhl",
    ]
    if include_tax_claims:
        source_keys.append("tax_claims")
    for source_key in source_keys:
        require_source_use(cur, source_key, "derived_product", conceal=False)


def _serialize_radar_row(
    row: dict,
    reason_scope: set[str] | None = None,
    *,
    allow_people: bool = False,
) -> RadarParcelPayload:
    d = dict(row)
    for key in ("acres", "aprtotal"):
        if d.get(key) is not None:
            try:
                d[key] = float(d[key])
            except (TypeError, ValueError):
                pass

    presentation_signals = sanitize_signals_for_public(
        d.get("signals"),
        allow_people=allow_people,
    )
    if reason_scope is not None and isinstance(presentation_signals, dict):
        presentation_signals = {
            key: value
            for key, value in presentation_signals.items()
            if key in reason_scope
        }
        d["signal_count"] = len(presentation_signals)
    d["signals"] = presentation_signals
    d["reason_signals"] = build_reason_signals(presentation_signals)
    d["top_signal"] = compute_headline_signal(
        presentation_signals,
        fallback=None if reason_scope is not None else d.get("top_signal"),
    )
    serialize_temporal_fields(d, "computed_at")
    return cast(RadarParcelPayload, d)


@router.get("/municipalities")
def radar_municipalities(
    view: str = Query(default="opportunity", pattern="^(opportunity|momentum|readiness)$"),
    min_score: int | None = Query(default=None, ge=0, le=100),
) -> RadarMunicipalitiesResponse:
    """Distinct municipalities available for the current radar cohort."""
    defaults = {"opportunity": 30, "momentum": 50, "readiness": 40}
    threshold = min_score if min_score is not None else defaults[view]

    with get_cursor() as cur:
        _require_radar_sources(cur, include_tax_claims=view != "readiness")
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
        elif view == "momentum":
            cur.execute("""
                SELECT DISTINCT p.municipality
                FROM public.development_momentum dm
                JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
                WHERE dm.eligible = TRUE
                  AND dm.score >= %(min_score)s
                  AND p.municipality IS NOT NULL
                ORDER BY p.municipality
            """, {"min_score": threshold})
        else:
            cur.execute("""
                SELECT DISTINCT p.municipality
                FROM public.development_momentum dm
                JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
                WHERE dm.eligible = TRUE
                  AND dm.site_readiness_score >= %(min_score)s
                  AND p.municipality IS NOT NULL
                ORDER BY p.municipality
            """, {"min_score": threshold})
        rows = cur.fetchall()

    return {"municipalities": [r["municipality"] for r in rows]}


@router.get("/development")
def development_scores(
    min_score: int = Query(default=50, ge=0, le=100),
    municipality: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RadarParcelListResponse:
    """Ranked parcels by development momentum score."""
    params: dict = {"min_score": min_score, "limit": limit, "offset": offset}

    extra_where = ""
    if municipality:
        extra_where += " AND p.municipality ILIKE %(municipality)s"
        params["municipality"] = municipality

    with get_cursor() as cur:
        _require_radar_sources(cur)
        params["show_owner"] = source_use_allowed(
            cur, open_data_source_key(), "person_level_display"
        )
        cur.execute(f"""
            SELECT dm.pidn, dm.score, dm.site_readiness_score,
                   dm.top_signal, dm.signal_count,
                   dm.signals, dm.eligible, dm.score_version, dm.computed_at,
                   CASE WHEN %(show_owner)s THEN p.owner_full ELSE NULL END AS owner_full,
                   p.propadr, p.municipality, p.acres,
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

    return {
        "count": len(rows),
        "parcels": [
            _serialize_radar_row(r, allow_people=bool(params["show_owner"]))
            for r in rows
        ],
    }


@router.get("/development/bbox", response_model=None)
def development_bbox(
    west: float = Query(..., ge=-180, le=180),
    south: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180),
    north: float = Query(..., ge=-90, le=90),
    min_score: int = Query(default=0, ge=0, le=100),
) -> RadarBboxResponse:
    """Map layer for parcel coloring by development momentum score."""
    with get_cursor() as cur:
        _require_radar_sources(cur)
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
    limit: int = Query(default=50, ge=1, le=200),
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
        _require_radar_sources(cur)
        params["show_owner"] = source_use_allowed(
            cur, open_data_source_key(), "person_level_display"
        )
        cur.execute(f"""
            SELECT dm.pidn, dm.opportunity_score AS score,
                   dm.site_readiness_score, dm.top_signal,
                   dm.signal_count, dm.signals, dm.eligible, dm.has_active_plan,
                   dm.score_version, dm.computed_at,
                   CASE WHEN %(show_owner)s THEN p.owner_full ELSE NULL END AS owner_full,
                   p.propadr, p.municipality, p.acres,
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

    return {
        "count": len(rows),
        "parcels": [
            _serialize_radar_row(r, allow_people=bool(params["show_owner"]))
            for r in rows
        ],
    }


@router.get("/site-readiness")
def site_readiness_scores(
    min_score: int = Query(default=40, ge=0, le=100),
    municipality: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RadarParcelListResponse:
    """Parcels ranked by physical and policy readiness for development."""
    params: dict = {"min_score": min_score, "limit": limit, "offset": offset}
    extra_where = ""
    if municipality:
        extra_where = " AND p.municipality ILIKE %(municipality)s"
        params["municipality"] = municipality

    with get_cursor() as cur:
        _require_radar_sources(cur, include_tax_claims=False)
        params["show_owner"] = source_use_allowed(
            cur, open_data_source_key(), "person_level_display"
        )
        cur.execute(f"""
            SELECT dm.pidn, dm.site_readiness_score AS score,
                   dm.site_readiness_score, dm.top_signal,
                   dm.signal_count, dm.signals, dm.eligible,
                   dm.has_active_plan, dm.score_version, dm.computed_at,
                   CASE WHEN %(show_owner)s THEN p.owner_full ELSE NULL END AS owner_full,
                   p.propadr, p.municipality, p.acres,
                   p.aprtotal, p.class
            FROM public.development_momentum dm
            JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
            WHERE dm.eligible = TRUE
              AND dm.site_readiness_score >= %(min_score)s
              {extra_where}
            ORDER BY dm.site_readiness_score DESC, dm.signal_count DESC
            LIMIT %(limit)s OFFSET %(offset)s
        """, params)
        rows = cur.fetchall()
        cur.execute(
            """
            SELECT
                EXISTS (SELECT 1 FROM staging.zoning_overlays WHERE valid_to IS NULL) AS zoning_overlays,
                EXISTS (SELECT 1 FROM staging.economic_development_parks WHERE valid_to IS NULL) AS economic_parks,
                EXISTS (SELECT 1 FROM staging.soils WHERE valid_to IS NULL) AS soils,
                EXISTS (SELECT 1 FROM staging.local_traffic_counts WHERE valid_to IS NULL) AS local_traffic,
                EXISTS (SELECT 1 FROM staging.penndot_projects WHERE valid_to IS NULL) AS penndot_projects,
                EXISTS (SELECT 1 FROM staging.flood_zones WHERE valid_to IS NULL) AS fema_flood,
                EXISTS (SELECT 1 FROM staging.environmental_diligence_sites WHERE valid_to IS NULL) AS pa_dep_diligence
            """
        )
        coverage_row = dict(cur.fetchone())

    loaded_layers = [key for key, loaded in coverage_row.items() if loaded]

    return {
        "count": len(rows),
        "parcels": [
            _serialize_radar_row(
                r,
                READINESS_SIGNAL_KEYS,
                allow_people=bool(params["show_owner"]),
            )
            for r in rows
        ],
        "coverage": {
            "loaded_count": len(loaded_layers),
            "total_count": len(coverage_row),
            "loaded_layers": loaded_layers,
            "missing_layers": [key for key, loaded in coverage_row.items() if not loaded],
        },
    }
