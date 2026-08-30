"""Enrichment: aggregate validated development signals into scored parcel snapshots.

Reads raw `public.development_signals` plus Pass 2 outputs in `public.evidence`,
so the shipped radar/property experience reflects when signals were confirmed,
downgraded, marked stale, or ruled irrelevant.

If a signal has not been validated yet, the raw signal weight is used as a
fallback so the score path still works when the LLM layer is unavailable.
"""

from dagster import asset, AssetExecutionContext, MaterializeResult, MetadataValue

from countyiq.lib.county_config import county_open_data_source_key, get_county_config
from countyiq.lib.source_rights import authorize_source_uses
from countyiq.resources.database import DatabaseResource


@asset(
    group_name="enrichment",
    # development_signals is a real (transitive) input; declaring it directly
    # keeps partial selections from running momentum before signals exist.
    deps=["signal_validation_batched", "development_signals"],
    description="Aggregate validated development signals → public.development_momentum (0-100 score)",
    kinds={"postgres"},
)
def development_momentum(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    """Aggregate development signals per PIDN into momentum and opportunity scores."""

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
        asset_key="development_momentum",
        dagster_run_id=context.run_id,
    )

    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        cur.execute("TRUNCATE public.development_momentum")
        context.log.info("Truncated public.development_momentum")

        cur.execute("""
            WITH signal_rows AS (
                SELECT DISTINCT ON (ds.pidn, ds.signal_key)
                    ds.pidn,
                    ds.signal_key,
                    ds.signal_weight AS base_weight,
                    ds.source_id,
                    ds.distance_m,
                    ds.evidence,
                    ds.observed_at,
                    e.claim,
                    COALESCE(e.source_url, ds.evidence->>'source_url') AS source_url,
                    e.internal_url,
                    e.validation_status,
                    e.adjusted_significance,
                    e.validation_reasoning,
                    e.cross_references,
                    e.validated_at,
                    CASE COALESCE(e.adjusted_significance, '')
                        WHEN 'high' THEN 1.0
                        WHEN 'medium' THEN 0.7
                        WHEN 'low' THEN 0.4
                        WHEN 'none' THEN 0.0
                        ELSE 1.0
                    END AS significance_multiplier,
                    CASE COALESCE(e.validation_status, '')
                        WHEN 'upgraded' THEN 1.1
                        WHEN 'downgraded' THEN 0.6
                        WHEN 'stale' THEN 0.25
                        WHEN 'irrelevant' THEN 0.0
                        ELSE 1.0
                    END AS status_multiplier
                FROM public.development_signals ds
                LEFT JOIN public.evidence e
                    ON e.pidn = ds.pidn
                   AND e.signal_key = ds.signal_key
                ORDER BY
                    ds.pidn,
                    ds.signal_key,
                    e.validated_at DESC NULLS LAST,
                    ds.observed_at DESC NULLS LAST,
                    ds.id DESC
            ),
            scored_signals AS (
                SELECT
                    pidn,
                    signal_key,
                    base_weight,
                    source_id,
                    distance_m,
                    evidence,
                    claim,
                    source_url,
                    internal_url,
                    validation_status,
                    adjusted_significance,
                    validation_reasoning,
                    COALESCE(cross_references, '[]'::jsonb) AS cross_references,
                    validated_at,
                    CASE
                        WHEN signal_key IN ('conservation_easement', 'ag_security')
                            THEN base_weight
                        ELSE ROUND(
                            (base_weight * significance_multiplier * status_multiplier)::numeric,
                            4
                        )
                    END AS effective_weight
                FROM signal_rows
            ),
            aggregated AS (
                SELECT
                    pidn,
                    jsonb_object_agg(
                        signal_key,
                        jsonb_build_object(
                            'weight', effective_weight,
                            'base_weight', base_weight,
                            'distance_m', distance_m,
                            'source_id', source_id,
                            'evidence', evidence,
                            'claim', claim,
                            'source_url', source_url,
                            'internal_url', internal_url,
                            'validation_status', validation_status,
                            'adjusted_significance', adjusted_significance,
                            'validation_reasoning', validation_reasoning,
                            'cross_references', cross_references,
                            'validated_at', validated_at
                        )
                    ) AS signals,
                    -- Momentum should reflect observed activity, not vacant-site optionality.
                    GREATEST(SUM(
                        CASE
                            WHEN signal_key IN ('vacancy', 'assemblage') THEN 0
                            ELSE effective_weight
                        END
                    ), 0)                                     AS raw_score,
                    COALESCE(SUM(effective_weight) FILTER (
                        WHERE signal_key IN (
                            'economic_development_park',
                            'ownership_change',
                            'tax_distress'
                        )
                    ), 0)                                     AS opportunity_strong_raw,
                    COALESCE(SUM(effective_weight) FILTER (
                        WHERE signal_key IN ('vacancy', 'assemblage')
                    ), 0)                                     AS opportunity_site_raw,
                    COALESCE(SUM(effective_weight) FILTER (
                        WHERE signal_key IN (
                            'zoning_mismatch',
                            'penndot_project',
                            'development_overlay',
                            'local_traffic_activity',
                            'growth_area'
                        )
                    ), 0)                                     AS opportunity_context_raw,
                    COALESCE(SUM(effective_weight) FILTER (
                        WHERE signal_key IN (
                            'flood_zone', 'soil_constraint', 'zoning_constraint',
                            'environmental_diligence'
                        )
                    ), 0)                                     AS opportunity_negative_raw,
                    BOOL_OR(signal_key = 'active_subdivision' AND effective_weight > 0)
                                                              AS has_active_plan,
                    BOOL_OR(signal_key IN (
                        'economic_development_park',
                        'ownership_change',
                        'tax_distress'
                    ) AND effective_weight > 0)               AS has_strong_opportunity,
                    COUNT(*) FILTER (
                        WHERE effective_weight > 0
                           OR signal_key IN ('conservation_easement', 'ag_security')
                    )                                         AS signal_count,
                    BOOL_OR(signal_key IN ('conservation_easement', 'ag_security'))
                                                              AS has_exclusion,
                    jsonb_agg(signal_key)
                        FILTER (WHERE signal_key IN ('conservation_easement', 'ag_security'))
                                                              AS exclusion_reasons,
                    BOOL_OR(signal_key = 'economic_development_park' AND effective_weight > 0)
                                                              AS in_economic_park,
                    BOOL_OR(signal_key = 'growth_area' AND effective_weight > 0)
                                                              AS in_growth_area,
                    BOOL_OR(signal_key = 'development_overlay' AND effective_weight > 0)
                                                              AS in_development_overlay,
                    BOOL_OR(signal_key = 'local_traffic_activity' AND effective_weight > 0)
                                                              AS has_local_traffic,
                    BOOL_OR(signal_key = 'penndot_project' AND effective_weight > 0)
                                                              AS near_penndot_project,
                    BOOL_OR(signal_key = 'vacancy' AND effective_weight > 0)
                                                              AS is_lightly_improved,
                    BOOL_OR(signal_key = 'soil_constraint')   AS has_soil_constraint,
                    BOOL_OR(signal_key = 'zoning_constraint') AS has_zoning_constraint,
                    BOOL_OR(signal_key = 'flood_zone')        AS has_flood_constraint,
                    BOOL_OR(signal_key = 'environmental_diligence')
                                                              AS has_environmental_diligence
                FROM scored_signals
                GROUP BY pidn
            ),
            top_signals AS (
                SELECT DISTINCT ON (pidn)
                    pidn,
                    signal_key,
                    evidence
                FROM scored_signals
                WHERE signal_key NOT IN ('conservation_easement', 'ag_security')
                  AND effective_weight > 0
                ORDER BY
                    pidn,
                    CASE signal_key
                        WHEN 'active_subdivision' THEN 1
                        WHEN 'economic_development_park' THEN 2
                        WHEN 'tax_distress' THEN 3
                        WHEN 'ownership_change' THEN 4
                        WHEN 'vacancy' THEN 5
                        WHEN 'assemblage' THEN 6
                        WHEN 'zoning_mismatch' THEN 7
                        WHEN 'penndot_project' THEN 8
                        WHEN 'development_overlay' THEN 9
                        WHEN 'local_traffic_activity' THEN 10
                        WHEN 'growth_area' THEN 11
                        WHEN 'flood_zone' THEN 99
                        ELSE 50
                    END,
                    effective_weight DESC
            )
            INSERT INTO public.development_momentum (
                pidn,
                score,
                opportunity_score,
                site_readiness_score,
                has_active_plan,
                eligible,
                signal_count,
                top_signal,
                signals,
                exclusion_reasons,
                score_version,
                computed_at
            )
            SELECT
                a.pidn,
                -- Momentum score: all signals
                CASE
                    WHEN a.has_exclusion THEN 0
                    ELSE LEAST(ROUND(a.raw_score * 100)::int, 100)
                END                                           AS score,
                -- Opportunity score: excludes active_subdivision weight
                CASE
                    WHEN a.has_exclusion THEN 0
                    WHEN a.has_active_plan THEN 0
                    WHEN NOT a.has_strong_opportunity THEN 0
                    ELSE LEAST(ROUND(GREATEST(
                        a.opportunity_strong_raw
                        + LEAST(a.opportunity_site_raw, 0.12)
                        + LEAST(a.opportunity_context_raw, 0.08)
                        + a.opportunity_negative_raw,
                        0
                    ) * 100)::int, 100)
                END                                           AS opportunity_score,
                CASE
                    WHEN a.has_exclusion THEN 0
                    ELSE LEAST(GREATEST(
                        50
                        + CASE WHEN a.in_economic_park THEN 25 ELSE 0 END
                        + CASE WHEN a.in_growth_area THEN 10 ELSE 0 END
                        + CASE WHEN a.in_development_overlay THEN 5 ELSE 0 END
                        + CASE WHEN a.has_local_traffic THEN 5 ELSE 0 END
                        + CASE WHEN a.near_penndot_project THEN 5 ELSE 0 END
                        + CASE WHEN a.is_lightly_improved THEN 5 ELSE 0 END
                        - CASE WHEN a.has_soil_constraint THEN 15 ELSE 0 END
                        - CASE WHEN a.has_zoning_constraint THEN 15 ELSE 0 END
                        - CASE WHEN a.has_flood_constraint THEN 20 ELSE 0 END
                        - CASE WHEN a.has_environmental_diligence THEN 10 ELSE 0 END,
                        0
                    ), 100)
                END                                           AS site_readiness_score,
                COALESCE(a.has_active_plan, FALSE),
                NOT a.has_exclusion                           AS eligible,
                a.signal_count,
                CASE t.signal_key
                    WHEN 'active_subdivision'
                        THEN 'Active subdivision: ' || COALESCE(t.evidence->>'plan_title', 'Unknown')
                    WHEN 'economic_development_park'
                        THEN 'Designated economic-development park'
                    WHEN 'zoning_mismatch'
                        THEN 'Zoned ' || COALESCE(t.evidence->>'current_zname', t.evidence->>'current_ztype') || ' → planned ' || COALESCE(t.evidence->>'future_lu', '?')
                    WHEN 'ownership_change'
                        THEN CASE
                            WHEN COALESCE(t.evidence->>'buyer_is_llc', 'false') = 'true'
                                THEN 'Investor purchase ' || COALESCE(t.evidence->>'saledt', '?') || ' for $' || COALESCE(t.evidence->>'price', '?')
                            ELSE 'Sold ' || COALESCE(t.evidence->>'saledt', '?') || ' for $' || COALESCE(t.evidence->>'price', '?')
                        END
                    WHEN 'vacancy'
                        THEN 'Likely vacant / lightly improved parcel'
                    WHEN 'tax_distress'
                        THEN '$' || COALESCE(t.evidence->>'total_owed', '?') || ' owed (' || COALESCE(t.evidence->>'years_delinquent', '?') || ' years)'
                    WHEN 'assemblage'
                        THEN 'Assemblage edge: ' || COALESCE(t.evidence->>'different_owner_neighbors', '?') || ' differently owned neighbors'
                    WHEN 'penndot_project'
                        THEN 'Near ' || COALESCE(t.evidence->>'project_name', 'PennDOT project')
                    WHEN 'development_overlay'
                        THEN 'In ' || COALESCE(t.evidence->>'overlay_name', 'development overlay')
                    WHEN 'local_traffic_activity'
                        THEN COALESCE(t.evidence->>'volume', '?') || ' vehicles at a nearby ' || COALESCE(t.evidence->>'count_year', '?') || ' count'
                    WHEN 'growth_area'
                        THEN 'In ' || CASE WHEN t.evidence->>'ga_type' = 'PGA' THEN 'Primary' ELSE 'Secondary' END || ' Growth Area'
                    WHEN 'flood_zone'
                        THEN 'In SFHA flood zone (' || COALESCE(t.evidence->>'fld_zone', '?') || ')'
                    WHEN 'environmental_diligence'
                        THEN 'PA DEP diligence record within screening radius'
                    ELSE t.signal_key
                END                                           AS top_signal,
                a.signals,
                COALESCE(a.exclusion_reasons, '[]'::jsonb)    AS exclusion_reasons,
                5                                             AS score_version,
                NOW()                                         AS computed_at
            FROM aggregated a
            LEFT JOIN top_signals t USING (pidn)
        """)
        rows_inserted = cur.rowcount
        conn.commit()
        context.log.info(f"Inserted {rows_inserted} rows into public.development_momentum")
    except Exception:
        conn.rollback()
        raise
    finally:
        if was_autocommit:
            conn.autocommit = True
        cur.close()

    # Gather stats for metadata
    result = database.execute("""
        SELECT
            COUNT(*)                                        AS total,
            COUNT(*) FILTER (WHERE eligible)                AS eligible,
            COUNT(*) FILTER (WHERE NOT eligible)            AS excluded,
            ROUND(AVG(score)::numeric, 1)                   AS avg_score,
            MAX(score)                                      AS max_score,
            ROUND(AVG(site_readiness_score)::numeric, 1)    AS avg_site_readiness,
            MAX(site_readiness_score)                       AS max_site_readiness
        FROM public.development_momentum
    """)
    (
        total,
        eligible,
        excluded,
        avg_score,
        max_score,
        avg_site_readiness,
        max_site_readiness,
    ) = result[0] if result else (0, 0, 0, 0, 0, 0, 0)

    context.log.info(
        f"Stats — total: {total}, eligible: {eligible}, excluded: {excluded}, "
        f"avg_score: {avg_score}, max_score: {max_score}, "
        f"avg_site_readiness: {avg_site_readiness}, "
        f"max_site_readiness: {max_site_readiness}"
    )

    return MaterializeResult(
        metadata={
            "rows_inserted": MetadataValue.int(rows_inserted),
            "total": MetadataValue.int(total),
            "eligible": MetadataValue.int(eligible),
            "excluded": MetadataValue.int(excluded),
            "avg_score": MetadataValue.float(float(avg_score or 0)),
            "max_score": MetadataValue.int(max_score or 0),
            "avg_site_readiness": MetadataValue.float(float(avg_site_readiness or 0)),
            "max_site_readiness": MetadataValue.int(max_site_readiness or 0),
        }
    )
