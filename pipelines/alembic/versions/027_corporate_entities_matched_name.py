"""corporate_entities: add matched_name for the SODA lookup path

entity_name stays the parcel-owner search key (what the pending-lookup dedupe
joins on); matched_name records the DOS-registered business name exactly as
published in the data.pa.gov dataset (xvd7-5r2c), which may differ in case
and punctuation from the county's owner string.

Revision ID: 027
Revises: 026
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "corporate_entities",
        sa.Column("matched_name", sa.Text),
        schema="staging",
    )


def downgrade() -> None:
    op.drop_column("corporate_entities", "matched_name", schema="staging")
