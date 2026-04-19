"""Parcel endpoints — bbox query, property report card, delinquency overlay."""

from fastapi import APIRouter, HTTPException, Query

from api.lib.database import get_cursor
from api.lib.development_radar import build_reason_signals, compute_headline_signal
from api.lib.response_types import ParcelBboxResponse, PropertyReportResponse

router = APIRouter(tags=["parcels"])


@router.get("/bbox", response_model=None)
def parcels_bbox(
    west: float = Query(...),
    south: float = Query(...),
    east: float = Query(...),
    north: float = Query(...),
    layer: str | None = Query(default=None),
) -> ParcelBboxResponse:
    """Return parcels within a bounding box as GeoJSON.

    Optional layer=delinquent adds tax delinquency status.
    """
    with get_cursor() as cur:
        if layer == "delinquent":
            cur.execute("""
                SELECT
                    ST_AsGeoJSON(p.geom)::json AS geometry,
                    p.pidn, p.owner_full, p.propadr, p.aprtotal, p.municipality,
                    p.class, p.saledt, p.price,
                    COALESCE(tc.total_owed, 0) AS delinquent_total,
                    tc.years_delinquent
                FROM staging.parcels p
                LEFT JOIN (
                    SELECT pidn,
                           SUM(CASE WHEN total > 0 THEN total ELSE 0 END) AS total_owed,
                           COUNT(DISTINCT tax_year) AS years_delinquent
                    FROM staging.tax_claims
                    WHERE valid_to IS NULL
                    GROUP BY pidn
                ) tc ON p.pidn = tc.pidn
                WHERE p.valid_to IS NULL
                  AND p.geom IS NOT NULL
                  AND p.geom && ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)
            """, {"west": west, "south": south, "east": east, "north": north})
        elif layer == "vacant":
            # Multi-signal vacancy: no building footprint + not recently sold at high price
            # Excludes parcels with high assessed value or recent expensive sales
            # which indicate development even if footprint data is stale
            cur.execute("""
                SELECT
                    ST_AsGeoJSON(p.geom)::json AS geometry,
                    p.pidn, p.owner_full, p.propadr, p.aprtotal, p.municipality,
                    p.class, p.saledt, p.price,
                    COALESCE(tc.total_owed, 0) AS delinquent_total
                FROM staging.parcels p
                LEFT JOIN (
                    SELECT pidn, SUM(CASE WHEN total > 0 THEN total ELSE 0 END) AS total_owed
                    FROM staging.tax_claims WHERE valid_to IS NULL GROUP BY pidn
                ) tc ON p.pidn = tc.pidn
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
            """, {"west": west, "south": south, "east": east, "north": north})
        else:
            cur.execute("""
                SELECT
                    ST_AsGeoJSON(p.geom)::json AS geometry,
                    p.pidn, p.owner_full, p.propadr, p.aprtotal, p.municipality,
                    p.class, p.saledt, p.price
                FROM staging.parcels p
                WHERE p.valid_to IS NULL
                  AND p.geom IS NOT NULL
                  AND p.geom && ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)
            """, {"west": west, "south": south, "east": east, "north": north})
        rows = cur.fetchall()

    features = []
    for row in rows:
        geom = row.pop("geometry")
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {k: (float(v) if k in ("aprtotal", "price", "delinquent_total") and v is not None else v)
                           for k, v in dict(row).items()},
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/{pidn}")
def parcel_detail(pidn: str) -> PropertyReportResponse:
    """Full property report card for a single parcel."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT pidn, owner_full, own_name1, own_name2, prev_owner,
                   propadr, mail_addr_full, municipality, school_dis,
                   class, luc, acres, style, num_stories, res_living_area,
                   yrblt, heatsys, fuel, clean_green, grade, cdu,
                   aprland, aprbldg, aprtotal, saledt, price, prev_price,
                   deed_bk, deed_pg, comm_struc, comm_year_built, comm_building_sq_ft,
                   ST_Y(ST_Centroid(geom)) AS lat,
                   ST_X(ST_Centroid(geom)) AS lng
            FROM staging.parcels
            WHERE pidn = %(pidn)s AND valid_to IS NULL
        """, {"pidn": pidn})
        parcel = cur.fetchone()
        if not parcel:
            raise HTTPException(status_code=404, detail=f"Parcel not found: {pidn}")

        cur.execute("""
            SELECT tax_year, authority_name, tax_owed, penalty_owed,
                   interest_owed, fees_owed, total, owner_name, property_address
            FROM staging.tax_claims
            WHERE pidn = %(pidn)s AND valid_to IS NULL AND total > 0
            ORDER BY tax_year DESC, authority_name
        """, {"pidn": pidn})
        tax_claims = cur.fetchall()

        cur.execute("""
            SELECT fld_zone, zone_subty, sfha_tf
            FROM staging.flood_zones
            WHERE valid_to IS NULL
              AND geom IS NOT NULL
              AND ST_Intersects(geom, (
                  SELECT geom FROM staging.parcels WHERE pidn = %(pidn)s AND valid_to IS NULL
              ))
            LIMIT 1
        """, {"pidn": pidn})
        flood = cur.fetchone()

        cur.execute("""
            SELECT s.building_type,
                   ROUND(ST_Area(ST_Transform(s.geom, 32617))::numeric) AS sqm
            FROM staging.structures s
            WHERE s.valid_to IS NULL
              AND s.geom IS NOT NULL
              AND ST_Intersects(s.geom, (
                  SELECT geom FROM staging.parcels WHERE pidn = %(pidn)s AND valid_to IS NULL
              ))
            ORDER BY ST_Area(s.geom) DESC
        """, {"pidn": pidn})
        structure_rows = cur.fetchall()

        cur.execute("""
            SELECT score, opportunity_score, has_active_plan, eligible,
                   exclusion_reasons, signals, top_signal,
                   signal_count, score_version, computed_at
            FROM public.development_momentum WHERE pidn = %(pidn)s
        """, {"pidn": pidn})
        momentum_row = cur.fetchone()

        # Parcel brief (Pass 3)
        cur.execute("""
            SELECT
                brief_text,
                assessment,
                assessment_reasoning,
                key_questions,
                signal_count,
                citations,
                brief_version,
                generated_at
            FROM public.parcel_briefs
            WHERE pidn = %(pidn)s
        """, {"pidn": pidn})
        brief_row = cur.fetchone()

        # County narratives that explicitly reference this parcel (Pass 4)
        cur.execute("""
            SELECT
                narrative_id,
                title,
                body,
                narrative_type,
                trajectory,
                key_entities,
                citations,
                generated_at
            FROM public.county_narratives
            WHERE (expires_at IS NULL OR expires_at > NOW())
              AND affected_pidns IS NOT NULL
              AND %(pidn)s = ANY(affected_pidns)
            ORDER BY generated_at DESC NULLS LAST, narrative_id DESC
            LIMIT 5
        """, {"pidn": pidn})
        related_narratives = cur.fetchall()

        # Pass 2 cross-signal insight for this parcel
        cur.execute("""
            SELECT cross_signal_insight, last_run_at, signals_validated_count
            FROM meta.intelligence_passes
            WHERE pidn = %(pidn)s AND pass_number = 2 AND status = 'complete'
        """, {"pidn": pidn})
        intelligence_row = cur.fetchone()

        # Pass 0 proceeding extractions linked by PIDN or property address.
        # parcel_reference is free-text: Pass 0 writes whatever the PDF said,
        # which is usually an address, occasionally a PIDN. Match both.
        match_refs = [pidn]
        if parcel["propadr"]:
            match_refs.append(parcel["propadr"])
        cur.execute("""
            SELECT
                pe.proceeding_id,
                pp.body_name,
                pp.meeting_date,
                pp.proceeding_type,
                pe.extraction_type,
                pe.applicant_name,
                pe.decision,
                pe.current_zoning,
                pe.proposed_zoning,
                pe.supporting_text,
                pp.document_url,
                pe.extraction_confidence,
                CASE
                    WHEN pe.parcel_reference = %(pidn)s THEN 'pidn'
                    ELSE 'address'
                END AS match_type
            FROM staging.proceeding_extractions pe
            JOIN staging.public_proceedings pp ON pp.id = pe.proceeding_id
            WHERE pp.valid_to IS NULL
              AND pe.extraction_type NOT IN ('_complete', '_no_extractions')
              AND pe.parcel_reference = ANY(%(match_refs)s)
            ORDER BY pp.meeting_date DESC NULLS LAST, pe.proceeding_id DESC
            LIMIT 20
        """, {"pidn": pidn, "match_refs": match_refs})
        proceeding_rows = cur.fetchall()

    p = dict(parcel)
    for key in ("aprland", "aprbldg", "aprtotal", "price", "prev_price", "acres", "lat", "lng"):
        if p.get(key):
            p[key] = float(p[key])

    delinquent_total = sum(float(r["total"]) for r in tax_claims)

    structure_count = len(structure_rows)
    # Multi-signal vacancy: no footprint + not high-value residential
    likely_vacant = (
        structure_count == 0
        and (p.get("class") not in ("R",) or not p.get("aprtotal") or float(p.get("aprtotal") or 0) < 50000)
        and (not p.get("price") or float(p.get("price") or 0) < 100000)
    )
    momentum = dict(momentum_row) if momentum_row else None
    if momentum:
        momentum["reason_signals"] = build_reason_signals(momentum.get("signals"))
        momentum["top_signal"] = compute_headline_signal(
            momentum.get("signals"),
            fallback=momentum.get("top_signal"),
        )

    brief = dict(brief_row) if brief_row else None
    if brief:
        brief["key_questions"] = brief.get("key_questions") or []
        brief["citations"] = brief.get("citations") or []

    narratives = [dict(row) for row in related_narratives]
    for narrative in narratives:
        narrative["key_entities"] = narrative.get("key_entities") or []
        narrative["citations"] = narrative.get("citations") or []

    intelligence_summary = dict(intelligence_row) if intelligence_row else None

    linked_proceedings = []
    for row in proceeding_rows:
        record = dict(row)
        if record.get("extraction_confidence") is not None:
            record["extraction_confidence"] = float(record["extraction_confidence"])
        linked_proceedings.append(record)

    return {
        "parcel": p,
        "tax_delinquency": {
            "is_delinquent": len(tax_claims) > 0,
            "total_owed": delinquent_total,
            "records": [dict(r) for r in tax_claims],
        },
        "flood_zone": {
            "in_flood_zone": flood is not None,
            "zone": flood["fld_zone"] if flood else None,
            "sfha": flood["sfha_tf"] == "T" if flood else False,
        },
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
        "development_momentum": momentum,
        "parcel_brief": brief,
        "related_narratives": narratives,
        "intelligence_summary": intelligence_summary,
        "linked_proceedings": linked_proceedings,
    }
