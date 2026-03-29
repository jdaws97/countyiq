"""add staging.tax_claims

Revision ID: 008
Revises: 007
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tax_claims",
        sa.Column("pidn", sa.String(13), nullable=False),
        sa.Column("parcel_id_raw", sa.String(30), nullable=False),
        sa.Column("unit_suffix", sa.String(10), server_default="00000"),
        sa.Column("tax_district_code", sa.String(5)),
        sa.Column("tax_district_name", sa.String(100)),
        sa.Column("owner_name", sa.Text),
        sa.Column("property_address", sa.Text),
        sa.Column("tax_year", sa.Integer, nullable=False),
        sa.Column("authority_name", sa.String(20), nullable=False),
        sa.Column("tax_owed", sa.Numeric(12, 2)),
        sa.Column("penalty_owed", sa.Numeric(12, 2)),
        sa.Column("interest_owed", sa.Numeric(12, 2)),
        sa.Column("fees_owed", sa.Numeric(12, 2)),
        sa.Column("tax_paid", sa.Numeric(12, 2)),
        sa.Column("penalty_paid", sa.Numeric(12, 2)),
        sa.Column("interest_paid", sa.Numeric(12, 2)),
        sa.Column("fees_paid", sa.Numeric(12, 2)),
        sa.Column("total", sa.Numeric(12, 2)),
        sa.Column("report_date", sa.Date, nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("pidn", "unit_suffix", "tax_year", "authority_name", "valid_from"),
        schema="staging",
    )
    op.create_index(
        "idx_tax_claims_current", "tax_claims",
        ["pidn"], schema="staging",
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "idx_tax_claims_district", "tax_claims",
        ["tax_district_code"], schema="staging",
    )
    op.create_index(
        "idx_tax_claims_owner", "tax_claims",
        ["owner_name"], schema="staging",
    )


def downgrade() -> None:
    op.drop_table("tax_claims", schema="staging")
