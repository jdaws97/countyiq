"""Parcel endpoints — bbox query, property report card, delinquency overlay."""

from fastapi import APIRouter, HTTPException, Query

from api.lib.database import get_cursor
from api.lib.development_radar import (
    build_reason_signals,
    compute_headline_signal,
    sanitize_signals_for_public,
)
from api.lib.response_types import ParcelBboxResponse, PropertyReportResponse
from api.lib.serialization import serialize_temporal_fields
from api.lib.settings import open_data_source_key
from api.lib.source_policy import (
    PUBLIC_ORGANIZATION_TYPES,
    require_source_use,
    source_use_allowed,
)

router = APIRouter(tags=["parcels"])

_PUBLIC_OWNER_NAME_SQL = """
CASE
    WHEN %(show_people)s OR EXISTS (
        SELECT 1
        FROM public.owner_source_links osl
        JOIN public.owners owner_entity ON owner_entity.owner_id = osl.owner_id
        WHERE osl.source_type = 'parcel'
          AND osl.source_id = p.pidn
          AND lower(COALESCE(owner_entity.entity_type, '')) = ANY(%(organization_types)s)
    ) THEN p.owner_full
    ELSE NULL
END
"""


@router.get("/bbox", response_model=None)
def parcels_bbox(
    west: float = Query(..., ge=-180, le=180),
    south: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180),
    north: float = Query(..., ge=-90, le=90),
    layer: str | None = Query(default=None),
) -> ParcelBboxResponse:
    """Return parcels within a bounding box as GeoJSON.

    Optional layer=delinquent adds a derived tax-delinquency signal.
    """
    with get_cursor() as cur:
        parcel_source = open_data_source_key()
        require_source_use(cur, parcel_source, "derived_product", conceal=False)
        show_people = source_use_allowed(
            cur, parcel_source, "person_level_display"
        )
        bbox_params = {
            "west": west,
            "south": south,
            "east": east,
            "north": north,
            "show_people": show_people,
            "organization_types": list(PUBLIC_ORGANIZATION_TYPES),
        }
        if layer == "delinquent":
            require_source_use(cur, "tax_claims", "derived_product", conceal=False)
            cur.execute(f"""
                SELECT
                    ST_AsGeoJSON(p.geom)::json AS geometry,
                    p.pidn,
                    {_PUBLIC_OWNER_NAME_SQL} AS owner_full,
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
            """, bbox_params)
        elif layer in {"vacant", "vacant_delinquent"}:
            tax_signal_sql = "NULL::boolean"
            if layer == "vacant_delinquent":
                require_source_use(
                    cur, "tax_claims", "derived_product", conceal=False
                )
                tax_signal_sql = (
                    "EXISTS (SELECT 1 FROM staging.tax_claims tc "
                    "WHERE tc.valid_to IS NULL AND tc.total > 0 "
                    "AND tc.pidn = p.pidn)"
                )
            # Multi-signal vacancy: no building footprint + not recently sold at high price
            # Excludes parcels with high assessed value or recent expensive sales
            # which indicate development even if footprint data is stale
            cur.execute(f"""
                SELECT
                    ST_AsGeoJSON(p.geom)::json AS geometry,
                    p.pidn,
                    {_PUBLIC_OWNER_NAME_SQL} AS owner_full,
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
            """, bbox_params)
        else:
            cur.execute(f"""
                SELECT
                    ST_AsGeoJSON(p.geom)::json AS geometry,
                    p.pidn,
                    {_PUBLIC_OWNER_NAME_SQL} AS owner_full,
                    p.propadr, p.aprtotal, p.municipality,
                    p.class, p.saledt, p.price
                FROM staging.parcels p
                WHERE p.valid_to IS NULL
                  AND p.geom IS NOT NULL
                  AND p.geom && ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)
            """, bbox_params)
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
    `changed_at` is the current row's valid_from, so a recent value means the
    parcel's tracked fields changed in a recent pipeline run.
    """
    pidn_list = [p.strip() for p in pidns.split(",") if p.strip()][:100]
    if not pidn_list:
        return {"parcels": []}

    with get_cursor() as cur:
        parcel_source = open_data_source_key()
        require_source_use(cur, parcel_source, "derived_product", conceal=False)
        require_source_use(cur, "tax_claims", "derived_product", conceal=False)
        show_people = source_use_allowed(
            cur, parcel_source, "person_level_display"
        )
        cur.execute(
            f"""
            SELECT
                p.pidn,
                {_PUBLIC_OWNER_NAME_SQL} AS owner_full,
                p.propadr, p.municipality,
                p.aprtotal, p.class, p.acres,
                p.valid_from AS changed_at,
                (p.valid_from >= NOW() - INTERVAL '30 days') AS changed_recently,
                EXISTS (
                    SELECT 1 FROM staging.tax_claims tc
                    WHERE tc.valid_to IS NULL AND tc.total > 0 AND tc.pidn = p.pidn
                ) AS has_tax_delinquency,
                dm.score AS momentum_score,
                dm.site_readiness_score,
                dm.top_signal
            FROM staging.parcels p
            LEFT JOIN public.development_momentum dm ON dm.pidn = p.pidn
            WHERE p.valid_to IS NULL AND p.pidn = ANY(%(pidns)s)
            ORDER BY p.valid_from DESC
            """,
            {
                "pidns": pidn_list,
                "show_people": show_people,
                "organization_types": list(PUBLIC_ORGANIZATION_TYPES),
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


@router.get("/{pidn}")
def parcel_detail(pidn: str) -> PropertyReportResponse:
    """Full property report card for a single parcel."""
    with get_cursor() as cur:
        parcel_source = open_data_source_key()
        require_source_use(cur, parcel_source, "derived_product", conceal=False)
        require_source_use(cur, "tax_claims", "derived_product", conceal=False)
        require_source_use(cur, "public_proceedings", "derived_product", conceal=False)
        show_people = source_use_allowed(
            cur, parcel_source, "person_level_display"
        )
        show_proceeding_people = source_use_allowed(
            cur, "public_proceedings", "person_level_display"
        )
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

        show_owner = show_people
        if not show_owner:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM public.owner_source_links osl
                    JOIN public.owners owner_entity
                      ON owner_entity.owner_id = osl.owner_id
                    WHERE osl.source_type = 'parcel'
                      AND osl.source_id = %(pidn)s
                      AND lower(COALESCE(owner_entity.entity_type, ''))
                          = ANY(%(organization_types)s)
                ) AS allowed
                """,
                {
                    "pidn": pidn,
                    "organization_types": list(PUBLIC_ORGANIZATION_TYPES),
                },
            )
            show_owner = bool((cur.fetchone() or {}).get("allowed"))

        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM staging.tax_claims
                WHERE pidn = %(pidn)s AND valid_to IS NULL AND total > 0
            ) AS has_tax_delinquency
        """, {"pidn": pidn})
        tax_signal = cur.fetchone() or {"has_tax_delinquency": False}

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
            SELECT score, opportunity_score, site_readiness_score,
                   has_active_plan, eligible,
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
                CASE WHEN %(show_people)s THEN pe.applicant_name ELSE NULL END
                    AS applicant_name,
                pe.decision,
                pe.current_zoning,
                pe.proposed_zoning,
                CASE WHEN %(show_people)s THEN LEFT(pe.supporting_text, 280)
                     ELSE NULL END AS supporting_text,
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
        """, {
            "pidn": pidn,
            "match_refs": match_refs,
            "show_people": show_proceeding_people,
        })
        proceeding_rows = cur.fetchall()

    p = dict(parcel)
    if not show_owner:
        for key in (
            "owner_full",
            "own_name1",
            "own_name2",
            "prev_owner",
            "mail_addr_full",
        ):
            p[key] = None
    for key in ("aprland", "aprbldg", "aprtotal", "price", "prev_price", "acres", "lat", "lng"):
        if p.get(key):
            p[key] = float(p[key])

    structure_count = len(structure_rows)
    # Multi-signal vacancy: no footprint + not high-value residential
    likely_vacant = (
        structure_count == 0
        and (p.get("class") not in ("R",) or not p.get("aprtotal") or float(p.get("aprtotal") or 0) < 50000)
        and (not p.get("price") or float(p.get("price") or 0) < 100000)
    )
    momentum = dict(momentum_row) if momentum_row else None
    if momentum:
        momentum["signals"] = sanitize_signals_for_public(
            momentum.get("signals"),
            allow_people=show_people,
        )
        momentum["reason_signals"] = build_reason_signals(momentum.get("signals"))
        momentum["top_signal"] = compute_headline_signal(
            momentum.get("signals"),
            fallback=momentum.get("top_signal"),
        )
        serialize_temporal_fields(momentum, "computed_at")

    # Existing LLM prose was not generated under a person-name redaction
    # contract. Keep it backend-only until the governing source permits
    # person-level display or public-safe briefs are regenerated.
    brief = dict(brief_row) if brief_row and show_people else None
    if brief:
        brief["key_questions"] = brief.get("key_questions") or []
        brief["citations"] = brief.get("citations") or []
        serialize_temporal_fields(brief, "generated_at")

    narratives = (
        [dict(row) for row in related_narratives]
        if show_owner and show_proceeding_people
        else []
    )
    for narrative in narratives:
        narrative["key_entities"] = narrative.get("key_entities") or []
        narrative["citations"] = narrative.get("citations") or []
        serialize_temporal_fields(narrative, "generated_at")

    intelligence_summary = (
        dict(intelligence_row) if intelligence_row and show_people else None
    )
    if intelligence_summary:
        serialize_temporal_fields(intelligence_summary, "last_run_at")

    linked_proceedings = []
    for row in proceeding_rows:
        record = dict(row)
        if record.get("extraction_confidence") is not None:
            record["extraction_confidence"] = float(record["extraction_confidence"])
        serialize_temporal_fields(record, "meeting_date")
        linked_proceedings.append(record)

    return {
        "parcel": p,
        "tax_delinquency": {
            "detail_available": False,
            "is_delinquent": bool(tax_signal["has_tax_delinquency"]),
            "total_owed": None,
            "records": [],
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
