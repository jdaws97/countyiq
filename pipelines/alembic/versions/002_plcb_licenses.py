"""add staging.plcb_licenses

Revision ID: 002
Revises: 001
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plcb_licenses",
        sa.Column("lid", sa.Text, nullable=False),
        sa.Column("license_number", sa.Text),
        sa.Column("license_type", sa.Text),
        sa.Column("status", sa.Text),
        sa.Column("licensee", sa.Text),
        sa.Column("premises_name", sa.Text),
        sa.Column("premises_address", sa.Text),
        sa.Column("premises_mailing_address", sa.Text),
        sa.Column("premises_owner", sa.Text),
        sa.Column("premises_manager", sa.Text),
        sa.Column("municipality", sa.Text),
        sa.Column("last_issue_date", sa.Text),
        sa.Column("expiration_date", sa.Text),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("lid", "valid_from"),
        schema="staging",
    )
    op.create_index("idx_plcb_current", "plcb_licenses", ["lid"], schema="staging", postgresql_where=sa.text("valid_to IS NULL"))
    op.create_index("idx_plcb_municipality", "plcb_licenses", ["municipality"], schema="staging")
    op.create_index("idx_plcb_licensee", "plcb_licenses", ["licensee"], schema="staging")


def downgrade() -> None:
    op.drop_table("plcb_licenses", schema="staging")
