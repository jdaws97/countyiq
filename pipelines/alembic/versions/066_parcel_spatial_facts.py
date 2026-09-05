"""Share parcel zoning selection and soil coverage between reports and signals.

These invoker-rights functions only read current staging records. They do not
rewrite county geometry, retire source history, or refresh serving tables.
"""

from alembic import op

revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION public.parcel_center_zoning(parcel_geom geometry)
        RETURNS SETOF staging.zoning
        LANGUAGE sql STABLE STRICT
        AS $function$
            SELECT z.*
            FROM staging.zoning z
            WHERE z.valid_to IS NULL AND z.geom IS NOT NULL
              AND ST_Intersects(z.geom, ST_Centroid(parcel_geom))
            -- The county can retain an older district polygon under a later
            -- rezoning. Select the newest adoption before comparing land use.
            ORDER BY z.adpt_date DESC NULLS LAST, z.zrecid DESC
            LIMIT 1
        $function$
    """)
    op.execute("""
        CREATE FUNCTION public.parcel_soil_units(parcel_geom geometry)
        RETURNS TABLE (
            source_record_ids integer[], map_unit_key text,
            map_unit_symbol text, map_unit_name text, drainage text,
            capability_class numeric, permeability numeric, septic_rating text,
            slope_low integer, slope_high integer, representative_slope numeric,
            hydric_rating text, hydrologic_group text, relative_value text,
            source_url text, valid_from timestamptz, coverage_pct numeric,
            mapped_coverage_pct numeric, very_limited_coverage_pct numeric
        )
        LANGUAGE sql STABLE STRICT
        AS $function$
            WITH clipped AS MATERIALIZED (
                SELECT s.*,
                    ST_Intersection(ST_MakeValid(parcel_geom), ST_MakeValid(s.geom)) AS overlap_geom
                FROM staging.soils s
                WHERE s.valid_to IS NULL AND s.geom IS NOT NULL
                  AND s.geom && parcel_geom AND ST_Intersects(s.geom, parcel_geom)
            ), material AS MATERIALIZED (
                SELECT * FROM clipped WHERE ST_Area(overlap_geom) > 0
            ), totals AS (
                SELECT
                    ST_Area(ST_Transform(ST_MakeValid(parcel_geom), 32617)) AS area_m2,
                    ST_Area(ST_Transform(ST_UnaryUnion(ST_Collect(overlap_geom)), 32617)) AS mapped_m2,
                    COALESCE(ST_Area(ST_Transform(ST_UnaryUnion(ST_Collect(overlap_geom)
                        FILTER (WHERE LOWER(septic_rating) = 'very limited')), 32617)), 0) AS septic_m2
                FROM material
            ), units AS (
                SELECT ARRAY_AGG(DISTINCT objectid ORDER BY objectid) AS source_record_ids,
                    map_unit_key, map_unit_symbol, map_unit_name, drainage,
                    capability_class, permeability, septic_rating,
                    slope_low, slope_high, representative_slope,
                    hydric_rating, hydrologic_group, relative_value, source_url,
                    MAX(valid_from) AS valid_from,
                    ST_UnaryUnion(ST_Collect(overlap_geom)) AS overlap_geom
                FROM material
                GROUP BY map_unit_key, map_unit_symbol, map_unit_name, drainage,
                    capability_class, permeability, septic_rating,
                    slope_low, slope_high, representative_slope,
                    hydric_rating, hydrologic_group, relative_value, source_url,
                    -- An unidentified unit must not merge merely by its label.
                    CASE WHEN map_unit_key IS NULL THEN objectid END
            )
            SELECT u.source_record_ids, u.map_unit_key,
                u.map_unit_symbol, u.map_unit_name, u.drainage,
                u.capability_class, u.permeability, u.septic_rating,
                u.slope_low, u.slope_high, u.representative_slope,
                u.hydric_rating, u.hydrologic_group, u.relative_value,
                u.source_url, u.valid_from,
                (100 * ST_Area(ST_Transform(u.overlap_geom, 32617)) / NULLIF(t.area_m2, 0))::numeric,
                (100 * t.mapped_m2 / NULLIF(t.area_m2, 0))::numeric,
                (100 * t.septic_m2 / NULLIF(t.area_m2, 0))::numeric
            FROM units u CROSS JOIN totals t
        $function$
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION public.parcel_soil_units(geometry)")
    op.execute("DROP FUNCTION public.parcel_center_zoning(geometry)")
