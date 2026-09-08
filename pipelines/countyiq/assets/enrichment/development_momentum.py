"""Enrichment: aggregate deterministic development signals into scored parcel snapshots.

Score version 7 (2026-09-02). Every score is a deterministic function of
``public.development_signals``:

- **Momentum** ("where activity IS"): the sum of activity signal weights
  (own plan, municipal action, park designation, sales, entity assemblage,
  tax distress, and context). Vacancy and neighbourhood fragmentation are
  optionality, not activity, and are excluded.
- **Opportunity** ("where it SHOULD happen next"): a separately calibrated
  weight set. The weights come from the historical-plan back-test in
  ``pipelines/scripts/backtest_radar_weights.py`` (report:
  ``docs/research/radar-backtest-2026-09-02.md``), which asks which current
  signals predicted a believable subdivision or land-development plan being
  filed on the parcel. Parcels that already have their own plan or municipal
  matter are activity, not opportunity, and score 0 here.
- **Site readiness**: unchanged policy/physical screen.

Pass 2 output (``public.evidence``) is carried into the ``signals`` JSON as
an annotation (validation status, reasoning, claim) so the property page can
show it, but it never changes a score. Before v6 the LLM's status and
significance multiplied the weights, which ranked every validated parcel
below unvalidated ones and let a model opinion move an auditable rank.

Each rebuild also appends to ``public.development_momentum_history`` and
fills the previous-snapshot columns so the radar can show movers.
"""

from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from countyiq.lib.county_config import county_open_data_source_key, get_county_config
from countyiq.lib.source_rights import authorize_source_uses
from countyiq.resources.database import DatabaseResource

SCORE_VERSION = 7

# Signals whose weight counts toward momentum. Everything else in the signal
# table is either optionality (vacancy, assemblage), a constraint, or an
# exclusion.
MOMENTUM_SIGNAL_KEYS = (
    "active_subdivision",
    "nearby_subdivision",
    "municipal_action",
    "economic_development_park",
    "ownership_change",
    "entity_assemblage",
    "tax_distress",
    "zoning_mismatch",
    "penndot_project",
    "development_overlay",
    "local_traffic_activity",
    "growth_area",
)

# A parcel with its own plan or its own municipal matter is already moving;
# it belongs on the momentum view, not the "buy before everyone notices" one.
ACTIVE_PLAN_SIGNAL_KEYS = ("active_subdivision", "municipal_action")

# Opportunity requires at least one parcel-level signal so overlay-only
# parcels (every parcel in a growth area) do not flood the list.
OPPORTUNITY_GATE_KEYS = (
    "economic_development_park",
    "ownership_change",
    "entity_assemblage",
    "tax_distress",
    "vacancy",
    "nearby_subdivision",
    "zoning_mismatch",
    "assemblage",
)

# Calibrated opportunity weights (raw scale; score = round(sum * 100)).
# Source: docs/research/radar-backtest-2026-09-02.md — ridge logistic fit of
# current signals against believable plans received on the parcel in the
# prior 24 months (131,701 eligible parcels, 496 positives, AUC 0.73 vs 0.62
# for the version-5 weights; precision@250 7.6% vs 3.2%). Entries marked
# "prior" could not be calibrated locally and must be re-fitted after the
# first live proceedings backfill; update this table in one commit with the
# regenerated report rather than hand-tuning individual entries.
OPPORTUNITY_WEIGHTS: dict[str, float] = {
    "entity_assemblage": 0.23,  # lift 12.2x, coef +2.60
    "economic_development_park": 0.22,  # lift 26.4x, coef +2.50
    "assemblage": 0.15,  # lift 3.7x, coef +1.64
    "vacancy": 0.12,  # lift 3.6x, coef +1.35 (under-counted for positives)
    "nearby_subdivision": 0.10,  # prior: label-derived, excluded from the fit
    "zoning_mismatch": 0.06,  # lift 1.7x, coef +0.64
    "growth_area": 0.05,  # lift 1.15x, coef +0.53
    "tax_distress": 0.04,  # lift 2.0x, coef +0.39
    "ownership_change": 0.04,  # prior: 12-month window vs 24-month label was inconclusive
    "penndot_project": 0.02,  # lift 1.4x, coef +0.20
    "local_traffic_activity": 0.02,  # lift 1.3x, coef +0.20
    "development_overlay": 0.00,  # 0 positives in 1,284 parcels: built-out corridors
    "environmental_diligence": 0.00,  # positive lift, but a diligence flag never adds opportunity
    "zoning_constraint": -0.01,  # lift 0.92, coef -0.10
    "flood_zone": -0.02,  # coef -0.25
    "soil_constraint": -0.03,  # lift 0.80, coef -0.28
    "ag_security": 0.00,  # planning context only; ASA enrollment is not a development prohibition
}

_TOP_SIGNAL_PRIORITY = {
    "active_subdivision": 1,
    "municipal_action": 2,
    "municipal_record": 3,
    "economic_development_park": 3,
    "entity_assemblage": 4,
    "tax_distress": 5,
    "ownership_change": 6,
    "nearby_subdivision": 7,
    "vacancy": 8,
    "assemblage": 9,
    "zoning_mismatch": 10,
    "penndot_project": 11,
    "development_overlay": 12,
    "local_traffic_activity": 13,
    "growth_area": 14,
    "ag_security": 95,
    "flood_zone": 99,
}


def _sql_list(keys) -> str:
    return ", ".join(f"'{key}'" for key in keys)


def _weight_case(weights: dict[str, float]) -> str:
    branches = "\n".join(
        f"                        WHEN '{key}' THEN {weight:.4f}"
        for key, weight in weights.items()
    )
    return f"CASE signal_key\n{branches}\n                        ELSE 0 END"


def _priority_case() -> str:
    branches = "\n".join(
        f"                        WHEN '{key}' THEN {rank}"
        for key, rank in _TOP_SIGNAL_PRIORITY.items()
    )
    return f"CASE signal_key\n{branches}\n                        ELSE 50 END"


def _site_screening_case() -> str:
    """Return the exact per-signal point adjustment used by site screening."""

    return """CASE signal_key
                        WHEN 'economic_development_park' THEN 25
                        WHEN 'growth_area' THEN 10
                        WHEN 'development_overlay' THEN 5
                        WHEN 'local_traffic_activity' THEN 5
                        WHEN 'penndot_project' THEN 5
                        WHEN 'vacancy' THEN 5
                        WHEN 'soil_constraint' THEN -15
                        WHEN 'zoning_constraint' THEN -15
                        WHEN 'flood_zone' THEN -20
                        WHEN 'environmental_diligence' THEN -10
                        ELSE 0
                    END"""


def build_rebuild_sql() -> str:
    """Return the INSERT that rebuilds public.development_momentum."""

    return f"""
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
                e.validated_at
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
                *,
                -- Score version 7: the deterministic weight is the effective
                -- weight. Pass 2 fields above are annotations only.
                base_weight AS effective_weight,
                ({_weight_case(OPPORTUNITY_WEIGHTS)}) AS opportunity_weight,
                CASE
                    WHEN signal_key IN ({_sql_list(MOMENTUM_SIGNAL_KEYS)})
                        THEN ROUND(base_weight * 100)::int
                    ELSE 0
                END AS momentum_points,
                ROUND((({_weight_case(OPPORTUNITY_WEIGHTS)}) * 100))::int
                    AS opportunity_points,
                ({_site_screening_case()}) AS site_screening_points,
                (signal_key = 'conservation_easement') AS affects_eligibility
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
                        'opportunity_weight', opportunity_weight,
                        'momentum_points', momentum_points,
                        'opportunity_points', opportunity_points,
                        'site_screening_points', site_screening_points,
                        'affects_eligibility', affects_eligibility,
                        'distance_m', distance_m,
                        'source_id', source_id,
                        'evidence', evidence,
                        'claim', claim,
                        'source_url', source_url,
                        'internal_url', internal_url,
                        'validation_status', validation_status,
                        'adjusted_significance', adjusted_significance,
                        'validation_reasoning', validation_reasoning,
                        'cross_references', COALESCE(cross_references, '[]'::jsonb),
                        'validated_at', validated_at
                    )
                ) AS signals,
                GREATEST(COALESCE(SUM(effective_weight) FILTER (
                    WHERE signal_key IN ({_sql_list(MOMENTUM_SIGNAL_KEYS)})
                ), 0), 0)                                     AS momentum_raw,
                COALESCE(SUM(opportunity_weight) FILTER (
                    WHERE signal_key <> 'conservation_easement'
                ), 0)                                         AS opportunity_raw,
                BOOL_OR(signal_key IN ({_sql_list(ACTIVE_PLAN_SIGNAL_KEYS)}))
                                                              AS has_active_plan,
                BOOL_OR(signal_key IN ({_sql_list(OPPORTUNITY_GATE_KEYS)}))
                                                              AS passes_opportunity_gate,
                COUNT(*)                                      AS signal_count,
                BOOL_OR(signal_key = 'conservation_easement')
                                                              AS has_exclusion,
                jsonb_agg(signal_key)
                    FILTER (WHERE signal_key = 'conservation_easement')
                                                              AS exclusion_reasons,
                BOOL_OR(signal_key = 'economic_development_park') AS in_economic_park,
                BOOL_OR(signal_key = 'growth_area')            AS in_growth_area,
                BOOL_OR(signal_key = 'development_overlay')    AS in_development_overlay,
                BOOL_OR(signal_key = 'local_traffic_activity') AS has_local_traffic,
                BOOL_OR(signal_key = 'penndot_project')        AS near_penndot_project,
                BOOL_OR(signal_key = 'vacancy')                AS is_lightly_improved,
                BOOL_OR(signal_key = 'soil_constraint')        AS has_soil_constraint,
                BOOL_OR(signal_key = 'zoning_constraint')      AS has_zoning_constraint,
                BOOL_OR(signal_key = 'flood_zone')             AS has_flood_constraint,
                BOOL_OR(signal_key = 'environmental_diligence')
                                                              AS has_environmental_diligence
            FROM scored_signals
            GROUP BY pidn
        ),
        top_signals AS (
            SELECT DISTINCT ON (pidn)
                pidn,
                signal_key,
                evidence,
                distance_m
            FROM scored_signals
            WHERE signal_key <> 'conservation_easement'
            ORDER BY
                pidn,
                {_priority_case()},
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
            CASE
                WHEN a.has_exclusion THEN 0
                ELSE LEAST(ROUND(a.momentum_raw * 100)::int, 100)
            END                                           AS score,
            CASE
                WHEN a.has_exclusion THEN 0
                WHEN a.has_active_plan THEN 0
                WHEN NOT a.passes_opportunity_gate THEN 0
                ELSE LEAST(ROUND(GREATEST(a.opportunity_raw, 0) * 100)::int, 100)
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
                    THEN CASE
                        WHEN COALESCE(t.distance_m, 0) <= 0.5
                            THEN 'Plan point mapped on parcel: '
                        ELSE 'Plan point ' || ROUND(t.distance_m)::text || ' m from parcel boundary: '
                    END || COALESCE(t.evidence->>'plan_title', 'Unknown')
                WHEN 'nearby_subdivision'
                    THEN 'Plan ' || COALESCE(ROUND(t.distance_m)::text, '?') || ' m away: '
                         || COALESCE(t.evidence->>'plan_title', 'Unknown')
                WHEN 'municipal_action'
                    THEN 'Municipal ' || REPLACE(COALESCE(t.evidence->>'extraction_type', 'proceeding'), '_', ' ')
                         || ' linked by ' || REPLACE(COALESCE(t.evidence->>'match_method', 'record'), '_', ' ')
                         || COALESCE(' (' || (t.evidence->>'decision') || ')', '')
                WHEN 'municipal_record'
                    THEN 'Municipal record: ' || COALESCE(t.evidence->>'title', 'property reference')
                WHEN 'economic_development_park'
                    THEN 'Mapped in official business/industrial park inventory'
                WHEN 'entity_assemblage'
                    THEN 'Same recorded owner holds ' || COALESCE(t.evidence->>'contiguous_same_owner_parcels', '?') || ' touching parcels after a recent acquisition'
                WHEN 'zoning_mismatch'
                    THEN 'Parcel-center zoning ' || COALESCE(t.evidence->>'current_zname', t.evidence->>'current_ztype') || ' differs from planned land use ' || COALESCE(t.evidence->>'future_lu', '?')
                WHEN 'ownership_change'
                    THEN CASE
                        WHEN COALESCE(t.evidence->>'buyer_name_looks_organizational', 'false') = 'true'
                            THEN 'Recorded sale to organization-name buyer on ' || COALESCE(t.evidence->>'saledt', '?') || ' for $' || COALESCE(t.evidence->>'price', '?')
                        ELSE 'Recorded sale on ' || COALESCE(t.evidence->>'saledt', '?') || ' for $' || COALESCE(t.evidence->>'price', '?')
                    END
                WHEN 'vacancy'
                    THEN 'No mapped building footprint; low-value screen'
                WHEN 'tax_distress'
                    THEN 'Current tax-delinquency indicator'
                WHEN 'assemblage'
                    THEN 'Touches ' || COALESCE(t.evidence->>'neighbor_parcels', '?') || ' parcels held by other named owners'
                WHEN 'penndot_project'
                    THEN COALESCE(INITCAP(t.evidence->>'status') || ' ', '') || 'PennDOT project '
                         || COALESCE(ROUND(t.distance_m)::text || ' m away: ', '')
                         || COALESCE(t.evidence->>'project_name', 'Unnamed project')
                WHEN 'development_overlay'
                    THEN 'Parcel center mapped in ' || COALESCE(t.evidence->>'overlay_name', 'development overlay')
                WHEN 'local_traffic_activity'
                    THEN 'Reported volume ' || COALESCE(t.evidence->>'volume', '?') || ' at '
                         || COALESCE(t.evidence->>'count_year', '?') || ' traffic count'
                WHEN 'growth_area'
                    THEN 'Parcel center lies in ' || CASE WHEN t.evidence->>'ga_type' = 'PGA' THEN 'Primary' ELSE 'Secondary' END || ' Growth Area'
                WHEN 'soil_constraint'
                    THEN 'Mapped soil constraint: ' || COALESCE(
                        t.evidence->'soil_units'->0->>'map_unit_name',
                        t.evidence->>'map_unit_name',
                        'review mapped soil units'
                    )
                WHEN 'zoning_constraint'
                    THEN 'Parcel center lies in ' || COALESCE(t.evidence->>'overlay_type', 'special-purpose') || ' overlay'
                WHEN 'flood_zone'
                    THEN 'SFHA overlaps ' || COALESCE(t.evidence->>'overlap_pct', '?') || '% of parcel'
                WHEN 'environmental_diligence'
                    THEN 'PA DEP record ' || COALESCE(ROUND(t.distance_m)::text || ' m away', 'within screening radius')
                WHEN 'ag_security'
                    THEN 'Agricultural Security Area enrollment (not a development prohibition)'
                ELSE t.signal_key
            END                                           AS top_signal,
            a.signals,
            COALESCE(a.exclusion_reasons, '[]'::jsonb)    AS exclusion_reasons,
            {SCORE_VERSION}                               AS score_version,
            NOW()                                         AS computed_at
        FROM aggregated a
        LEFT JOIN top_signals t USING (pidn)
    """


# Movers: fill previous-snapshot columns from the newest history row that is
# at least a day old (so a same-day re-run compares to last week, not to
# itself), then append this rebuild to the history.
HISTORY_SQL = """
    WITH previous AS (
        SELECT DISTINCT ON (h.pidn)
            h.pidn, h.score, h.opportunity_score, h.site_readiness_score, h.computed_at
        FROM public.development_momentum_history h
        WHERE h.computed_at < NOW() - INTERVAL '1 day'
        ORDER BY h.pidn, h.computed_at DESC
    ),
    latest AS (
        SELECT DISTINCT ON (h.pidn)
            h.pidn, h.score, h.opportunity_score, h.site_readiness_score, h.computed_at
        FROM public.development_momentum_history h
        ORDER BY h.pidn, h.computed_at DESC
    ),
    first_seen AS (
        SELECT pidn, MIN(computed_at) AS first_seen_at
        FROM public.development_momentum_history
        GROUP BY pidn
    )
    UPDATE public.development_momentum dm
    SET previous_score = COALESCE(p.score, l.score),
        previous_opportunity_score = COALESCE(p.opportunity_score, l.opportunity_score),
        previous_site_readiness_score = COALESCE(p.site_readiness_score, l.site_readiness_score),
        previous_computed_at = COALESCE(p.computed_at, l.computed_at),
        score_delta = dm.score - COALESCE(p.score, l.score),
        opportunity_delta = dm.opportunity_score - COALESCE(p.opportunity_score, l.opportunity_score),
        first_seen_at = COALESCE(f.first_seen_at, dm.computed_at),
        is_new = (l.pidn IS NULL)
    FROM public.development_momentum inner_dm
    LEFT JOIN previous p ON p.pidn = inner_dm.pidn
    LEFT JOIN latest l ON l.pidn = inner_dm.pidn
    LEFT JOIN first_seen f ON f.pidn = inner_dm.pidn
    WHERE inner_dm.pidn = dm.pidn
"""

APPEND_HISTORY_SQL = """
    INSERT INTO public.development_momentum_history (
        pidn, computed_at, score, opportunity_score, site_readiness_score,
        signal_count, top_signal, score_version
    )
    SELECT pidn, computed_at, score, opportunity_score, site_readiness_score,
           signal_count, top_signal, score_version
    FROM public.development_momentum
    ON CONFLICT (pidn, computed_at) DO NOTHING
"""

PRUNE_HISTORY_SQL = """
    DELETE FROM public.development_momentum_history
    WHERE computed_at < NOW() - INTERVAL '400 days'
"""


@asset(
    group_name="enrichment",
    # development_signals is a real (transitive) input; declaring it directly
    # keeps partial selections from running momentum before signals exist.
    # signal_validation_batched only supplies display annotations now, but the
    # ordering keeps a same-run Pass 2 result visible in the rebuilt JSON.
    deps=["signal_validation_batched", "development_signals"],
    description="Aggregate deterministic development signals → public.development_momentum (score v7) + history",
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
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtext('countyiq:development_momentum'))"
        )
        cur.execute("""
            CREATE TEMP TABLE countyiq_new_momentum
            (LIKE public.development_momentum INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)
            ON COMMIT DROP
        """)
        cur.execute(
            build_rebuild_sql().replace(
                "public.development_momentum", "pg_temp.countyiq_new_momentum"
            )
        )
        rows_inserted = cur.rowcount
        # Match the table plus its separating space, leaving the separate
        # public.development_momentum_history table unchanged.
        cur.execute(
            HISTORY_SQL.replace(
                "public.development_momentum ", "pg_temp.countyiq_new_momentum "
            )
        )
        cur.execute("TRUNCATE public.development_momentum")
        cur.execute(
            "INSERT INTO public.development_momentum SELECT * FROM pg_temp.countyiq_new_momentum"
        )
        cur.execute(APPEND_HISTORY_SQL)
        history_rows = cur.rowcount
        cur.execute(PRUNE_HISTORY_SQL)
        conn.commit()
        context.log.info(
            f"Inserted {rows_inserted} rows into public.development_momentum "
            f"(score_version {SCORE_VERSION}); appended {history_rows} history rows"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        if was_autocommit:
            conn.autocommit = True
        cur.close()

    result = database.execute("""
        SELECT
            COUNT(*)                                        AS total,
            COUNT(*) FILTER (WHERE eligible)                AS eligible,
            COUNT(*) FILTER (WHERE NOT eligible)            AS excluded,
            ROUND(AVG(score)::numeric, 1)                   AS avg_score,
            MAX(score)                                      AS max_score,
            ROUND(AVG(site_readiness_score)::numeric, 1)    AS avg_site_readiness,
            MAX(site_readiness_score)                       AS max_site_readiness,
            COUNT(*) FILTER (WHERE is_new)                  AS new_on_radar,
            COUNT(*) FILTER (WHERE opportunity_delta > 0)   AS opportunity_risers,
            COUNT(*) FILTER (WHERE opportunity_delta < 0)   AS opportunity_fallers
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
        new_on_radar,
        opportunity_risers,
        opportunity_fallers,
    ) = result[0] if result else (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    context.log.info(
        f"Stats — total: {total}, eligible: {eligible}, excluded: {excluded}, "
        f"avg_score: {avg_score}, max_score: {max_score}, "
        f"avg_site_readiness: {avg_site_readiness}, "
        f"max_site_readiness: {max_site_readiness}, new: {new_on_radar}, "
        f"risers: {opportunity_risers}, fallers: {opportunity_fallers}"
    )

    return MaterializeResult(
        metadata={
            "rows_inserted": MetadataValue.int(rows_inserted),
            "score_version": MetadataValue.int(SCORE_VERSION),
            "total": MetadataValue.int(total),
            "eligible": MetadataValue.int(eligible),
            "excluded": MetadataValue.int(excluded),
            "avg_score": MetadataValue.float(float(avg_score or 0)),
            "max_score": MetadataValue.int(max_score or 0),
            "avg_site_readiness": MetadataValue.float(float(avg_site_readiness or 0)),
            "max_site_readiness": MetadataValue.int(max_site_readiness or 0),
            "new_on_radar": MetadataValue.int(new_on_radar or 0),
            "opportunity_risers": MetadataValue.int(opportunity_risers or 0),
            "opportunity_fallers": MetadataValue.int(opportunity_fallers or 0),
        }
    )
