"""Municipality listing and profile endpoints."""

from fastapi import APIRouter, HTTPException

from api.lib.database import get_cursor
from api.lib.municipality_names import (
    muni_name_to_pattern,
    municipality_event_patterns,
)
from api.lib.response_types import MunicipalityProfileResponse, MunicipalitySummary
from api.lib.serialization import serialize_temporal_fields
from api.lib.settings import open_data_source_key
from api.lib.source_policy import require_source_use, source_use_allowed

PIPELINE_WINDOW_DAYS = 365

router = APIRouter(tags=["municipalities"])


def _fetch_municipality_stats(cur, municipality_name: str) -> dict:
    cur.execute(
        """
        SELECT
            COUNT(DISTINCT pidn) AS parcel_count,
            COALESCE(SUM(COALESCE(aprtotal, 0)), 0) AS total_assessed
        FROM staging.parcels
        WHERE valid_to IS NULL
          AND UPPER(municipality) LIKE UPPER(%(municipality)s) || '%%'
        """,
        {"municipality": municipality_name},
    )
    row = cur.fetchone() or {}
    return {
        "parcel_count": row.get("parcel_count", 0) or 0,
        "total_assessed": float(row.get("total_assessed", 0) or 0),
    }


def _fetch_municipality_delinquency(cur, district_pattern: str) -> dict:
    cur.execute(
        """
        SELECT
            COUNT(DISTINCT pidn) AS delinquent_parcels,
            COALESCE(SUM(CASE WHEN total > 0 THEN total ELSE 0 END), 0) AS total_delinquent,
            MIN(tax_year) AS oldest_delinquent_year,
            COUNT(DISTINCT tax_year) AS delinquent_years
        FROM staging.tax_claims
        WHERE valid_to IS NULL
          AND UPPER(tax_district_name) LIKE UPPER(%(pattern)s)
        """,
        {"pattern": district_pattern},
    )
    row = cur.fetchone() or {}
    return {
        "delinquent_parcels": row.get("delinquent_parcels", 0) or 0,
        "total_delinquent": float(row.get("total_delinquent", 0) or 0),
        "oldest_delinquent_year": row.get("oldest_delinquent_year"),
        "delinquent_years": row.get("delinquent_years", 0) or 0,
    }


def _fetch_development_pipeline(cur, municipality_name: str) -> dict | None:
    """Planning-pipeline summary from the deterministic event table.

    Answers the developer job "what is moving through planning in this
    municipality" with source-backed events only; nothing here is generated.
    """
    if not source_use_allowed(cur, "public_proceedings", "derived_product"):
        return None
    patterns = municipality_event_patterns(municipality_name)
    cur.execute(
        """
        SELECT event_type, COUNT(*) AS count
        FROM public.intelligence_events
        WHERE category = 'development'
          AND municipality IS NOT NULL
          AND UPPER(municipality) LIKE ANY(%(patterns)s)
          AND COALESCE(event_date, detected_at::date) >= CURRENT_DATE - %(window)s
        GROUP BY event_type
        ORDER BY count DESC, event_type
        """,
        {"patterns": [p.upper() for p in patterns], "window": PIPELINE_WINDOW_DAYS},
    )
    by_type = [dict(row) for row in cur.fetchall()]

    def _matters(where: str, order: str, limit: int) -> list[dict]:
        cur.execute(
            f"""
            SELECT event_key, event_type, title, event_date, project_key, project_name,
                   related_pidns
            FROM public.intelligence_events
            WHERE category = 'development'
              AND municipality IS NOT NULL
              AND UPPER(municipality) LIKE ANY(%(patterns)s)
              AND {where}
            ORDER BY {order}
            LIMIT %(limit)s
            """,
            {
                "patterns": [p.upper() for p in patterns],
                "window": PIPELINE_WINDOW_DAYS,
                "limit": limit,
            },
        )
        rows = []
        for row in cur.fetchall():
            item = dict(row)
            item["related_pidns"] = list(item.get("related_pidns") or [])
            serialize_temporal_fields(item, "event_date")
            rows.append(item)
        return rows

    upcoming = _matters(
        "event_tags && ARRAY['upcoming_decision','hearing']::text[] "
        "AND COALESCE(event_date, detected_at::date) >= CURRENT_DATE - 60",
        "COALESCE(event_date, detected_at::date) DESC, event_key",
        8,
    )
    recent = _matters(
        "COALESCE(event_date, detected_at::date) >= CURRENT_DATE - %(window)s",
        "COALESCE(event_date, detected_at::date) DESC, detected_at DESC, event_key",
        12,
    )
    # Municipality-wide decisions (ordinance amendments, comprehensive plan
    # actions, sewer capacity, moratoria) answer "what is this township up
    # to" more directly than any single applicant's matter.
    policy = _matters(
        "event_tags && ARRAY['policy_action']::text[] "
        "AND COALESCE(event_date, detected_at::date) >= CURRENT_DATE - %(window)s",
        "COALESCE(event_date, detected_at::date) DESC, detected_at DESC, event_key",
        8,
    )
    return {
        "window_days": PIPELINE_WINDOW_DAYS,
        "total_matters": sum(int(row["count"]) for row in by_type),
        "by_event_type": by_type,
        "upcoming": upcoming,
        "recent": recent,
        "policy": policy,
    }


def _fetch_radar_top(cur, municipality_name: str, *, limit: int = 8) -> list[dict]:
    """Top opportunity parcels for the municipality, or [] when radar sources are gated."""
    for source_key in ("penndot_open_data", "fema_nfhl"):
        if not source_use_allowed(cur, source_key, "derived_product"):
            return []
    cur.execute(
        """
        SELECT dm.pidn, p.propadr, p.acres, dm.opportunity_score, dm.score,
               dm.top_signal, dm.opportunity_delta, dm.is_new
        FROM public.development_momentum dm
        JOIN staging.parcels p ON p.pidn = dm.pidn AND p.valid_to IS NULL
        WHERE dm.eligible = TRUE
          AND dm.has_active_plan = FALSE
          AND dm.opportunity_score > 0
          AND UPPER(p.municipality) LIKE UPPER(%(municipality)s) || '%%'
        ORDER BY dm.opportunity_score DESC, dm.signal_count DESC, dm.pidn
        LIMIT %(limit)s
        """,
        {"municipality": municipality_name, "limit": limit},
    )
    rows = []
    for row in cur.fetchall():
        item = dict(row)
        item["acres"] = float(item["acres"]) if item.get("acres") is not None else None
        item["is_new"] = bool(item.get("is_new"))
        rows.append(item)
    return rows


def _fetch_municipality_licenses(
    cur, municipality_name: str, *, limit: int = 50
) -> list[dict]:
    cur.execute(
        """
        SELECT
            NULL::text AS licensee,
            premises_name,
            premises_address,
            license_type,
            status,
            municipality,
            last_issue_date,
            expiration_date
        FROM staging.plcb_licenses
        WHERE valid_to IS NULL
          AND UPPER(status) = 'ACTIVE'
          AND UPPER(municipality) LIKE UPPER(%(municipality)s) || '%%'
        ORDER BY premises_name NULLS LAST, premises_address
        LIMIT %(limit)s
        """,
        {"municipality": municipality_name, "limit": limit},
    )
    return [dict(row) for row in cur.fetchall()]


@router.get("", response_model=None)
def list_municipalities() -> list[MunicipalitySummary]:
    """List all municipalities with delinquency stats."""
    with get_cursor() as cur:
        require_source_use(
            cur, open_data_source_key(), "derived_product", conceal=False
        )
        require_source_use(cur, "tax_claims", "derived_product", conceal=False)
        cur.execute("""
            SELECT name, muni_type
            FROM staging.municipalities
            WHERE valid_to IS NULL
            ORDER BY name
        """)
        munis = cur.fetchall()

        cur.execute("""
            SELECT
                tax_district_name,
                COUNT(DISTINCT pidn) AS delinquent_parcels,
                COALESCE(SUM(CASE WHEN total > 0 THEN total ELSE 0 END), 0) AS total_delinquent
            FROM staging.tax_claims
            WHERE valid_to IS NULL
            GROUP BY tax_district_name
        """)
        district_stats = {row["tax_district_name"]: row for row in cur.fetchall()}

    results = []
    for muni in munis:
        pattern = muni_name_to_pattern(muni["name"])
        base = pattern.rstrip("%").upper()
        delinquent_parcels = 0
        total_delinquent = 0.0
        for dist_name, stats in district_stats.items():
            if dist_name.upper().startswith(base):
                delinquent_parcels += stats["delinquent_parcels"]
                total_delinquent += float(stats["total_delinquent"])

        results.append(
            {
                "name": muni["name"],
                "muni_type": muni["muni_type"],
                "delinquent_parcels": delinquent_parcels,
                "total_delinquent": round(total_delinquent, 2),
            }
        )

    return results


@router.get("/{name}")
def get_municipality(name: str) -> MunicipalityProfileResponse:
    """Get a single municipality profile."""
    with get_cursor() as cur:
        require_source_use(
            cur, open_data_source_key(), "derived_product", conceal=False
        )
        require_source_use(cur, "tax_claims", "derived_product", conceal=False)
        require_source_use(cur, "plcb_licenses", "derived_product", conceal=False)
        cur.execute(
            """
            SELECT name, muni_type, county
            FROM staging.municipalities
            WHERE valid_to IS NULL AND UPPER(name) = UPPER(%s)
            """,
            (name,),
        )
        muni = cur.fetchone()
        if not muni:
            raise HTTPException(
                status_code=404, detail=f"Municipality not found: {name}"
            )

        pattern = muni_name_to_pattern(muni["name"])
        stats = _fetch_municipality_stats(cur, muni["name"])
        delinquency = _fetch_municipality_delinquency(cur, pattern)
        licenses = _fetch_municipality_licenses(cur, muni["name"], limit=50)
        development_pipeline = _fetch_development_pipeline(cur, muni["name"])
        radar_top = _fetch_radar_top(cur, muni["name"])

    return {
        **dict(muni),
        "stats": stats,
        "delinquency": delinquency,
        "licenses": licenses,
        "development_pipeline": development_pipeline,
        "radar_top": radar_top,
    }
