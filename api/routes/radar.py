"""Development Radar — momentum (where IS activity), opportunity (where SHOULD it happen next), and movers."""

from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Query

from api.lib.database import get_cursor
from api.lib.development_radar import (
    build_reason_signals,
    compact_signals_for_list,
    compute_headline_signal,
    sanitize_signals_for_public,
)
from api.lib.query_bounds import MAX_BBOX_RESULTS, validate_bbox
from api.lib.response_types import (
    RadarBboxItem,
    RadarBboxResponse,
    RadarMoversResponse,
    RadarMunicipalitiesResponse,
    RadarParcelListResponse,
    RadarParcelPayload,
)
from api.lib.serialization import serialize_temporal_fields
from api.lib.settings import open_data_source_key
from api.lib.source_policy import require_source_use

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

VIEW_SCORE_COLUMN = {
    "opportunity": "dm.opportunity_score",
    "momentum": "dm.score",
    "readiness": "dm.site_readiness_score",
}
VIEW_DEFAULT_THRESHOLD = {"opportunity": 30, "momentum": 30, "readiness": 40}

PARCEL_CLASS_CODES = {"R", "C", "I", "F", "A", "E", "U"}
PLAN_STATUS_VALUES = {"any", "active", "none"}

RADAR_ROW_COLUMNS = """
    dm.pidn, dm.score, dm.opportunity_score, dm.site_readiness_score,
    dm.top_signal, dm.signal_count, dm.signals, dm.eligible, dm.has_active_plan,
    dm.score_version, dm.computed_at,
    dm.previous_score, dm.previous_opportunity_score, dm.score_delta,
    dm.opportunity_delta, dm.previous_computed_at, dm.is_new,
    p.owner_full,
    p.propadr, p.municipality, p.acres, p.aprtotal, p.class
"""


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


def _parcel_filters(
    params: dict,
    *,
    municipality: str | None,
    min_acres: float | None,
    max_acres: float | None,
    parcel_class: str | None,
) -> str:
    """Deterministic parcel-attribute filters shared by every radar list."""
    clauses = ""
    if municipality:
        clauses += " AND p.municipality ILIKE %(municipality)s"
        params["municipality"] = municipality
    if min_acres is not None:
        clauses += " AND p.acres >= %(min_acres)s"
        params["min_acres"] = min_acres
    if max_acres is not None:
        clauses += " AND p.acres <= %(max_acres)s"
        params["max_acres"] = max_acres
    if parcel_class:
        codes = [
            code.strip().upper() for code in parcel_class.split(",") if code.strip()
        ]
        codes = [code for code in codes if code in PARCEL_CLASS_CODES]
        if codes:
            clauses += " AND UPPER(p.class) = ANY(%(parcel_classes)s)"
            params["parcel_classes"] = codes
    return clauses


def _plan_status_clause(
    *,
    plan_status: str | None,
    view: str,
) -> str:
    """Filter on a recorded linked plan, without implying approval or availability."""
    resolved_status = plan_status or ("none" if view == "opportunity" else "any")
    if resolved_status not in PLAN_STATUS_VALUES:
        raise HTTPException(status_code=422, detail="Invalid plan_status")
    if resolved_status == "active":
        return " AND dm.has_active_plan = TRUE"
    if resolved_status == "none":
        return " AND dm.has_active_plan = FALSE"
    return ""


def _validate_acre_range(min_acres: float | None, max_acres: float | None) -> None:
    if min_acres is not None and max_acres is not None and min_acres > max_acres:
        raise HTTPException(
            status_code=422,
            detail="min_acres must be less than or equal to max_acres",
        )


def _serialize_radar_row(
    row: dict,
    reason_scope: set[str] | None = None,
    *,
    score_column: str = "score",
) -> RadarParcelPayload:
    d = dict(row)
    for key in ("acres", "aprtotal"):
        if d.get(key) is not None:
            try:
                d[key] = float(d[key])
            except (TypeError, ValueError):
                pass
    if score_column != "score":
        d["score"] = d.get(score_column)

    presentation_signals = sanitize_signals_for_public(d.get("signals"))
    if reason_scope is not None and isinstance(presentation_signals, dict):
        presentation_signals = {
            key: value
            for key, value in presentation_signals.items()
            if key in reason_scope
        }
        d["signal_count"] = len(presentation_signals)
    d["reason_signals"] = build_reason_signals(presentation_signals, limit=4)
    d["top_signal"] = compute_headline_signal(
        presentation_signals,
        fallback=None if reason_scope is not None else d.get("top_signal"),
    )
    d["signals"] = compact_signals_for_list(presentation_signals)
    d["is_new"] = bool(d.get("is_new"))
    serialize_temporal_fields(d, "computed_at", "previous_computed_at")
    return cast(RadarParcelPayload, d)


@router.get("/municipalities")
def radar_municipalities(
    view: str = Query(
        default="opportunity", pattern="^(opportunity|momentum|readiness)$"
    ),
    min_score: int | None = Query(default=None, ge=0, le=100),
    plan_status: str | None = Query(default=None, pattern="^(any|active|none)$"),
) -> RadarMunicipalitiesResponse:
    """Distinct municipalities available for the current radar cohort."""
    threshold = min_score if min_score is not None else VIEW_DEFAULT_THRESHOLD[view]
    score_column = VIEW_SCORE_COLUMN[view]
    plan_clause = _plan_status_clause(plan_status=plan_status, view=view)

    with get_cursor() as cur:
        _require_radar_sources(cur, include_tax_claims=view != "readiness")
        cur.execute(
            f"""
            SELECT DISTINCT p.municipality
            FROM public.current_development_momentum dm
            JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
            WHERE dm.eligible = TRUE
              {plan_clause}
              AND {score_column} >= %(min_score)s
              AND p.municipality IS NOT NULL
            ORDER BY p.municipality
        """,
            {"min_score": threshold},
        )
        rows = cur.fetchall()

    return {"municipalities": [r["municipality"] for r in rows]}


def _list_view(
    *,
    view: Literal["opportunity", "momentum", "readiness"],
    min_score: int,
    municipality: str | None,
    min_acres: float | None,
    max_acres: float | None,
    parcel_class: str | None,
    plan_status: str | None,
    limit: int,
    offset: int,
) -> RadarParcelListResponse:
    _validate_acre_range(min_acres, max_acres)
    params: dict = {"min_score": min_score, "limit": limit, "offset": offset}
    extra_where = _parcel_filters(
        params,
        municipality=municipality,
        min_acres=min_acres,
        max_acres=max_acres,
        parcel_class=parcel_class,
    )
    score_column = VIEW_SCORE_COLUMN[view]
    plan_clause = _plan_status_clause(plan_status=plan_status, view=view)
    payload_column = {
        "opportunity": "opportunity_score",
        "momentum": "score",
        "readiness": "site_readiness_score",
    }[view]

    with get_cursor() as cur:
        _require_radar_sources(cur, include_tax_claims=view != "readiness")
        cur.execute(
            f"""
            SELECT {RADAR_ROW_COLUMNS}
            FROM public.current_development_momentum dm
            JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
            WHERE dm.eligible = TRUE
              {plan_clause}
              AND {score_column} >= %(min_score)s
              {extra_where}
            ORDER BY {score_column} DESC, dm.signal_count DESC, dm.pidn
            LIMIT %(limit)s OFFSET %(offset)s
        """,
            params,
        )
        rows = cur.fetchall()
        coverage_row = None
        if view == "readiness":
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

    response: RadarParcelListResponse = {
        "count": len(rows),
        "parcels": [
            _serialize_radar_row(
                r,
                READINESS_SIGNAL_KEYS if view == "readiness" else None,
                score_column=payload_column,
            )
            for r in rows
        ],
    }
    if coverage_row is not None:
        loaded_layers = [key for key, loaded in coverage_row.items() if loaded]
        response["coverage"] = {
            "loaded_count": len(loaded_layers),
            "total_count": len(coverage_row),
            "loaded_layers": loaded_layers,
            "missing_layers": [
                key for key, loaded in coverage_row.items() if not loaded
            ],
        }
    return response


@router.get("/development")
def development_scores(
    min_score: int = Query(default=30, ge=0, le=100),
    municipality: str | None = Query(default=None),
    min_acres: float | None = Query(default=None, ge=0),
    max_acres: float | None = Query(default=None, ge=0),
    parcel_class: str | None = Query(default=None, alias="class", max_length=32),
    plan_status: str | None = Query(default=None, pattern="^(any|active|none)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RadarParcelListResponse:
    """Ranked parcels by development momentum score (where activity already is)."""
    return _list_view(
        view="momentum",
        min_score=min_score,
        municipality=municipality,
        min_acres=min_acres,
        max_acres=max_acres,
        parcel_class=parcel_class,
        plan_status=plan_status,
        limit=limit,
        offset=offset,
    )


@router.get("/opportunity")
def opportunity_scores(
    min_score: int = Query(default=30, ge=0, le=100),
    municipality: str | None = Query(default=None),
    min_acres: float | None = Query(default=None, ge=0),
    max_acres: float | None = Query(default=None, ge=0),
    parcel_class: str | None = Query(default=None, alias="class", max_length=32),
    plan_status: str | None = Query(default=None, pattern="^(any|active|none)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RadarParcelListResponse:
    """Parcels with strong fundamentals but NO plan or municipal matter of their own yet.

    Weights are calibrated against historical plan filings
    (docs/research/radar-backtest-2026-09-02.md); no model output is involved.
    """
    return _list_view(
        view="opportunity",
        min_score=min_score,
        municipality=municipality,
        min_acres=min_acres,
        max_acres=max_acres,
        parcel_class=parcel_class,
        plan_status=plan_status,
        limit=limit,
        offset=offset,
    )


@router.get("/site-readiness")
def site_readiness_scores(
    min_score: int = Query(default=40, ge=0, le=100),
    municipality: str | None = Query(default=None),
    min_acres: float | None = Query(default=None, ge=0),
    max_acres: float | None = Query(default=None, ge=0),
    parcel_class: str | None = Query(default=None, alias="class", max_length=32),
    plan_status: str | None = Query(default=None, pattern="^(any|active|none)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RadarParcelListResponse:
    """Parcels ranked by physical and policy readiness for development."""
    return _list_view(
        view="readiness",
        min_score=min_score,
        municipality=municipality,
        min_acres=min_acres,
        max_acres=max_acres,
        parcel_class=parcel_class,
        plan_status=plan_status,
        limit=limit,
        offset=offset,
    )


@router.get("/movers")
def radar_movers(
    view: Literal["opportunity", "momentum"] = Query(default="opportunity"),
    direction: Literal["up", "down", "new"] = Query(default="up"),
    municipality: str | None = Query(default=None),
    min_delta: int = Query(default=5, ge=1, le=100),
    min_score: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RadarMoversResponse:
    """Parcels whose score changed most since the previous rebuild, or that are new on radar.

    This is the change loop the radar lacked: a stateless weekly snapshot could
    never say "this parcel rose 18 points since last week".
    """
    params: dict = {
        "min_delta": min_delta,
        "min_score": min_score,
        "limit": limit,
        "offset": offset,
    }
    extra_where = _parcel_filters(
        params,
        municipality=municipality,
        min_acres=None,
        max_acres=None,
        parcel_class=None,
    )
    score_column = VIEW_SCORE_COLUMN[view]
    delta_column = "dm.opportunity_delta" if view == "opportunity" else "dm.score_delta"
    payload_column = "opportunity_score" if view == "opportunity" else "score"
    plan_clause = " AND dm.has_active_plan = FALSE" if view == "opportunity" else ""

    if direction == "new":
        where = f"dm.is_new = TRUE AND {score_column} >= GREATEST(%(min_score)s, %(min_delta)s)"
        order = f"{score_column} DESC, dm.pidn"
    elif direction == "up":
        where = f"{delta_column} >= %(min_delta)s AND {score_column} >= %(min_score)s"
        order = f"{delta_column} DESC, {score_column} DESC, dm.pidn"
    else:
        where = f"{delta_column} <= -%(min_delta)s"
        order = f"{delta_column} ASC, {score_column} DESC, dm.pidn"

    with get_cursor() as cur:
        _require_radar_sources(cur)
        cur.execute(
            f"""
            SELECT {RADAR_ROW_COLUMNS}
            FROM public.current_development_momentum dm
            JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
            WHERE dm.eligible = TRUE
              {plan_clause}
              AND {where}
              {extra_where}
            ORDER BY {order}
            LIMIT %(limit)s OFFSET %(offset)s
        """,
            params,
        )
        rows = cur.fetchall()
        cur.execute(
            "SELECT MAX(previous_computed_at) AS previous_computed_at FROM public.current_development_momentum"
        )
        previous_row = cur.fetchone() or {}

    previous = dict(previous_row)
    serialize_temporal_fields(previous, "previous_computed_at")
    return {
        "count": len(rows),
        "view": view,
        "direction": direction,
        "previous_computed_at": previous.get("previous_computed_at"),
        "parcels": [
            _serialize_radar_row(
                r,
                score_column=payload_column,
            )
            for r in rows
        ],
    }


@router.get("/development/bbox", response_model=None)
def development_bbox(
    west: float = Query(..., ge=-180, le=180),
    south: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180),
    north: float = Query(..., ge=-90, le=90),
    view: Literal["opportunity", "momentum", "readiness"] = Query(default="momentum"),
    min_score: int = Query(default=0, ge=0, le=100),
    municipality: str | None = Query(default=None),
    min_acres: float | None = Query(default=None, ge=0),
    max_acres: float | None = Query(default=None, ge=0),
    parcel_class: str | None = Query(default=None, alias="class", max_length=32),
    plan_status: str | None = Query(default=None, pattern="^(any|active|none)$"),
    limit: int = Query(default=MAX_BBOX_RESULTS, ge=1, le=MAX_BBOX_RESULTS),
) -> RadarBboxResponse:
    """Map layer for parcel coloring by development momentum or opportunity score."""
    validate_bbox(west, south, east, north)
    _validate_acre_range(min_acres, max_acres)
    score_column = VIEW_SCORE_COLUMN[view]
    params: dict = {
        "min_score": min_score,
        "west": west,
        "south": south,
        "east": east,
        "north": north,
        "fetch_limit": limit + 1,
    }
    parcel_filter_clause = _parcel_filters(
        params,
        municipality=municipality,
        min_acres=min_acres,
        max_acres=max_acres,
        parcel_class=parcel_class,
    )
    plan_clause = _plan_status_clause(plan_status=plan_status, view=view)
    with get_cursor() as cur:
        _require_radar_sources(cur, include_tax_claims=view != "readiness")
        cur.execute(
            f"""
            SELECT dm.pidn, {score_column} AS score, dm.eligible, dm.top_signal,
                   ST_X(ST_Centroid(p.geom)) AS lng,
                   ST_Y(ST_Centroid(p.geom)) AS lat
            FROM public.current_development_momentum dm
            JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
            WHERE dm.eligible = TRUE
              AND {score_column} >= %(min_score)s
              {plan_clause}
              {parcel_filter_clause}
              AND p.geom && ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)
            ORDER BY {score_column} DESC, dm.pidn
            LIMIT %(fetch_limit)s
        """,
            params,
        )
        rows = cur.fetchall()

    truncated = len(rows) > limit
    rows = rows[:limit]
    return {
        "count": len(rows),
        "limit": limit,
        "truncated": truncated,
        "parcels": [cast(RadarBboxItem, dict(r)) for r in rows],
    }
