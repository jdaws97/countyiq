"""Use indexed owner candidates when refreshing or restoring the materialized view.

The original direct similarity self-join compares every parcel pair within a
municipality. The trigram operator supplies an indexed prefilter; the original
strict similarity cutoff and distinct name-pair result remain unchanged.
"""

from alembic import op

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def _indexes() -> None:
    op.execute("CREATE INDEX idx_ecp_name_a ON public.entity_candidate_pairs (name_a)")
    op.execute("CREATE INDEX idx_ecp_name_b ON public.entity_candidate_pairs (name_b)")


def upgrade() -> None:
    # A global trigram lookup still fetches similar owners across the county.
    # Combining municipality and name reduced a 1,000-owner VPS benchmark from
    # 9.2 to 2.1 seconds. GIN also supports owner-only use of this same index.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")
    op.execute("DROP INDEX staging.idx_parcels_owner_full_trgm")
    op.execute("""
        CREATE INDEX idx_parcels_owner_full_trgm
        ON staging.parcels USING gin (municipality, owner_full gin_trgm_ops)
        WHERE valid_to IS NULL
    """)
    # Function-local settings also apply to pg_restore's direct REFRESH, and
    # cannot inherit a stricter caller threshold that would silently lose pairs.
    # This is an invoker-rights function: it grants no new access to parcel data.
    op.execute("""
        CREATE FUNCTION public.compute_entity_candidate_pairs()
        RETURNS TABLE (name_a varchar, name_b varchar, municipality text, sim real)
        LANGUAGE sql STABLE
        SET pg_trgm.similarity_threshold = '0.5'
        SET search_path = pg_catalog, public
        AS $function$
            WITH owners AS MATERIALIZED (
                SELECT DISTINCT p.municipality, p.owner_full
                FROM staging.parcels p
                WHERE p.valid_to IS NULL
                  AND p.owner_full IS NOT NULL AND p.owner_full <> ''
                  AND p.municipality IS NOT NULL
            )
            SELECT a.owner_full, b.name_b, a.municipality, b.sim
            FROM owners a
            CROSS JOIN LATERAL (
                SELECT DISTINCT p.owner_full AS name_b,
                    public.similarity(a.owner_full, p.owner_full) AS sim
                FROM staging.parcels p
                WHERE p.valid_to IS NULL AND p.owner_full <> ''
                  AND p.municipality = a.municipality
                  AND p.owner_full > a.owner_full
                  AND p.owner_full OPERATOR(public.%) a.owner_full
                  AND public.similarity(a.owner_full, p.owner_full) > 0.5
            ) b
        $function$
    """)
    # No CASCADE: an unexpected downstream schema dependency must stop migration.
    op.execute("DROP MATERIALIZED VIEW public.entity_candidate_pairs")
    op.execute("""
        CREATE MATERIALIZED VIEW public.entity_candidate_pairs AS
        SELECT * FROM public.compute_entity_candidate_pairs()
        WITH DATA
    """)
    _indexes()


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW public.entity_candidate_pairs")
    op.execute("DROP FUNCTION public.compute_entity_candidate_pairs()")
    op.execute("DROP INDEX staging.idx_parcels_owner_full_trgm")
    op.execute("""
        CREATE INDEX idx_parcels_owner_full_trgm
        ON staging.parcels USING gin (owner_full gin_trgm_ops)
        WHERE valid_to IS NULL
    """)
    op.execute("""
        CREATE MATERIALIZED VIEW public.entity_candidate_pairs AS
        SELECT DISTINCT a.owner_full AS name_a, b.owner_full AS name_b,
            a.municipality, similarity(a.owner_full, b.owner_full) AS sim
        FROM staging.parcels a
        JOIN staging.parcels b ON a.municipality = b.municipality
            AND a.owner_full < b.owner_full
            AND similarity(a.owner_full, b.owner_full) > 0.5
        WHERE a.valid_to IS NULL AND b.valid_to IS NULL
            AND a.owner_full IS NOT NULL AND b.owner_full IS NOT NULL
            AND a.owner_full <> '' AND b.owner_full <> ''
        WITH DATA
    """)
    _indexes()
