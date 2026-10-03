"""Commit source acquisition watermarks with each protected staging load."""

from alembic import op

revision = "089"
down_revision = "088"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE meta.source_snapshot_watermarks (
            dataset_key TEXT PRIMARY KEY,
            acquired_at TIMESTAMPTZ NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            snapshot_id TEXT NOT NULL
        );
        COMMENT ON TABLE meta.source_snapshot_watermarks IS
        'Monotonic acquisition timestamps committed in the same transaction '
        'as protected SCD2 loads, including individually scoped source layers.';
    """)


def downgrade():
    op.execute("DROP TABLE meta.source_snapshot_watermarks")
