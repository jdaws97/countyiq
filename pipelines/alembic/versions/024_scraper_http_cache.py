"""HTTP validator cache for polite conditional scraping.

Stores ETag / Last-Modified validators per listing URL so the proceedings
scraper can send If-None-Match / If-Modified-Since and skip municipalities
whose minutes pages haven't changed (304) — most weeks, most of them.

Validators are only written after a fully successful pass over that URL,
so a 304 can never hide PDFs that a partially-failed prior run missed.

Revision ID: 024
Revises: 023
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa


revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scraper_http_cache",
        sa.Column("url", sa.Text(), primary_key=True),
        sa.Column("etag", sa.Text()),
        sa.Column("last_modified", sa.Text()),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        schema="meta",
    )


def downgrade() -> None:
    op.drop_table("scraper_http_cache", schema="meta")
