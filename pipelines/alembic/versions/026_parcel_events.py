"""add public.parcel_events

Explicit transfer/value/structure events derived from consecutive
staging.parcels SCD2 versions. Derived data: the table is rebuildable at any
time from parcel version history (INSERT ... ON CONFLICT DO NOTHING keyed on
pidn + event_type + new_version_from), so no raw payloads live here — only
observed field changes with provenance into the SCD2 versions they came from.

Revision ID: 026
Revises: 025
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parcel_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pidn", sa.Text, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("confidence", sa.Text, nullable=False),
        # Event date from source data when stated (e.g. SALEDT for transfers);
        # NULL when the source carries no date — fall back to detected_at.
        sa.Column("event_date", sa.Date),
        # When the weekly parcel refresh first surfaced the change
        # (= valid_from of the new SCD2 version).
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        # Provenance into staging.parcels version history.
        sa.Column("old_version_from", sa.DateTime(timezone=True)),
        sa.Column("new_version_from", sa.DateTime(timezone=True), nullable=False),
        # {changed: {field: {old, new}}, corroboration: [...], pattern: ...}
        sa.Column("evidence", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("pidn", "event_type", "new_version_from", name="uq_parcel_events_version"),
        schema="public",
    )
    op.execute(
        "ALTER TABLE public.parcel_events ADD CONSTRAINT chk_parcel_events_type "
        "CHECK (event_type IN ('transfer', 'value_change', 'structure_change'))"
    )
    op.execute(
        "ALTER TABLE public.parcel_events ADD CONSTRAINT chk_parcel_events_confidence "
        "CHECK (confidence IN ('confirmed', 'likely'))"
    )
    op.create_index("idx_parcel_events_pidn", "parcel_events", ["pidn"], schema="public")
    op.create_index(
        "idx_parcel_events_type_detected", "parcel_events",
        [sa.text("event_type"), sa.text("detected_at DESC")], schema="public",
    )


def downgrade() -> None:
    op.drop_table("parcel_events", schema="public")
