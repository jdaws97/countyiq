"""materialized view for entity candidate pairs (replaces live trgm self-join)

Revision ID: 017
Revises: 016
Create Date: 2026-04-08

The CANDIDATE_CLUSTERS_QUERY in Pass 1 does a trgm self-join on
staging.parcels within each municipality. This is O(n²) per municipality
and takes 30+ minutes across all 72 municipalities.

This migration creates a materialized view that pre-computes the pairs.
Pass 1 reads from the view (instant) and a Dagster job refreshes it weekly.
"""

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS public.entity_candidate_pairs AS
        SELECT DISTINCT
            a.owner_full AS name_a,
            b.owner_full AS name_b,
            a.municipality,
            similarity(a.owner_full, b.owner_full) AS sim
        FROM staging.parcels a
        JOIN staging.parcels b
            ON a.municipality = b.municipality
           AND a.owner_full < b.owner_full
           AND similarity(a.owner_full, b.owner_full) > 0.5
        WHERE a.valid_to IS NULL
          AND b.valid_to IS NULL
          AND a.owner_full IS NOT NULL
          AND b.owner_full IS NOT NULL
          AND a.owner_full != ''
          AND b.owner_full != ''
        WITH NO DATA
    """)
    # Index for fast lookups by name
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ecp_name_a
        ON public.entity_candidate_pairs (name_a)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ecp_name_b
        ON public.entity_candidate_pairs (name_b)
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS public.entity_candidate_pairs")
