"""add unified public intelligence events

Creates the product-facing event ledger that combines deterministic parcel and
delinquency changes with LLM-extracted municipal development activity.  The
ledger is derived and rebuildable; raw source payloads remain in R2 and source
records remain in their staging/public tables.

Revision ID: 029
Revises: 028
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Cache the source-bounded interpretation produced during Pass 0. Keeping
    # it on the extraction row means rebuilding the public feed never causes a
    # second LLM call.
    op.add_column(
        "proceeding_extractions",
        sa.Column("event_tags", sa.ARRAY(sa.Text), nullable=True),
        schema="staging",
    )
    op.add_column(
        "proceeding_extractions",
        sa.Column("project_name", sa.Text, nullable=True),
        schema="staging",
    )
    op.add_column(
        "proceeding_extractions",
        sa.Column("related_entities", sa.ARRAY(sa.Text), nullable=True),
        schema="staging",
    )
    op.add_column(
        "proceeding_extractions",
        sa.Column("what_happened", sa.Text, nullable=True),
        schema="staging",
    )
    op.add_column(
        "proceeding_extractions",
        sa.Column("why_it_matters", sa.Text, nullable=True),
        schema="staging",
    )
    op.add_column(
        "proceeding_extractions",
        sa.Column("what_happens_next", sa.Text, nullable=True),
        schema="staging",
    )
    # Municipal documents often say "next month" or name a meeting without a
    # parseable date. Preserve the source wording rather than inventing a date.
    op.add_column(
        "proceeding_extractions",
        sa.Column("upcoming_date", sa.Text, nullable=True),
        schema="staging",
    )
    op.add_column(
        "proceeding_extractions",
        sa.Column(
            "interpretation_generated_at", sa.DateTime(timezone=True), nullable=True
        ),
        schema="staging",
    )

    op.create_table(
        "intelligence_events",
        sa.Column("event_key", sa.Text, primary_key=True),
        sa.Column("source_kind", sa.Text, nullable=False),
        sa.Column("source_record_id", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column(
            "event_tags",
            sa.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("what_happened", sa.Text, nullable=False),
        sa.Column("why_it_matters", sa.Text, nullable=False),
        sa.Column("what_happens_next", sa.Text, nullable=False),
        sa.Column("event_date", sa.Date, nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("municipality", sa.Text, nullable=True),
        sa.Column("project_key", sa.Text, nullable=True),
        sa.Column("project_name", sa.Text, nullable=True),
        sa.Column(
            "related_entities",
            sa.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "related_pidns",
            sa.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "source_evidence",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("interpretation_kind", sa.Text, nullable=False),
        sa.Column("interpretation_model", sa.Text, nullable=True),
        sa.Column(
            "interpretation_generated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="public",
    )
    op.execute(
        "ALTER TABLE public.intelligence_events ADD CONSTRAINT "
        "chk_intelligence_events_source_kind CHECK "
        "(source_kind IN ('parcel_event', 'delinquency_event', 'proceeding_extraction'))"
    )
    op.execute(
        "ALTER TABLE public.intelligence_events ADD CONSTRAINT "
        "chk_intelligence_events_category CHECK "
        "(category IN ('parcel', 'development'))"
    )
    op.execute(
        "ALTER TABLE public.intelligence_events ADD CONSTRAINT "
        "chk_intelligence_events_interpretation CHECK "
        "(interpretation_kind IN ('deterministic', 'llm'))"
    )
    op.execute(
        "ALTER TABLE public.intelligence_events ADD CONSTRAINT "
        "chk_intelligence_events_type CHECK (event_type IN ("
        "'transfer', 'value_change', 'structure_change', 'delinquency_change', "
        "'application', 'hearing', 'revision', 'continuance', 'approval', "
        "'denial', 'condition', 'upcoming_decision'))"
    )
    op.create_index(
        "idx_intelligence_events_detected",
        "intelligence_events",
        [sa.text("detected_at DESC")],
        schema="public",
    )
    op.create_index(
        "idx_intelligence_events_category_type",
        "intelligence_events",
        ["category", "event_type"],
        schema="public",
    )
    op.create_index(
        "idx_intelligence_events_municipality",
        "intelligence_events",
        ["municipality"],
        schema="public",
    )
    op.create_index(
        "idx_intelligence_events_project",
        "intelligence_events",
        ["project_key"],
        schema="public",
    )
    op.create_index(
        "idx_intelligence_events_pidns_gin",
        "intelligence_events",
        ["related_pidns"],
        schema="public",
        postgresql_using="gin",
    )
    op.create_index(
        "idx_intelligence_events_tags_gin",
        "intelligence_events",
        ["event_tags"],
        schema="public",
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("intelligence_events", schema="public")
    for column in (
        "interpretation_generated_at",
        "upcoming_date",
        "what_happens_next",
        "why_it_matters",
        "what_happened",
        "related_entities",
        "project_name",
        "event_tags",
    ):
        op.drop_column("proceeding_extractions", column, schema="staging")
