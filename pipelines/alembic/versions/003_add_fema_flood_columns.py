"""add fema flood zone columns

Revision ID: 003
Revises: 002
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("flood_zones", sa.Column("dfirm_id", sa.Text), schema="staging")
    op.add_column("flood_zones", sa.Column("static_bfe", sa.Float), schema="staging")
    op.add_column("flood_zones", sa.Column("depth", sa.Float), schema="staging")
    op.add_column("flood_zones", sa.Column("v_datum", sa.Text), schema="staging")
    op.add_column("flood_zones", sa.Column("source_cit", sa.Text), schema="staging")
    op.create_index(
        "idx_flood_zones_dfirm",
        "flood_zones",
        ["dfirm_id"],
        schema="staging",
    )
    op.create_index(
        "idx_flood_zones_current",
        "flood_zones",
        ["fld_ar_id"],
        schema="staging",
        postgresql_where=sa.text("valid_to IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_flood_zones_current", table_name="flood_zones", schema="staging")
    op.drop_index("idx_flood_zones_dfirm", table_name="flood_zones", schema="staging")
    op.drop_column("flood_zones", "source_cit", schema="staging")
    op.drop_column("flood_zones", "v_datum", schema="staging")
    op.drop_column("flood_zones", "depth", schema="staging")
    op.drop_column("flood_zones", "static_bfe", schema="staging")
    op.drop_column("flood_zones", "dfirm_id", schema="staging")
