"""make meeting_date nullable, add content_hash for dedup

Revision ID: 019
Revises: 018
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Allow NULLs for PDFs where we can't parse a date from the filename
    op.alter_column(
        "public_proceedings",
        "meeting_date",
        existing_type=sa.Date(),
        nullable=True,
        schema="staging",
    )
    # SHA-256 hash of PDF content for dedup on same-URL sites
    op.add_column(
        "public_proceedings",
        sa.Column("content_hash", sa.Text),
        schema="staging",
    )
    op.create_index(
        "idx_public_proceedings_content_hash",
        "public_proceedings",
        ["content_hash"],
        schema="staging",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_public_proceedings_content_hash",
        table_name="public_proceedings",
        schema="staging",
    )
    op.drop_column("public_proceedings", "content_hash", schema="staging")
    op.alter_column(
        "public_proceedings",
        "meeting_date",
        existing_type=sa.Date(),
        nullable=False,
        schema="staging",
    )
