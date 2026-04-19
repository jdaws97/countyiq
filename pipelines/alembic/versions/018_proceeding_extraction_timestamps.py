"""add extracted_at timestamp to proceeding_extractions

Revision ID: 018
Revises: 017
Create Date: 2026-04-09

Pass 2 needs a real extraction timestamp so late or retried Pass 0 inserts on
older proceedings can trigger revalidation correctly. The base table only had
an autoincrement id, which is not enough to reconstruct "what changed since the
last pass run" without a stored watermark.
"""

from alembic import op
import sqlalchemy as sa


revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proceeding_extractions",
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="staging",
    )
    op.create_index(
        "idx_proceeding_extractions_extracted_at",
        "proceeding_extractions",
        ["extracted_at"],
        schema="staging",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_proceeding_extractions_extracted_at",
        table_name="proceeding_extractions",
        schema="staging",
    )
    op.drop_column("proceeding_extractions", "extracted_at", schema="staging")
