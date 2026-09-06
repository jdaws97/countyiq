"""add recorder document metadata tables

Revision ID: 011
Revises: 010
Create Date: 2026-04-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recorded_documents",
        sa.Column("document_id", sa.Text, nullable=False),
        sa.Column("document_number", sa.Text),
        sa.Column("document_type", sa.Text),
        sa.Column("recording_at", sa.DateTime(timezone=True)),
        sa.Column("book", sa.Text),
        sa.Column("page", sa.Text),
        sa.Column("num_pages", sa.Integer),
        sa.Column("consideration", sa.Numeric(14, 2)),
        sa.Column("grantors", JSONB),
        sa.Column("grantees", JSONB),
        sa.Column("legal_text", sa.Text),
        sa.Column("source_url", sa.Text),
        sa.Column("detail_fetched_at", sa.DateTime(timezone=True)),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("document_id", "valid_from"),
        schema="staging",
    )
    op.create_index(
        "idx_recorded_documents_current",
        "recorded_documents",
        ["document_id"],
        schema="staging",
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "idx_recorded_documents_recording_at",
        "recorded_documents",
        ["recording_at"],
        schema="staging",
    )
    op.create_index(
        "idx_recorded_documents_book_page",
        "recorded_documents",
        ["book", "page"],
        schema="staging",
    )

    op.create_table(
        "recorded_document_parcels",
        sa.Column("pidn", sa.Text, nullable=False),
        sa.Column("document_id", sa.Text, nullable=False),
        sa.Column("recorder_upi", sa.String(18)),
        sa.Column("legal_text", sa.Text),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("pidn", "document_id", "valid_from"),
        schema="staging",
    )
    op.create_index(
        "idx_recorded_document_parcels_current_pidn",
        "recorded_document_parcels",
        ["pidn"],
        schema="staging",
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "idx_recorded_document_parcels_current_document",
        "recorded_document_parcels",
        ["document_id"],
        schema="staging",
        postgresql_where=sa.text("valid_to IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_recorded_document_parcels_current_document",
        table_name="recorded_document_parcels",
        schema="staging",
    )
    op.drop_index(
        "idx_recorded_document_parcels_current_pidn",
        table_name="recorded_document_parcels",
        schema="staging",
    )
    op.drop_table("recorded_document_parcels", schema="staging")
    op.drop_index(
        "idx_recorded_documents_book_page",
        table_name="recorded_documents",
        schema="staging",
    )
    op.drop_index(
        "idx_recorded_documents_recording_at",
        table_name="recorded_documents",
        schema="staging",
    )
    op.drop_index(
        "idx_recorded_documents_current",
        table_name="recorded_documents",
        schema="staging",
    )
    op.drop_table("recorded_documents", schema="staging")
