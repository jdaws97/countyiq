"""add GIN trgm index on staging.parcels.owner_full for entity resolution

Revision ID: 015
Revises: 014
Create Date: 2026-04-07

The CANDIDATE_CLUSTERS_QUERY in Pass 1 entity verification does a self-join
on staging.parcels using pg_trgm similarity(). Without a GIN index, this is
O(n²) per municipality — York City alone has 14,678 parcels = 215M comparisons.
With the GIN index, Postgres uses the index to prune candidates before
computing exact similarity, reducing this to seconds.
"""

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pg_trgm extension exists (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # GIN index on owner_full for trgm similarity lookups.
    # Only index current records (valid_to IS NULL) to keep the index small.
    # Using gin_trgm_ops for the % (similarity) operator.
    op.execute("""
        CREATE INDEX IF NOT EXISTS
            idx_parcels_owner_full_trgm
        ON staging.parcels
        USING gin (owner_full gin_trgm_ops)
        WHERE valid_to IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS staging.idx_parcels_owner_full_trgm")
