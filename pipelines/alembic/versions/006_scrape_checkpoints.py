"""meta.scrape_checkpoints for resumable scraper state

Revision ID: 006
Revises: 005
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scrape_checkpoints",
        sa.Column("source_name", sa.Text, primary_key=True),
        sa.Column("checkpoint", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        schema="meta",
    )


def downgrade() -> None:
    op.drop_table("scrape_checkpoints", schema="meta")
