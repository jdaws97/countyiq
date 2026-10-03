"""Parcel endpoints — bbox query, property report card, delinquency overlay."""

from fastapi import APIRouter, HTTPException, Query

from api.lib.database import get_cursor
from api.lib.development_radar import (
    build_reason_signals,
    build_signal_presentation,
    compute_headline_signal,
    sanitize_signals_for_public,
)
from api.lib.evidence import (
    arcgis_record_url,
    evidence_item,
    signal_evidence_items,
)
from api.lib.flood_screening import parcel_flood_screening
from api.lib.inference_provenance import (
    BRIEF_SIGNAL_VERSIONS_CURRENT_SQL,
    CROSS_SIGNAL_SUMMARY_CURRENT_SQL,
    SUPPORTING_PROCEEDINGS_CURRENT_SQL,
)
from api.lib.municipal_evidence import fetch_municipal_evidence
from api.lib.query_bounds import MAX_BBOX_RESULTS, validate_bbox
from api.lib.record_briefs import build_record_brief
from api.lib.response_types import (
    ParcelBboxResponse,
    ParcelSummaryResponse,
    PropertyReportResponse,
)
from api.lib.serialization import serialize_temporal_fields
from api.lib.settings import county_metadata, open_data_source_key
from api.lib.site_intake import intake_packet
from api.lib.source_explanations import fetch_property_explanation
from api.lib.source_policy import require_source_use, source_use_allowed

router = APIRouter(tags=["parcels"])


@router.get("/{pidn}/evidence")
def municipal_property_evidence(
    pidn: str, limit: int = Query(12, ge=1, le=100)
) -> dict:
    with get_cursor() as cur:
        require_source_use(cur, "public_proceedings", "derived_product")
        cur.execute(
            "SELECT municipality FROM staging.parcels WHERE pidn=%s AND valid_to IS NULL",
            (pidn,),
        )
        parcel = cur.fetchone()
        if parcel is None:
            raise HTTPException(status_code=404, detail="Parcel not found")
        return fetch_municipal_evidence(
            cur, municipality=parcel["municipality"] or "", pidn=pidn, limit=limit
        )


def _soil_profile(rows: list[dict]) -> dict:
    """Build parcel-wide soil facts and plain-language screening considerations."""

    units: list[dict] = []
    considerations: list[str] = []
    for row in rows:
        unit = {
            key: value
            for key, value in row.items()
            if key not in {"mapped_coverage_pct", "very_limited_coverage_pct"}
        }
        for field in (
            "coverage_pct",
            "capability_class",
            "permeability",
            "representative_slope",
        ):
            if unit.get(field) is not None:
                unit[field] = float(unit[field])
        coverage = float(unit.get("coverage_pct") or 0)
        symbol = unit.get("map_unit_symbol") or "Mapped unit"
        representative = float(unit.get("representative_slope") or 0)
        if coverage >= 5 and representative >= 15:
            slope_range = (
                f"{unit.get('slope_low')}–{unit.get('slope_high')}% mapped slope"
                if unit.get("slope_low") is not None
                and unit.get("slope_high") is not None
                else f"{representative:g}% representative slope"
            )
            considerations.append(
                f"{symbol} covers {coverage:.1f}% of the parcel and has {slope_range} "
                f"({representative:g}% representative)."
            )
        drainage = str(unit.get("drainage") or "")
        if coverage >= 5 and drainage in {"Poorly drained", "Somewhat poorly drained"}:
            considerations.append(
                f"{symbol} covers {coverage:.1f}% and is mapped as {drainage.lower()}."
            )
        if coverage >= 5 and unit.get("hydrologic_group") == "D":
            considerations.append(
                f"{symbol} covers {coverage:.1f}% and is hydrologic group D, the high-runoff-potential group."
            )
        unit["coverage_pct"] = round(coverage, 1)
        units.append(unit)

    # Both totals come from geometric unions, including across unlike units.
    # Summing rounded card percentages would double-count overlapping polygons.
    very_limited = float(rows[0].get("very_limited_coverage_pct") or 0) if rows else 0
    if very_limited > 0:
        considerations.append(
            f"{min(very_limited, 100):.1f}% of the parcel is mapped as “Very limited” "
            "for on-lot septic suitability; this matters primarily where public sewer is unavailable."
        )
    if any(unit.get("drainage") == "Well drained" for unit in units) and considerations:
        considerations.append(
            "“Well drained” describes soil drainage only; it does not cancel separate slope, runoff, or septic limitations."
        )

    source_ids = sorted(
        {source_id for unit in units for source_id in unit["source_record_ids"]}
    )
    source_url = next(
        (unit.get("source_url") for unit in units if unit.get("source_url")), None
    )
    return {
        "mapped_coverage_pct": round(float(rows[0].get("mapped_coverage_pct") or 0), 1)
        if rows
        else 0,
        "units": units,
        "considerations": considerations,
        "source_record_ids": source_ids,
        "source_url": arcgis_record_url(source_url, "OBJECTID_1", source_ids)
        or source_url,
    }


@router.get("/bbox", response_model=None)
def parcels_bbox(
    west: float = Query(..., ge=-180, le=180),
    south: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180),
    north: float = Query(..., ge=-90, le=90),
    layer: str | None = Query(default=None),
    limit: int = Query(default=MAX_BBOX_RESULTS, ge=1, le=MAX_BBOX_RESULTS),
) -> ParcelBboxResponse:
    """Return parcels within a bounding box as GeoJSON.

    Optional layer=delinquent adds a derived tax-delinquency signal.
    """
    validate_bbox(west, south, east, north)
    with get_cursor() as cur:
        parcel_source = open_data_source_key()
        require_source_use(cur, parcel_source, "derived_product", conceal=False)
        bbox_params = {
            "west": west,
            "south": south,
            "east": east,
            "north": north,
            "fetch_limit": limit + 1,
        }
        if layer == "delinquent":
            require_source_use(cur, "tax_claims", "derived_product", conceal=False)
            cur.execute(
                """
                SELECT
                    ST_AsGeoJSON(p.geom)::json AS geometry,
                    p.pidn,
                    p.owner_full,
                    p.propadr, p.aprtotal, p.municipality,
                    p.class, p.saledt, p.price,
                    tc.pidn IS NOT NULL AS has_tax_delinquency
                FROM staging.parcels p
                LEFT JOIN (
                    SELECT DISTINCT pidn
                    FROM staging.tax_claims
                    WHERE valid_to IS NULL AND total > 0
                ) tc ON p.pidn = tc.pidn
                WHERE p.valid_to IS NULL
                  AND p.geom IS NOT NULL
                  AND p.geom && ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)
                ORDER BY p.pidn
                LIMIT %(fetch_limit)s
            """,
                bbox_params,
            )
        elif layer in {"vacant", "vacant_delinquent"}:
            tax_signal_sql = "NULL::boolean"
            if layer == "vacant_delinquent":
                require_source_use(cur, "tax_claims", "derived_product", conceal=False)
                tax_signal_sql = (
                    "EXISTS (SELECT 1 FROM staging.tax_claims tc "
                    "WHERE tc.valid_to IS NULL AND tc.total > 0 "
                    "AND tc.pidn = p.pidn)"
                )
            # Multi-signal vacancy: no building footprint + not recently sold at high price
            # Excludes parcels with high assessed value or recent expensive sales
            # which indicate development even if footprint data is stale
            cur.execute(
                f"""
                SELECT
                    ST_AsGeoJSON(p.geom)::json AS geometry,
                    p.pidn,
                    p.owner_full,
                    p.propadr, p.aprtotal, p.municipality,
                    p.class, p.saledt, p.price,
                    {tax_signal_sql} AS has_tax_delinquency
                FROM staging.parcels p
                WHERE p.valid_to IS NULL
                  AND p.geom IS NOT NULL
                  AND p.geom && ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)
                  AND NOT EXISTS (
                      SELECT 1 FROM staging.structures s
                      WHERE s.valid_to IS NULL AND s.geom IS NOT NULL
                        AND ST_Intersects(s.geom, p.geom)
                  )
                  AND (
                      p.class NOT IN ('R')
                      OR p.aprtotal IS NULL
                      OR p.aprtotal::numeric < 50000
                  )
                  AND (p.price IS NULL OR p.price::numeric < 100000)
                ORDER BY p.pidn
                LIMIT %(fetch_limit)s
            """,
                bbox_params,
            )
        else:
            cur.execute(
                """
                SELECT
                    ST_AsGeoJSON(p.geom)::json AS geometry,
                    p.pidn,
                    p.owner_full,
                    p.propadr, p.aprtotal, p.municipality,
                    p.class, p.saledt, p.price
                FROM staging.parcels p
                WHERE p.valid_to IS NULL
                  AND p.geom IS NOT NULL
                  AND p.geom && ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)
                ORDER BY p.pidn
                LIMIT %(fetch_limit)s
            """,
                bbox_params,
            )
        rows = cur.fetchall()

    truncated = len(rows) > limit
    rows = rows[:limit]
    features = []
    for row in rows:
        record = dict(row)
        geom = record.pop("geometry")
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    k: (
                        float(v)
                        if k in ("aprtotal", "price", "delinquent_total")
                        and v is not None
                        else v
                    )
                    for k, v in record.items()
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "count": len(features),
        "limit": limit,
        "truncated": truncated,
        "features": features,
    }


@router.get("/near")
def parcels_near(
    pidn: str | None = Query(default=None, max_length=32),
    project_key: str | None = Query(default=None, max_length=64),
    radius_m: int = Query(default=800, ge=50, le=3000),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Parcels within ``radius_m`` of an anchor parcel or a project's linked parcels.

    This is the corridor question ("what is around the plan that just landed")
    that neither the radar filters nor the map could answer directly. Rows are
    ranked by opportunity score, then distance. Owner names are public record;
    an owner links to its case file when the entity resolver knows it.
    """
    if not pidn and not project_key:
        raise HTTPException(status_code=422, detail="pidn or project_key is required")

    with get_cursor() as cur:
        parcel_source = open_data_source_key()
        require_source_use(cur, parcel_source, "derived_product", conceal=False)
        include_tax = source_use_allowed(cur, "tax_claims", "derived_product")
        include_scores = all(
            source_use_allowed(cur, key, "derived_product")
            for key in ("penndot_open_data", "fema_nfhl")
        )

        anchors: list[str] = [pidn.strip()] if pidn and pidn.strip() else []
        if project_key:
            cur.execute(
                """
                SELECT DISTINCT linked.pidn
                FROM public.current_intelligence_events ev
                CROSS JOIN LATERAL unnest(COALESCE(ev.related_pidns, ARRAY[]::text[])) AS linked(pidn)
                WHERE ev.project_key = %(project_key)s
                ORDER BY linked.pidn
                LIMIT 50
                """,
                {"project_key": project_key},
            )
            anchors.extend(str(row["pidn"]) for row in cur.fetchall())
        anchors = list(dict.fromkeys(anchors))[:50]

        rows: list[dict] = []
        anchor_point = None
        if anchors:
            tax_sql = (
                "EXISTS (SELECT 1 FROM staging.tax_claims tc "
                "WHERE tc.valid_to IS NULL AND tc.total > 0 AND tc.pidn = p.pidn)"
                if include_tax
                else "NULL::boolean"
            )
            cur.execute(
                f"""
                WITH anchor AS (
                    SELECT ST_Union(geom) AS geom
                    FROM staging.parcels
                    WHERE pidn = ANY(%(anchors)s) AND valid_to IS NULL AND geom IS NOT NULL
                )
                SELECT
                    p.pidn, p.propadr, p.municipality, p.class, p.acres, p.aprtotal,
                    p.saledt, p.price,
                    ROUND(ST_Distance(p.geom::geography, a.geom::geography)::numeric) AS distance_m,
                    ST_Y(ST_Centroid(p.geom)) AS lat,
                    ST_X(ST_Centroid(p.geom)) AS lng,
                    ST_Y(ST_Centroid(a.geom)) AS anchor_lat,
                    ST_X(ST_Centroid(a.geom)) AS anchor_lng,
                    p.owner_full,
                    owner_entity.owner_id,
                    lower(COALESCE(owner_entity.entity_type, '')) AS entity_type,
                    {tax_sql} AS has_tax_delinquency,
                    NOT EXISTS (
                        SELECT 1 FROM staging.structures s
                        WHERE s.valid_to IS NULL AND s.geom IS NOT NULL
                          AND ST_Intersects(s.geom, p.geom)
                    )
                    AND (p.class NOT IN ('R') OR p.aprtotal IS NULL OR p.aprtotal::numeric < 50000)
                    AND (p.price IS NULL OR p.price::numeric < 100000) AS likely_vacant,
                    dm.opportunity_score, dm.score AS momentum_score,
                    dm.site_readiness_score, dm.top_signal, dm.has_active_plan, dm.eligible
                FROM staging.parcels p
                CROSS JOIN anchor a
                LEFT JOIN public.owner_source_links osl
                    ON osl.source_type = 'parcel' AND osl.source_id = p.pidn
                LEFT JOIN public.owners owner_entity ON owner_entity.owner_id = osl.owner_id
                LEFT JOIN public.current_development_momentum dm ON dm.pidn = p.pidn
                WHERE p.valid_to IS NULL
                  AND p.geom IS NOT NULL
                  AND a.geom IS NOT NULL
                  AND NOT (p.pidn = ANY(%(anchors)s))
                  AND ST_DWithin(p.geom::geography, a.geom::geography, %(radius_m)s)
                ORDER BY COALESCE(dm.opportunity_score, 0) DESC, distance_m ASC, p.pidn
                LIMIT %(limit)s
                """,
                {
                    "anchors": anchors,
                    "radius_m": radius_m,
                    "limit": limit,
                },
            )
            rows = [dict(row) for row in cur.fetchall()]
            if not rows:
                cur.execute(
                    """
                    SELECT ST_Y(ST_Centroid(ST_Union(geom))) AS anchor_lat,
                           ST_X(ST_Centroid(ST_Union(geom))) AS anchor_lng
                    FROM staging.parcels
                    WHERE pidn = ANY(%(anchors)s) AND valid_to IS NULL AND geom IS NOT NULL
                    """,
                    {"anchors": anchors},
                )
                anchor_point = cur.fetchone()

    parcels = []
    for row in rows:
        owner_kind = row.get("entity_type") or "unknown"
        owner_label = row.get("owner_full")
        owner_id = row.get("owner_id")
        parcels.append(
            {
                "pidn": row["pidn"],
                "propadr": row.get("propadr"),
                "municipality": row.get("municipality"),
                "class": row.get("class"),
                "acres": float(row["acres"]) if row.get("acres") is not None else None,
                "aprtotal": float(row["aprtotal"])
                if row.get("aprtotal") is not None
                else None,
                "saledt": row.get("saledt"),
                "price": float(row["price"]) if row.get("price") is not None else None,
                "distance_m": int(row["distance_m"])
                if row.get("distance_m") is not None
                else None,
                "lat": row.get("lat"),
                "lng": row.get("lng"),
                "owner_label": owner_label,
                "owner_kind": owner_kind,
                "owner_id": owner_id,
                "has_tax_delinquency": row.get("has_tax_delinquency"),
                "likely_vacant": bool(row.get("likely_vacant")),
                "opportunity_score": row.get("opportunity_score")
                if include_scores
                else None,
                "momentum_score": row.get("momentum_score") if include_scores else None,
                "site_readiness_score": row.get("site_readiness_score")
                if include_scores
                else None,
                "top_signal": row.get("top_signal") if include_scores else None,
                "has_active_plan": bool(row.get("has_active_plan"))
                if include_scores
                else False,
            }
        )

    first = rows[0] if rows else (dict(anchor_point) if anchor_point else {})
    return {
        "anchor_pidns": anchors,
        "anchor_lat": first.get("anchor_lat"),
        "anchor_lng": first.get("anchor_lng"),
        "radius_m": radius_m,
        "count": len(parcels),
        "parcels": parcels,
    }


@router.get("/summary")
def parcels_summary(
    pidns: str = Query(
        ...,
        max_length=2000,
        description="Comma-separated PIDNs, max 100",
    ),
) -> dict:
    """Batch summary for a set of parcels — powers the client-side watchlist.

    Returns current fundamentals plus change indicators derived from SCD2:
    `changed_at` is the current row's valid_from. A recent initial observation
    is not a change: `changed_recently` also requires an earlier source version.
    """
    pidn_list = [p.strip() for p in pidns.split(",") if p.strip()][:100]
    if not pidn_list:
        return {"parcels": []}

    with get_cursor() as cur:
        parcel_source = open_data_source_key()
        require_source_use(cur, parcel_source, "derived_product", conceal=False)
        require_source_use(cur, "tax_claims", "derived_product", conceal=False)
        cur.execute(
            """
            SELECT
                p.pidn,
                p.owner_full,
                p.propadr, p.municipality,
                p.aprtotal, p.class, p.acres,
                p.valid_from AS changed_at,
                (p.valid_from >= NOW() - INTERVAL '30 days' AND EXISTS (
                    SELECT 1 FROM staging.parcels previous
                    WHERE previous.pidn = p.pidn AND previous.valid_to IS NOT NULL
                      AND previous.valid_from < p.valid_from
                )) AS changed_recently,
                EXISTS (
                    SELECT 1 FROM staging.tax_claims tc
                    WHERE tc.valid_to IS NULL AND tc.total > 0 AND tc.pidn = p.pidn
                ) AS has_tax_delinquency,
                dm.score AS momentum_score,
                dm.site_readiness_score,
                dm.top_signal
            FROM staging.parcels p
            LEFT JOIN public.current_development_momentum dm ON dm.pidn = p.pidn
            WHERE p.valid_to IS NULL AND p.pidn = ANY(%(pidns)s)
            ORDER BY p.valid_from DESC
            """,
            {
                "pidns": pidn_list,
            },
        )
        rows = [dict(r) for r in cur.fetchall()]

    for row in rows:
        for key in ("aprtotal", "acres"):
            if row.get(key) is not None:
                row[key] = float(row[key])
        serialize_temporal_fields(row, "changed_at")
    found = {r["pidn"] for r in rows}
    return {
        "parcels": rows,
        "missing": [p for p in pidn_list if p not in found],
    }


@router.get("/{pidn}/summary")
def parcel_summary(pidn: str) -> ParcelSummaryResponse:
    """Map facts without calculating the full report's soil coverage."""
    report = _parcel_report(pidn, include_soils=False)
    return {
        "parcel": report["parcel"],
        "tax_delinquency": report["tax_delinquency"],
        "flood_zone": report["flood_zone"],
        "structures": report["structures"],
        "development_momentum": report["development_momentum"],
        "source_explanation": report["source_explanation"],
    }


@router.get("/{pidn}/intake")
def parcel_intake(pidn: str) -> dict:
    report = _parcel_report(pidn, include_soils=True)
    with get_cursor(snapshot=True) as cur:
        for source in (
            open_data_source_key(),
            "fema_nfhl",
            "tax_claims",
            "public_proceedings",
        ):
            require_source_use(cur, source, "derived_product", conceal=False)
        return intake_packet(cur, report)


@router.get("/{pidn}")
def parcel_detail(pidn: str) -> PropertyReportResponse:
    """Full property report card for a single parcel."""
    return _parcel_report(pidn, include_soils=True)


def _parcel_report(pidn: str, *, include_soils: bool) -> PropertyReportResponse:
    with get_cursor(snapshot=True) as cur:
        parcel_source = open_data_source_key()
        require_source_use(cur, parcel_source, "derived_product", conceal=False)
        require_source_use(cur, "tax_claims", "derived_product", conceal=False)
        require_source_use(cur, "public_proceedings", "derived_product", conceal=False)
        require_source_use(cur, "fema_nfhl", "derived_product", conceal=False)
        cur.execute(
            """
            SELECT pidn, owner_full, own_name1, own_name2, prev_owner,
                   (
                       SELECT osl.owner_id
                       FROM public.owner_source_links osl
                       WHERE osl.source_type = 'parcel' AND osl.source_id = pidn
                       ORDER BY osl.owner_id
                       LIMIT 1
                   ) AS owner_id,
                   propadr, mail_addr_full, municipality, school_dis,
                   class, luc, acres, style, num_stories, res_living_area,
                   yrblt, heatsys, fuel, clean_green, grade, cdu,
                   aprland, aprbldg, aprtotal, saledt, price, prev_price,
                   deed_bk, deed_pg, comm_struc, comm_year_built, comm_building_sq_ft,
                   source_url, valid_from AS parcel_record_effective_at,
                   ST_Y(ST_Centroid(geom)) AS lat,
                   ST_X(ST_Centroid(geom)) AS lng
            FROM staging.parcels
            WHERE pidn = %(pidn)s AND valid_to IS NULL
        """,
            {"pidn": pidn},
        )
        parcel = cur.fetchone()
        if not parcel:
            raise HTTPException(status_code=404, detail=f"Parcel not found: {pidn}")

        # Current zoning at the parcel center point: table stakes for "can a
        # business go here", separate from the plan/zoning divergence signal.
        cur.execute(
            """
            SELECT z.zrecid, z.zcode, z.zname, z.ztype, z.gen_zcode, z.gen_zname,
                   z.muni_name, z.muni_ord, z.adpt_date, z.source_url, z.valid_from
            FROM staging.parcels p
            CROSS JOIN LATERAL public.parcel_center_zoning(p.geom) z
            WHERE p.pidn = %(pidn)s AND p.valid_to IS NULL
        """,
            {"pidn": pidn},
        )
        zoning_row = cur.fetchone()

        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE total > 0) > 0 AS has_tax_delinquency,
                MAX(source_url) FILTER (WHERE total > 0) AS source_url,
                MAX(valid_from) FILTER (WHERE total > 0) AS record_effective_at
            FROM staging.tax_claims
            WHERE pidn = %(pidn)s AND valid_to IS NULL
        """,
            {"pidn": pidn},
        )
        tax_signal = cur.fetchone() or {"has_tax_delinquency": False}

        flood = parcel_flood_screening(cur, pidn)

        soil_rows = []
        if include_soils:
            cur.execute(
                """
                SELECT s.*
                FROM staging.parcels p
                CROSS JOIN LATERAL public.parcel_soil_units(p.geom) s
                WHERE p.pidn = %(pidn)s AND p.valid_to IS NULL
                ORDER BY s.coverage_pct DESC, s.source_record_ids
                """,
                {"pidn": pidn},
            )
            soil_rows = cur.fetchall()

        cur.execute(
            """
            SELECT s.objectid, s.index_id, s.building_type, s.source_url, s.valid_from,
                   ROUND(ST_Area(ST_Transform(s.geom, 32617))::numeric) AS sqm
            FROM staging.structures s
            WHERE s.valid_to IS NULL
              AND s.geom IS NOT NULL
              AND ST_Intersects(s.geom, (
                  SELECT geom FROM staging.parcels WHERE pidn = %(pidn)s AND valid_to IS NULL
              ))
            ORDER BY ST_Area(s.geom) DESC
        """,
            {"pidn": pidn},
        )
        structure_rows = cur.fetchall()

        cur.execute(
            """
            SELECT score, opportunity_score, site_readiness_score,
                   has_active_plan, eligible,
                   exclusion_reasons, signals, top_signal,
                   signal_count, score_version, computed_at
            FROM public.current_development_momentum WHERE pidn = %(pidn)s
        """,
            {"pidn": pidn},
        )
        momentum_row = cur.fetchone()

        # Parcel brief (Pass 3)
        cur.execute(
            f"""
            SELECT
                brief_text,
                (
                    SELECT action_history.payload->>'recommendation'
                    FROM meta.intelligence_inference_history action_history
                    WHERE action_history.inference_id = brief.active_inference_id
                ) AS recommendation,
                assessment,
                assessment_reasoning,
                key_questions,
                signal_count,
                citations,
                brief_version,
                generated_at
            FROM public.parcel_briefs brief
            WHERE pidn = %(pidn)s
              AND {BRIEF_SIGNAL_VERSIONS_CURRENT_SQL}
              AND EXISTS (
                  SELECT 1 FROM meta.intelligence_inference_history context_history
                  WHERE context_history.inference_id=brief.active_inference_id
                    AND context_history.evidence_refs ? (
                        'parcel-context:v1:' || meta.parcel_brief_source_fingerprint(brief.pidn)
                    )
              )
              AND NOT EXISTS (
                  SELECT 1 FROM jsonb_array_elements_text(COALESCE(brief.citations, '[]'::jsonb)) citation(signal_key)
                  WHERE NOT EXISTS (
                      SELECT 1 FROM public.evidence supporting
                      WHERE supporting.pidn = brief.pidn
                        AND supporting.signal_key = citation.signal_key
                        AND supporting.validation_status IN ('confirmed', 'upgraded', 'downgraded')
                        AND {SUPPORTING_PROCEEDINGS_CURRENT_SQL}
                  )
              )
        """,
            {"pidn": pidn, "brief_kind": "parcel_brief", "brief_subject": pidn},
        )
        brief_row = cur.fetchone()

        # Pass 4 has no immutable upstream dependency receipts or serving-time
        # freshness contract. Expiry and parcel membership cannot certify prose.
        # Retain stored narratives, but do not expose them until that contract
        # supports source revocation, changed evidence and legacy-cache handling.
        related_narratives = []

        # Pass 2 cross-signal insight for this parcel
        cur.execute(
            f"""
            SELECT cross_signal_insight, last_run_at, signals_validated_count
            FROM meta.intelligence_passes pass_record
            WHERE pidn = %(pidn)s AND pass_number = 2 AND status = 'complete'
              AND {CROSS_SIGNAL_SUMMARY_CURRENT_SQL}
        """,
            {"pidn": pidn},
        )
        intelligence_row = cur.fetchone()

        # Use the shared attribution result, subject to current source eligibility.
        cur.execute(
            """
            SELECT
                pe.proceeding_id,
                pp.body_name,
                pp.meeting_date,
                pp.proceeding_type,
                pp.source_url,
                pp.content_hash,
                pp.valid_from AS source_observed_at,
                pe.extraction_type,
                pe.applicant_name,
                pe.decision,
                pe.extraction_details->>'decision_scope' AS decision_scope,
                pe.current_zoning,
                pe.proposed_zoning,
                LEFT(pe.supporting_text, 280) AS supporting_text,
                pp.document_url,
                pe.extraction_confidence,
                pe.page_number,
                pe.extracted_at AS interpretation_observed_at,
                matched.match_method AS match_type
            FROM staging.proceeding_extractions pe
            JOIN staging.public_proceedings pp ON pp.id = pe.proceeding_id
            CROSS JOIN LATERAL public.proceeding_parcel_matches(
                COALESCE(pe.extraction_details->'parcel_references', jsonb_build_array(pe.parcel_reference)),
                pp.body_name) matched
            WHERE pp.valid_to IS NULL
              AND LEFT(pe.extraction_type, 1) <> '_'
              AND matched.pidn = %(pidn)s
              AND pp.metadata_quality->>'status' = 'ready'
              AND EXISTS (
                  SELECT 1 FROM meta.municipality_source_rights body_policy
                  WHERE body_policy.body_name = pp.body_name
                    AND body_policy.rights_status <> 'paused'
                    AND body_policy.derived_product_allowed
                    AND body_policy.review_due_on >= CURRENT_DATE
              )
            ORDER BY pp.meeting_date DESC NULLS LAST, pe.proceeding_id DESC
            LIMIT 20
        """,
            {
                "pidn": pidn,
            },
        )
        proceeding_rows = cur.fetchall()
        municipal_evidence = fetch_municipal_evidence(
            cur, municipality=parcel["municipality"] or "", pidn=pidn
        )
        source_explanation = fetch_property_explanation(cur, pidn)

    p = dict(parcel)
    parcel_source_url = p.pop("source_url", None)
    parcel_record_effective_at = p.pop("parcel_record_effective_at", None)
    for key in (
        "aprland",
        "aprbldg",
        "aprtotal",
        "price",
        "prev_price",
        "acres",
        "lat",
        "lng",
    ):
        if p.get(key):
            p[key] = float(p[key])

    structure_count = len(structure_rows)
    # Multi-signal vacancy: no footprint + not high-value residential
    likely_vacant = (
        structure_count == 0
        and (
            p.get("class") not in ("R",)
            or not p.get("aprtotal")
            or float(p.get("aprtotal") or 0) < 50000
        )
        and (not p.get("price") or float(p.get("price") or 0) < 100000)
    )
    soil = _soil_profile([dict(row) for row in soil_rows])
    momentum = dict(momentum_row) if momentum_row else None
    signal_receipts: list[dict] = []
    if momentum:
        momentum["signals"] = sanitize_signals_for_public(momentum.get("signals"))
        public_signals = momentum.get("signals") or {}
        signal_receipts = signal_evidence_items(
            public_signals,
            public_signals.keys(),
            scope=f"parcel:{pidn}:signals",
            pidn=pidn,
            observed_at=momentum.get("computed_at"),
        )
        receipts_by_key = {
            receipt["citation_key"].removeprefix("signal:"): receipt
            for receipt in signal_receipts
        }
        decorated_signals: dict[str, object] = {}
        for key, raw_signal in public_signals.items():
            signal = (
                dict(raw_signal)
                if isinstance(raw_signal, dict)
                else {"value": raw_signal}
            )
            signal["presentation"] = build_signal_presentation(key, signal)
            if key in receipts_by_key:
                signal["evidence_receipt"] = receipts_by_key[key]
            decorated_signals[key] = signal
        momentum["signals"] = decorated_signals
        momentum["reason_signals"] = build_reason_signals(momentum.get("signals"))
        momentum["top_signal"] = compute_headline_signal(
            momentum.get("signals"),
            fallback=momentum.get("top_signal"),
        )
        serialize_temporal_fields(momentum, "computed_at")

    brief = dict(brief_row) if brief_row else None
    if brief:
        if brief.get("recommendation") not in {
            "investigate",
            "watch",
            "insufficient_evidence",
        }:
            brief["recommendation"] = None
        brief["key_questions"] = brief.get("key_questions") or []
        brief["citations"] = brief.get("citations") or []
        serialize_temporal_fields(brief, "generated_at")
        brief["citation_evidence"] = signal_evidence_items(
            momentum.get("signals") if momentum else None,
            brief["citations"],
            scope=f"parcel:{pidn}:brief",
            pidn=pidn,
            observed_at=brief.get("generated_at"),
        )

    narratives = [dict(row) for row in related_narratives]
    for narrative in narratives:
        narrative["key_entities"] = narrative.get("key_entities") or []
        narrative["citations"] = narrative.get("citations") or []
        serialize_temporal_fields(narrative, "generated_at")
        narrative["citation_evidence"] = signal_evidence_items(
            momentum.get("signals") if momentum else None,
            narrative["citations"],
            scope=f"parcel:{pidn}:narrative:{narrative['narrative_id']}",
            pidn=pidn,
            observed_at=narrative.get("generated_at"),
        )

    intelligence_summary = dict(intelligence_row) if intelligence_row else None
    if intelligence_summary:
        serialize_temporal_fields(intelligence_summary, "last_run_at")

    linked_proceedings = []
    for row in proceeding_rows:
        record = dict(row)
        if record.get("extraction_confidence") is not None:
            record["extraction_confidence"] = float(record["extraction_confidence"])
        serialize_temporal_fields(
            record,
            "meeting_date",
            "source_observed_at",
            "interpretation_observed_at",
        )
        source_url = record.pop("source_url", None)
        content_hash = record.pop("content_hash", None)
        source_observed_at = record.pop("source_observed_at", None)
        interpretation_observed_at = record.pop("interpretation_observed_at", None)
        record["evidence"] = evidence_item(
            scope=f"parcel:{pidn}",
            citation_key=f"proceeding:{record['proceeding_id']}",
            label=record.get("body_name") or "Municipal proceeding",
            source_kind="municipal_proceeding",
            source_record_id=content_hash or record["proceeding_id"],
            url=source_url,
            document_url=record.get("document_url"),
            excerpt=record.get("supporting_text"),
            details={
                key: record.get(key)
                for key in (
                    "proceeding_type",
                    "extraction_type",
                    "decision",
                    "decision_scope",
                    "current_zoning",
                    "proposed_zoning",
                    "page_number",
                    "match_type",
                )
                if record.get(key) is not None
            },
            effective_at=record.get("meeting_date"),
            observed_at=interpretation_observed_at or source_observed_at,
            method="CountyIQ extracted this linked matter from the municipal document. Consult the source passage for its full context.",
            caveat=(
                "An address match can be ambiguous; confirm the parcel reference in the original document."
                if record.get("match_type") == "address"
                else None
            ),
            confidence=record.get("extraction_confidence"),
        )
        linked_proceedings.append(record)

    zoning = None
    if zoning_row:
        zoning = {
            "code": zoning_row.get("zcode"),
            "name": zoning_row.get("zname"),
            "type": zoning_row.get("ztype"),
            "general_code": zoning_row.get("gen_zcode"),
            "general_name": zoning_row.get("gen_zname"),
            "municipality": zoning_row.get("muni_name"),
            "ordinance": zoning_row.get("muni_ord"),
            "adopted": zoning_row.get("adpt_date"),
            "source_url": zoning_row.get("source_url"),
        }
        serialize_temporal_fields(zoning, "adopted")

    county_name = county_metadata()["county_name"]
    report_evidence = [
        evidence_item(
            scope=f"parcel:{pidn}",
            citation_key=f"parcel:{pidn}",
            label=f"{county_name} parcel and assessment record",
            source_kind="official_parcel_record",
            source_record_id=pidn,
            url=parcel_source_url,
            record_query=("PIDN", [pidn]),
            internal_url=f"/property/{pidn}",
            details={
                key: p.get(key)
                for key in (
                    "pidn",
                    "propadr",
                    "owner_full",
                    "municipality",
                    "acres",
                    "aprland",
                    "aprbldg",
                    "aprtotal",
                    "saledt",
                    "price",
                    "deed_bk",
                    "deed_pg",
                )
                if p.get(key) is not None
            },
            effective_at=None,
            observed_at=parcel_record_effective_at,
            method="CountyIQ displays the current versioned county parcel record without LLM interpretation.",
            caveat="Assessment and deed fields are informational county records; confirm legal title with the recorder or a title professional.",
        )
    ]
    if soil["units"]:
        soil_dates = [
            unit.get("valid_from") for unit in soil["units"] if unit.get("valid_from")
        ]
        soil_receipt = evidence_item(
            scope=f"parcel:{pidn}",
            citation_key=f"soils:{pidn}",
            label=f"{county_name} mapped soil units",
            source_kind="official_soil_layer",
            source_record_id=",".join(
                str(value) for value in soil["source_record_ids"]
            ),
            url=next(
                (
                    unit.get("source_url")
                    for unit in soil["units"]
                    if unit.get("source_url")
                ),
                None,
            ),
            record_query=("OBJECTID_1", soil["source_record_ids"]),
            details={
                "mapped_coverage_pct": soil["mapped_coverage_pct"],
                "map_units": [
                    {
                        key: unit.get(key)
                        for key in (
                            "source_record_ids",
                            "map_unit_key",
                            "map_unit_symbol",
                            "map_unit_name",
                            "coverage_pct",
                            "drainage",
                            "septic_rating",
                            "slope_low",
                            "slope_high",
                            "representative_slope",
                            "hydric_rating",
                            "hydrologic_group",
                        )
                        if unit.get(key) is not None
                    }
                    for unit in soil["units"]
                ],
            },
            effective_at=None,
            observed_at=max(soil_dates) if soil_dates else None,
            method="CountyIQ intersects current soil polygons with the parcel, groups matching map units and attributes, and unions their geometry before calculating coverage. Source IDs retain every contributing polygon.",
            caveat="Mapped soils are generalized screening data; site design, wastewater suitability, drainage, and foundations require parcel-specific professional review.",
        )
        soil["evidence"] = soil_receipt
        soil["source_url"] = soil_receipt["url"]
        report_evidence.append(soil_receipt)
    if tax_signal.get("has_tax_delinquency"):
        report_evidence.append(
            evidence_item(
                scope=f"parcel:{pidn}",
                citation_key=f"tax-status:{pidn}",
                label=f"{county_name} tax-claim listing",
                source_kind="official_tax_listing",
                source_record_id=pidn,
                url=tax_signal.get("source_url"),
                document_url=tax_signal.get("source_url"),
                details={"delinquency_signal": True},
                effective_at=None,
                observed_at=tax_signal.get("record_effective_at"),
                method="CountyIQ checks whether the PIDN appears with a positive balance in the current governed listing.",
                caveat="The public product suppresses exact claim rows and balances; confirm the current amount with the Tax Claim Bureau.",
            )
        )
    if flood["evidence"]:
        report_evidence.append(flood["evidence"])
    if structure_rows:
        structure_dates = [
            row.get("valid_from") for row in structure_rows if row.get("valid_from")
        ]
        structure_ids = [
            row.get("objectid")
            for row in structure_rows
            if row.get("objectid") is not None
        ]
        report_evidence.append(
            evidence_item(
                scope=f"parcel:{pidn}",
                citation_key=f"structures:{pidn}",
                label=f"{county_name} building-footprint layer",
                source_kind="official_structure_layer",
                source_record_id=",".join(str(value) for value in structure_ids)
                or pidn,
                url=next(
                    (
                        row.get("source_url")
                        for row in structure_rows
                        if row.get("source_url")
                    ),
                    None,
                ),
                record_query=("OBJECTID", structure_ids),
                details={
                    "footprint_count": structure_count,
                    "building_types": [
                        row.get("building_type") or "Unknown" for row in structure_rows
                    ],
                },
                effective_at=None,
                observed_at=max(structure_dates) if structure_dates else None,
                method="CountyIQ deterministically intersects county building footprints with the parcel geometry.",
                caveat="A missing footprint can reflect vacant land, recent construction, or source-data lag.",
            )
        )
    if zoning_row:
        report_evidence.append(
            evidence_item(
                scope=f"parcel:{pidn}",
                citation_key=f"zoning:{zoning_row.get('zrecid') or pidn}",
                label=f"{county_name} zoning layer",
                source_kind="official_zoning_layer",
                source_record_id=str(zoning_row.get("zrecid") or ""),
                url=zoning_row.get("source_url"),
                record_query=("ZRECID", [zoning_row.get("zrecid")]),
                details={
                    key: zoning.get(key)
                    for key in (
                        "code",
                        "name",
                        "type",
                        "general_name",
                        "municipality",
                        "ordinance",
                        "adopted",
                    )
                    if zoning.get(key) is not None
                },
                effective_at=zoning_row.get("adpt_date"),
                observed_at=zoning_row.get("valid_from"),
                method="CountyIQ intersects the parcel center point with the county zoning layer.",
                caveat="A center-point match can miss a split-zoned parcel; confirm against the municipal ordinance and official zoning map.",
            )
        )
    report_evidence.extend(signal_receipts)
    for item in report_evidence:
        if not item.get("internal_url"):
            item["internal_url"] = f"/property/{pidn}"
        serialize_temporal_fields(item, "effective_at", "observed_at")

    return {
        "parcel": p,
        "tax_delinquency": {
            "detail_available": False,
            "is_delinquent": bool(tax_signal["has_tax_delinquency"]),
            "total_owed": None,
            "records": [],
        },
        "flood_zone": flood,
        "soil_profile": soil,
        "structures": {
            "count": structure_count,
            "likely_vacant": likely_vacant,
            "buildings": [
                {
                    "type": r["building_type"] or "Unknown",
                    "sqm": int(r["sqm"]) if r["sqm"] else 0,
                    "sqft": int(float(r["sqm"]) * 10.764) if r["sqm"] else 0,
                }
                for r in structure_rows
            ],
        },
        "zoning": zoning,
        "development_momentum": momentum,
        "parcel_brief": brief,
        "record_brief": build_record_brief(
            momentum.get("signals") if momentum else None,
            source_updated_at=momentum.get("computed_at") if momentum else None,
        ),
        "related_narratives": narratives,
        "intelligence_summary": intelligence_summary,
        "linked_proceedings": linked_proceedings,
        "municipal_evidence": municipal_evidence,
        "source_explanation": source_explanation,
        "evidence": report_evidence,
    }
