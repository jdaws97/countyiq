"""Index meter-based proximity without an inaccurate degree prefilter."""
from alembic import op

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE INDEX idx_parcels_current_geography
        ON staging.parcels USING gist ((geom::geography))
        WHERE valid_to IS NULL AND geom IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX staging.idx_parcels_current_geography")
