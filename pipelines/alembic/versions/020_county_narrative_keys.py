"""add stable narrative_key to county_narratives

Revision ID: 020
Revises: 019
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "county_narratives",
        sa.Column("narrative_key", sa.Text(), nullable=True),
        schema="public",
    )
    op.execute(
        """
        UPDATE public.county_narratives
        SET narrative_key = COALESCE(narrative_type, 'narrative') || ':' || narrative_id::text
        WHERE narrative_key IS NULL
        """
    )
    op.alter_column(
        "county_narratives",
        "narrative_key",
        existing_type=sa.Text(),
        nullable=False,
        schema="public",
    )
    op.create_unique_constraint(
        "uq_county_narratives_narrative_key",
        "county_narratives",
        ["narrative_key"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_county_narratives_narrative_key",
        "county_narratives",
        schema="public",
        type_="unique",
    )
    op.drop_column("county_narratives", "narrative_key", schema="public")
