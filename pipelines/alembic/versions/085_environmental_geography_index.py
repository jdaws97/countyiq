"""Index meter-based environmental context reads for current parcels."""

from alembic import op

revision = "085"
down_revision = "084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX idx_environmental_diligence_sites_current_geography
        ON staging.environmental_diligence_sites USING gist ((geom::geography))
        WHERE valid_to IS NULL;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX staging.idx_environmental_diligence_sites_current_geography")
