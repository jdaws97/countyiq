"""Enrichment: spatial-join radar overlay layers to parcels.

Emits parcel-linked signal evidence rows into public.development_signals.
Each signal type is a separate INSERT query. Full refresh each run.

RULES:
  - One row per (pidn, signal_key) — DISTINCT ON for all proximity/spatial joins
  - Proximity: 250m for subdivision plans, 800m for PennDOT/CDBG
  - Exclude nominal transfers (price <= $1,000)
  - Growth area: PGA/SGA only, low weight (tiebreaker, not differentiator)
  - Zoning mismatch: actual zoning (staging.zoning) vs future land use
  - Opportunity score should be anchored by direct parcel signals, not overlays
  - Flood zone: negative weight (discount, not exclude)
"""

from dagster import (
    asset,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.resources.database import DatabaseResource

_SIGNALS: list[tuple[str, str]] = [
    # ── HIGH-VALUE DIRECT SIGNALS ──────────────────────────────────────

    # 1. active_subdivision — closest plan within 250m, last 3 years
    (
        "active_subdivision",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'active_subdivision', 0.30,
            'staging.planning_subdivisions', s.sequ_num,
            ST_Distance(ST_Centroid(p.geom)::geography, s.geom::geography),
            jsonb_build_object(
                'plan_title', s.plan_title, 'date_rcvd', s.date_rcvd,
                'pt_subdiv', s.pt_subdiv, 'pt_land_dev', s.pt_land_dev,
                'total_acres', s.total_acres, 'prop_lots', s.prop_lots, 'prop_du', s.prop_du
            )
        FROM staging.parcels p
        JOIN staging.planning_subdivisions s
            ON ST_DWithin(ST_Centroid(p.geom)::geography, s.geom::geography, 250)
        WHERE p.valid_to IS NULL AND s.valid_to IS NULL
          AND s.date_rcvd >= NOW() - INTERVAL '3 years'
        ORDER BY p.pidn, ST_Distance(ST_Centroid(p.geom)::geography, s.geom::geography)
        """,
    ),
    # 2. ecodev_candidate — YCPC flagged underutilized (PIDN join)
    (
        "ecodev_candidate",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT p.pidn, 'ecodev_candidate', 0.25,
            'staging.ecodev_candidates', e.pidn, NULL,
            jsonb_build_object(
                'percent_underutilized', e.percent_underutilized,
                'buildable_acres', e.buildable_acres,
                'sewer_water_availability', e.sewer_water_availability,
                'lev_suitability', e.lev_suitability
            )
        FROM staging.parcels p
        JOIN staging.ecodev_candidates e ON e.pidn = p.pidn AND e.valid_to IS NULL
        WHERE p.valid_to IS NULL
        """,
    ),

    # ── MEDIUM-VALUE CONTEXT SIGNALS ───────────────────────────────────

    # 3. zoning_mismatch — actual zoning vs future land use
    (
        "zoning_mismatch",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'zoning_mismatch', 0.10,
            'staging.future_landuse', f.globalid, NULL,
            jsonb_build_object(
                'current_ztype', z.ztype, 'current_zname', z.zname,
                'future_lu', f.future_lu, 'general_lu', f.general_lu
            )
        FROM staging.parcels p
        JOIN staging.zoning z
            ON ST_Intersects(ST_Centroid(p.geom), z.geom) AND z.valid_to IS NULL
        JOIN staging.future_landuse f
            ON ST_Intersects(ST_Centroid(p.geom), f.geom) AND f.valid_to IS NULL
        WHERE p.valid_to IS NULL
          AND f.future_lu IS NOT NULL AND f.future_lu != 'NO FUTURE LANDUSE'
          AND (
              (z.ztype = 'R' AND f.general_lu NOT ILIKE '%%resident%%')
              OR (z.ztype = 'C' AND f.general_lu NOT ILIKE '%%commerc%%')
              OR (z.ztype = 'A' AND f.general_lu NOT ILIKE '%%agri%%')
              OR (z.ztype = 'I' AND f.general_lu NOT ILIKE '%%industr%%')
              OR (z.ztype = 'M' AND f.general_lu NOT ILIKE '%%industr%%' AND f.general_lu NOT ILIKE '%%manufactur%%')
          )
          -- Exclude false mismatches where zoning name matches future use
          AND LOWER(REPLACE(z.zname, ' ', '')) != LOWER(REPLACE(f.future_lu, ' ', ''))
          AND f.future_lu NOT ILIKE '%%' || z.zname || '%%'
          AND z.zname NOT ILIKE '%%' || f.future_lu || '%%'
        ORDER BY p.pidn
        """,
    ),
    # 4. ownership_change — real market sale > $1,000 in last 12 months
    (
        "ownership_change",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT p.pidn, 'ownership_change', 0.10,
            'staging.parcels', p.pidn, NULL,
            jsonb_build_object(
                'saledt', p.saledt, 'price', p.price, 'prev_owner', p.prev_owner,
                'buyer_is_llc', (p.owner_full ILIKE '%%LLC%%' OR p.owner_full ILIKE '%%LP%%'
                    OR p.owner_full ILIKE '%%HOLDINGS%%' OR p.owner_full ILIKE '%%ASSOCIATES%%'
                    OR p.owner_full ILIKE '%%PARTNERS%%')
            )
        FROM staging.parcels p
        WHERE p.valid_to IS NULL
          AND p.saledt IS NOT NULL AND p.saledt != ''
          AND to_date(p.saledt, 'DD-MON-YYYY') >= NOW() - INTERVAL '12 months'
          AND COALESCE(p.price::numeric, 0) > 1000
        """,
    ),
    # 5. vacancy — no structures + not high-value residential + no recent high-dollar sale
    (
        "vacancy",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT p.pidn, 'vacancy', 0.12,
            'staging.structures', p.pidn, NULL,
            jsonb_build_object(
                'structure_count', 0,
                'class', p.class,
                'aprtotal', p.aprtotal,
                'price', p.price
            )
        FROM staging.parcels p
        WHERE p.valid_to IS NULL
          AND p.geom IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM staging.structures s
              WHERE s.valid_to IS NULL
                AND s.geom IS NOT NULL
                AND ST_Intersects(s.geom, p.geom)
          )
          AND (p.class NOT IN ('R') OR p.aprtotal IS NULL OR p.aprtotal::numeric < 50000)
          AND (p.price IS NULL OR p.price::numeric < 100000)
        """,
    ),
    # 6. tax_distress — active tax delinquency (redevelopment signal)
    (
        "tax_distress",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT
            agg.pidn, 'tax_distress', 0.10,
            'staging.tax_claims', agg.pidn, NULL,
            jsonb_build_object(
                'total_owed', agg.total_owed,
                'years_delinquent', agg.years_delinquent,
                'oldest_year', agg.oldest_year
            )
        FROM (
            SELECT tc.pidn,
                   SUM(tc.total) AS total_owed,
                   COUNT(DISTINCT tc.tax_year) AS years_delinquent,
                   MIN(tc.tax_year) AS oldest_year
            FROM staging.tax_claims tc
            JOIN staging.parcels p ON p.pidn = tc.pidn AND p.valid_to IS NULL
            WHERE tc.valid_to IS NULL
            GROUP BY tc.pidn
            HAVING SUM(tc.total) > 0
        ) agg
        """,
    ),
    # 7. assemblage — touches many differently owned parcels
    (
        "assemblage",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT
            p.pidn,
            'assemblage',
            CASE
                WHEN COUNT(DISTINCT NULLIF(TRIM(n.owner_full), '')) FILTER (
                    WHERE COALESCE(NULLIF(TRIM(n.owner_full), ''), '__blank__')
                          <> COALESCE(NULLIF(TRIM(p.owner_full), ''), '__blank__')
                ) >= 8 THEN 0.10
                ELSE 0.06
            END,
            'staging.parcels',
            p.pidn,
            NULL,
            jsonb_build_object(
                'different_owner_neighbors',
                COUNT(DISTINCT NULLIF(TRIM(n.owner_full), '')) FILTER (
                    WHERE COALESCE(NULLIF(TRIM(n.owner_full), ''), '__blank__')
                          <> COALESCE(NULLIF(TRIM(p.owner_full), ''), '__blank__')
                ),
                'neighbor_parcels',
                COUNT(DISTINCT n.pidn) FILTER (
                    WHERE COALESCE(NULLIF(TRIM(n.owner_full), ''), '__blank__')
                          <> COALESCE(NULLIF(TRIM(p.owner_full), ''), '__blank__')
                )
            )
        FROM staging.parcels p
        JOIN staging.parcels n
            ON p.valid_to IS NULL
           AND n.valid_to IS NULL
           AND p.geom IS NOT NULL
           AND n.geom IS NOT NULL
           AND p.pidn <> n.pidn
           AND ST_Touches(p.geom, n.geom)
        WHERE p.valid_to IS NULL
        GROUP BY p.pidn, p.owner_full
        HAVING COUNT(DISTINCT NULLIF(TRIM(n.owner_full), '')) FILTER (
            WHERE COALESCE(NULLIF(TRIM(n.owner_full), ''), '__blank__')
                  <> COALESCE(NULLIF(TRIM(p.owner_full), ''), '__blank__')
        ) >= 6
        """,
    ),

    # ── LOW-VALUE PROXIMITY / CONTEXT SIGNALS ──────────────────────────

    # 8. penndot_project — closest within 800m
    #    Evidence includes full project metadata so Pass 2 LLM can assess
    #    currency (active vs completed), scale (cost), and impact window.
    (
        "penndot_project",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'penndot_project', 0.03,
            'staging.penndot_projects', pp.project_id,
            ST_Distance(ST_Centroid(p.geom)::geography, pp.geom::geography),
            jsonb_build_object(
                'project_name', pp.project_name,
                'project_id', pp.project_id,
                'description', LEFT(COALESCE(pp.description, ''), 300),
                'status', pp.status,
                'project_type', pp.project_type,
                'start_date', pp.start_date,
                'end_date', pp.end_date,
                'cost', pp.cost,
                'municipality', pp.municipality,
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        JOIN staging.penndot_projects pp
            ON ST_DWithin(ST_Centroid(p.geom)::geography, pp.geom::geography, 800)
        WHERE p.valid_to IS NULL AND pp.valid_to IS NULL
        ORDER BY p.pidn, ST_Distance(ST_Centroid(p.geom)::geography, pp.geom::geography)
        """,
    ),
    # 9. cdbg_investment — closest within 800m
    #    Evidence includes construction type, unit count, affordability tier,
    #    and occupancy date so Pass 2 can assess investment scale and currency.
    (
        "cdbg_investment",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'cdbg_investment', 0.03,
            'staging.cdbg_housing', c.housingdevid,
            ST_Distance(ST_Centroid(p.geom)::geography, c.geom::geography),
            jsonb_build_object(
                'name', c.name,
                'address', c.address,
                'housing_dev_id', c.housingdevid,
                'project_id', c.prj_id,
                'construction_type', c.constructi,
                'units', c.units,
                'occupancy_date', c.date_of_oc,
                'affordability', c.affordabil,
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        JOIN staging.cdbg_housing c
            ON ST_DWithin(ST_Centroid(p.geom)::geography, c.geom::geography, 800)
        WHERE p.valid_to IS NULL AND c.valid_to IS NULL
        ORDER BY p.pidn, ST_Distance(ST_Centroid(p.geom)::geography, c.geom::geography)
        """,
    ),
    # 10. growth_area — PGA/SGA only, LOW WEIGHT (tiebreaker, not differentiator)
    (
        "growth_area",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'growth_area', 0.02,
            'staging.growth_areas', g.globalid, NULL,
            jsonb_build_object('ga_type', g.ga_type, 'ga_status', g.ga_status)
        FROM staging.parcels p
        JOIN staging.growth_areas g
            ON ST_Intersects(ST_Centroid(p.geom), g.geom)
        WHERE p.valid_to IS NULL AND g.valid_to IS NULL
          AND g.ga_type IN ('PGA', 'SGA')
        ORDER BY p.pidn, g.ga_type
        """,
    ),

    # ── NEGATIVE / EXCLUSION SIGNALS ───────────────────────────────────

    # 11. flood_zone — SFHA flood zone (discount, not hard exclude)
    (
        "flood_zone",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'flood_zone', -0.10,
            'staging.flood_zones', f.fld_ar_id, NULL,
            jsonb_build_object('fld_zone', f.fld_zone, 'zone_subty', f.zone_subty, 'sfha_tf', f.sfha_tf)
        FROM staging.parcels p
        JOIN staging.flood_zones f
            ON ST_Intersects(ST_Centroid(p.geom), f.geom)
        WHERE p.valid_to IS NULL AND f.valid_to IS NULL AND f.sfha_tf = 'T'
        ORDER BY p.pidn
        """,
    ),
    # 12. conservation_easement — hard exclude
    #    Evidence includes preservation date, current owner, exclusion/federal
    #    flags, and district so Pass 2 can assess enforceability and scope.
    (
        "conservation_easement",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'conservation_easement', 0.00,
            'staging.conservation_easements', ce.ease_id, NULL,
            jsonb_build_object(
                'ease_id', ce.ease_id,
                'ease_code', ce.ease_code,
                'ease_acres', ce.ease_acres,
                'grantor', ce.grantor,
                'current_owner', ce.curr_owner,
                'preservation_date', ce.pres_date,
                'exclusion_flag', ce.exclusion,
                'federal_flag', ce.federal,
                'district', ce.district,
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        JOIN staging.conservation_easements ce ON ce.pidn = p.pidn AND ce.valid_to IS NULL
        WHERE p.valid_to IS NULL
        ORDER BY p.pidn
        """,
    ),
    # 13. ag_security — hard exclude
    #    Evidence includes resolution ID, book/page, last review date, and
    #    status flag so Pass 2 can assess staleness (enrollments expire and
    #    must be renewed — last_review date is critical for currency).
    (
        "ag_security",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'ag_security', 0.00,
            'staging.ag_security', ag.resolution, NULL,
            jsonb_build_object(
                'resolution', ag.resolution,
                'res_acres', ag.res_acres,
                'res_date', ag.res_date,
                'last_review', ag.last_review,
                'book', ag.book,
                'page', ag.page,
                'instrument', ag.instrument,
                'flag', ag.flag,
                'district', ag.district,
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        JOIN staging.ag_security ag ON ag.pidn = p.pidn AND ag.valid_to IS NULL
        WHERE p.valid_to IS NULL
        ORDER BY p.pidn
        """,
    ),
]


@asset(
    group_name="enrichment",
    deps=[
        "planning_subdivisions_arcgis",
        "ecodev_candidates_arcgis",
        "growth_areas_arcgis",
        "future_landuse_arcgis",
        "conservation_easements_arcgis",
        "ag_security_arcgis",
        "cdbg_housing_arcgis",
        "parcels_arcgis",
        "penndot_projects_arcgis",
        "structures_arcgis",
        "zoning_arcgis",
    ],
    description="Spatial-join radar layers to parcels \u2192 public.development_signals",
    kinds={"postgres"},
)
def development_signals(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    """Truncate and rebuild public.development_signals."""

    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    signal_counts: dict[str, int] = {}
    total = 0

    try:
        cur.execute("TRUNCATE public.development_signals RESTART IDENTITY")
        context.log.info("Truncated public.development_signals")

        for signal_key, sql in _SIGNALS:
            cur.execute(sql)
            count = cur.rowcount
            signal_counts[signal_key] = count
            total += count
            context.log.info(f"  {signal_key}: {count:,} rows")

        conn.commit()
        context.log.info(f"Committed {total:,} total signal rows")

    except Exception:
        conn.rollback()
        raise
    finally:
        if was_autocommit:
            conn.autocommit = True
        cur.close()

    metadata = {"total_signal_rows": MetadataValue.int(total)}
    for key, count in signal_counts.items():
        metadata[key] = MetadataValue.int(count)
    return MaterializeResult(metadata=metadata)
