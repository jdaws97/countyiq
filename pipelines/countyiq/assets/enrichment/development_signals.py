"""Enrichment: spatial-join radar overlay layers to parcels.

Emits parcel-linked signal evidence rows into public.development_signals.
Each signal type is a separate INSERT query. Full refresh each run.

RULES:
  - One row per (pidn, signal_key) — DISTINCT ON for all proximity/spatial joins
  - Proximity radii, price cutoffs, and neighbor thresholds live in
    county_config.py (signal_* fields) and are bound as query parameters
  - Exclude nominal transfers (price <= signal_nominal_sale_max)
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

from countyiq.lib.county_config import county_open_data_source_key, get_county_config
from countyiq.lib.source_rights import authorize_source_uses, source_use_is_authorized
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
                'total_acres', s.total_acres, 'prop_lots', s.prop_lots, 'prop_du', s.prop_du,
                'source_url', s.source_url,
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        JOIN staging.planning_subdivisions s
            ON ST_DWithin(ST_Centroid(p.geom)::geography, s.geom::geography, %(subdivision_radius_m)s)
        WHERE p.valid_to IS NULL AND s.valid_to IS NULL
          AND s.date_rcvd >= NOW() - INTERVAL '3 years'
          -- Believability filter (see the hybrid-LLM decision in docs/decisions.md):
          -- plans with prop_du=0 AND pt_land_dev=NO were 20,773 of the raw
          -- signals and 0%% were ever confirmed — the LLM downgraded every
          -- one with identical reasoning. Filter at the source instead of
          -- paying Pass 2 to rediscover it per parcel.
          AND (COALESCE(s.prop_du, 0) > 0
               OR UPPER(COALESCE(s.pt_land_dev, 'NO')) = 'YES')
        ORDER BY p.pidn, ST_Distance(ST_Centroid(p.geom)::geography, s.geom::geography)
        """,
    ),
    # 2. economic_development_park — official open-data park designation
    (
        "economic_development_park",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT
            p.pidn,
            'economic_development_park',
            CASE WHEN BOOL_OR(ep.park_type = 'industrial') THEN 0.18 ELSE 0.15 END,
            'staging.economic_development_parks',
            STRING_AGG(DISTINCT ep.park_type || ':' || ep.source_objectid, ','),
            NULL,
            jsonb_build_object(
                'park_types', jsonb_agg(DISTINCT ep.park_type),
                'park_names', jsonb_agg(DISTINCT ep.name) FILTER (WHERE ep.name IS NOT NULL),
                'source_url', MIN(ep.source_url),
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        JOIN staging.economic_development_parks ep
            ON ep.pidn = p.pidn AND ep.valid_to IS NULL
        WHERE p.valid_to IS NULL
        GROUP BY p.pidn
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
                'future_lu', f.future_lu, 'general_lu', f.general_lu,
                'evidence_captured_at', NOW()
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
                    OR p.owner_full ILIKE '%%PARTNERS%%'),
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        WHERE p.valid_to IS NULL
          -- Format guard: a single malformed county date must not abort the
          -- whole rebuild (all 13 inserts share one transaction).
          AND p.saledt ~* '^\\d{1,2}-[a-z]{3}-\\d{4}$'
          AND to_date(p.saledt, 'DD-MON-YYYY') >= NOW() - INTERVAL '12 months'
          AND COALESCE(p.price::numeric, 0) > %(nominal_sale_max)s
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
                'price', p.price,
                'evidence_captured_at', NOW()
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
          AND (p.class NOT IN ('R') OR p.aprtotal IS NULL OR p.aprtotal::numeric < %(vacancy_apr_max)s)
          AND (p.price IS NULL OR p.price::numeric < %(vacancy_price_max)s)
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
                'oldest_year', agg.oldest_year,
                'evidence_captured_at', NOW()
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
                ) >= %(assemblage_strong_neighbors)s THEN 0.10
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
                ),
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        JOIN staging.parcels n
            ON p.valid_to IS NULL
           AND n.valid_to IS NULL
           AND p.geom IS NOT NULL
           AND n.geom IS NOT NULL
           AND p.pidn <> n.pidn
           -- ST_Intersects, not ST_Touches: county parcel polygons often
           -- overlap slightly, which makes interiors intersect and silently
           -- fails the strict touch test.
           AND ST_Intersects(p.geom, n.geom)
        WHERE p.valid_to IS NULL
        GROUP BY p.pidn, p.owner_full
        HAVING COUNT(DISTINCT NULLIF(TRIM(n.owner_full), '')) FILTER (
            WHERE COALESCE(NULLIF(TRIM(n.owner_full), ''), '__blank__')
                  <> COALESCE(NULLIF(TRIM(p.owner_full), ''), '__blank__')
        ) >= %(assemblage_min_neighbors)s
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
                'source_url', pp.source_url,
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        JOIN staging.penndot_projects pp
            ON ST_DWithin(ST_Centroid(p.geom)::geography, pp.geom::geography, %(infrastructure_radius_m)s)
        WHERE p.valid_to IS NULL AND pp.valid_to IS NULL
        ORDER BY p.pidn, ST_Distance(ST_Centroid(p.geom)::geography, pp.geom::geography)
        """,
    ),
    # 9. development_overlay — parcel is inside an expressly development-focused overlay
    (
        "development_overlay",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'development_overlay', 0.04,
            'staging.zoning_overlays', zo.globalid, NULL,
            jsonb_build_object(
                'overlay_type', zo.overlay_type,
                'overlay_name', zo.overlay_name,
                'description', zo.description,
                'municipality', zo.municipality,
                'source_url', zo.source_url,
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        JOIN staging.zoning_overlays zo
            ON ST_Intersects(ST_Centroid(p.geom), zo.geom)
        WHERE p.valid_to IS NULL
          AND zo.valid_to IS NULL
          AND zo.overlay_type = 'DEVELOPMENT'
        ORDER BY p.pidn, zo.overlay_name
        """,
    ),
    # 10. local_traffic_activity — recent motor-vehicle observation near the parcel
    (
        "local_traffic_activity",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn,
            'local_traffic_activity',
            CASE WHEN ltc.volume >= 10000 THEN 0.04
                 WHEN ltc.volume >= 3000 THEN 0.02
                 ELSE 0.01 END,
            'staging.local_traffic_counts', ltc.globalid,
            ST_Distance(ST_Centroid(p.geom)::geography, ltc.geom::geography),
            jsonb_build_object(
                'counter_id', ltc.counter_id,
                'count_type', ltc.count_type,
                'purpose', ltc.purpose,
                'volume', ltc.volume,
                'count_year', ltc.count_year,
                'source_url', ltc.source_url,
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        JOIN staging.local_traffic_counts ltc
            ON ST_DWithin(
                ST_Centroid(p.geom)::geography,
                ltc.geom::geography,
                %(local_traffic_radius_m)s
            )
        WHERE p.valid_to IS NULL
          AND ltc.valid_to IS NULL
          AND ltc.volume > 0
          AND ltc.count_year >= EXTRACT(YEAR FROM NOW())::int - 5
          AND ltc.purpose IN ('HPMS', 'FUNCTIONAL CLASS', 'I-83 TAC REPORT', 'T & E STUDY', 'SPECIAL STUDY')
        ORDER BY
            p.pidn,
            ltc.count_year DESC,
            ST_Distance(ST_Centroid(p.geom)::geography, ltc.geom::geography)
        """,
    ),
    # 11. growth_area — PGA/SGA only, LOW WEIGHT (tiebreaker, not differentiator)
    (
        "growth_area",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'growth_area', 0.02,
            'staging.growth_areas', g.globalid, NULL,
            jsonb_build_object('ga_type', g.ga_type, 'ga_status', g.ga_status,
                               'source_url', g.source_url,
                               'evidence_captured_at', NOW())
        FROM staging.parcels p
        JOIN staging.growth_areas g
            ON ST_Intersects(ST_Centroid(p.geom), g.geom)
        WHERE p.valid_to IS NULL AND g.valid_to IS NULL
          AND g.ga_type IN ('PGA', 'SGA')
        ORDER BY p.pidn, g.ga_type
        """,
    ),

    # ── NEGATIVE / EXCLUSION SIGNALS ───────────────────────────────────

    # 12. soil_constraint — clearly adverse drainage, slope, or runoff profile
    (
        "soil_constraint",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'soil_constraint', -0.08,
            'staging.soils', s.objectid::text, NULL,
            jsonb_build_object(
                'map_unit_symbol', s.map_unit_symbol,
                'map_unit_name', s.map_unit_name,
                'drainage', s.drainage,
                'septic_rating', s.septic_rating,
                'representative_slope', s.representative_slope,
                'slope_high', s.slope_high,
                'hydric_rating', s.hydric_rating,
                'hydrologic_group', s.hydrologic_group,
                'source_url', s.source_url,
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        JOIN staging.soils s
            ON ST_Intersects(ST_Centroid(p.geom), s.geom)
        WHERE p.valid_to IS NULL
          AND s.valid_to IS NULL
          AND (
              COALESCE(s.representative_slope, 0) >= 15
              OR s.drainage IN ('Poorly drained', 'Somewhat poorly drained')
              OR s.hydrologic_group = 'D'
          )
        ORDER BY
            p.pidn,
            COALESCE(s.representative_slope, 0) DESC,
            CASE WHEN s.drainage = 'Poorly drained' THEN 0 ELSE 1 END
        """,
    ),
    # 13. zoning_constraint — special-purpose overlay requiring extra diligence
    (
        "zoning_constraint",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn,
            'zoning_constraint',
            CASE WHEN zo.overlay_type IN ('STEEP SLOPES', 'UNDERGROUND MINING')
                 THEN -0.08 ELSE -0.05 END,
            'staging.zoning_overlays', zo.globalid, NULL,
            jsonb_build_object(
                'overlay_type', zo.overlay_type,
                'overlay_name', zo.overlay_name,
                'description', zo.description,
                'municipality', zo.municipality,
                'source_url', zo.source_url,
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        JOIN staging.zoning_overlays zo
            ON ST_Intersects(ST_Centroid(p.geom), zo.geom)
        WHERE p.valid_to IS NULL
          AND zo.valid_to IS NULL
          AND zo.overlay_type IN (
              'AIRPORT', 'HISTORIC', 'STEEP SLOPES',
              'UNDERGROUND MINING', 'WELLHEAD'
          )
        ORDER BY
            p.pidn,
            CASE WHEN zo.overlay_type IN ('STEEP SLOPES', 'UNDERGROUND MINING')
                 THEN 0 ELSE 1 END,
            zo.overlay_name
        """,
    ),
    # 14. environmental_diligence — a nearby public DEP record that warrants
    #     follow-up. This is screening evidence, never a contamination claim.
    (
        "environmental_diligence",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'environmental_diligence', -0.05,
            'staging.environmental_diligence_sites',
            eds.source_layer || ':' || eds.source_id,
            ST_Distance(ST_Centroid(p.geom)::geography, eds.geom::geography),
            jsonb_build_object(
                'screening_only', TRUE,
                'source_layer', eds.source_layer,
                'site_name', eds.site_name,
                'facility_type', eds.facility_type,
                'facility_status', eds.facility_status,
                'detail_url', eds.detail_url,
                'source_url', eds.source_url,
                'evidence_captured_at', NOW()
            )
        FROM staging.parcels p
        JOIN staging.environmental_diligence_sites eds
            ON ST_DWithin(
                ST_Centroid(p.geom)::geography,
                eds.geom::geography,
                %(environmental_radius_m)s
            )
        WHERE p.valid_to IS NULL AND eds.valid_to IS NULL
        ORDER BY
            p.pidn,
            ST_Distance(ST_Centroid(p.geom)::geography, eds.geom::geography)
        """,
    ),
    # 15. flood_zone — SFHA flood zone (discount, not hard exclude)
    (
        "flood_zone",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'flood_zone', -0.10,
            'staging.flood_zones', f.fld_ar_id, NULL,
            jsonb_build_object('fld_zone', f.fld_zone, 'zone_subty', f.zone_subty, 'sfha_tf', f.sfha_tf,
                               'source_url', f.source_url,
                               'evidence_captured_at', NOW())
        FROM staging.parcels p
        JOIN staging.flood_zones f
            ON ST_Intersects(ST_Centroid(p.geom), f.geom)
        WHERE p.valid_to IS NULL AND f.valid_to IS NULL AND f.sfha_tf = 'T'
        ORDER BY p.pidn
        """,
    ),
    # 15. conservation_easement — hard exclude
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
    # 16. ag_security — hard exclude
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
        "business_parks_arcgis",
        "industrial_parks_arcgis",
        "zoning_overlays_arcgis",
        "soils_arcgis",
        "local_traffic_counts_arcgis",
        "growth_areas_arcgis",
        "future_landuse_arcgis",
        "conservation_easements_arcgis",
        "ag_security_arcgis",
        "parcels_arcgis",
        "penndot_projects_arcgis",
        "tax_claims",
        "fema_flood_zones",
        "pa_dep_environmental_diligence",
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

    county = get_county_config()
    source_keys = [county_open_data_source_key()]
    if county.penndot_projects_url:
        source_keys.append("penndot_open_data")
    if county.fema_nfhl_url and county.fema_dfirm_id:
        source_keys.append("fema_nfhl")
    if county.pa_dep_query_bbox:
        source_keys.append("pa_dep_open_data")
    authorize_source_uses(
        database,
        source_keys=tuple(source_keys),
        use="derived_product",
        asset_key="development_signals",
        dagster_run_id=context.run_id,
    )
    include_tax_claims = bool(county.tax_claims_pdf_url) and source_use_is_authorized(
        database,
        source_key="tax_claims",
        use="derived_product",
        asset_key="development_signals:tax_distress",
        dagster_run_id=context.run_id,
    )
    signal_params = {
        "subdivision_radius_m": county.signal_subdivision_radius_m,
        "infrastructure_radius_m": county.signal_infrastructure_radius_m,
        "local_traffic_radius_m": county.signal_local_traffic_radius_m,
        "environmental_radius_m": county.signal_environmental_radius_m,
        "nominal_sale_max": county.signal_nominal_sale_max,
        "vacancy_apr_max": county.signal_vacancy_apr_max,
        "vacancy_price_max": county.signal_vacancy_price_max,
        "assemblage_min_neighbors": county.signal_assemblage_min_neighbors,
        "assemblage_strong_neighbors": county.signal_assemblage_strong_neighbors,
    }

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
            if signal_key == "tax_distress" and not include_tax_claims:
                signal_counts[signal_key] = 0
                context.log.info("  tax_distress: disabled by county capability or source policy")
                continue
            cur.execute(sql, signal_params)
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
