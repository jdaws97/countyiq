"""add intelligence platform tables (staging, public, meta)

Revision ID: 012
Revises: 011
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =====================================================================
    # STAGING SCHEMA -- Intelligence source tables (SCD Type 2)
    # =====================================================================

    # --- staging.corporate_entities (PA DOS corporate entity records) ---
    op.create_table(
        "corporate_entities",
        sa.Column("entity_name", sa.Text, nullable=False),
        sa.Column("entity_number", sa.Text),
        sa.Column("entity_type", sa.Text),
        sa.Column("status", sa.Text),
        sa.Column("formation_date", sa.Date),
        sa.Column("registered_agent_name", sa.Text),
        sa.Column("registered_agent_address", sa.Text),
        sa.Column("office_address", sa.Text),
        sa.Column("officers", JSONB),
        sa.Column("source_url", sa.Text),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("entity_name", "valid_from"),
        schema="staging",
    )
    op.create_index(
        "idx_corporate_entities_current",
        "corporate_entities",
        ["entity_name"],
        schema="staging",
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "idx_corporate_entities_agent",
        "corporate_entities",
        ["registered_agent_name"],
        schema="staging",
        postgresql_where=sa.text("valid_to IS NULL"),
    )

    # --- staging.public_proceedings (meeting minute document metadata) ---
    op.create_table(
        "public_proceedings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("body_name", sa.Text, nullable=False),
        sa.Column("meeting_date", sa.Date, nullable=False),
        sa.Column("proceeding_type", sa.Text, nullable=False),
        sa.Column("raw_text", sa.Text),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("document_url", sa.Text),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        schema="staging",
    )
    op.create_index(
        "idx_public_proceedings_body_date",
        "public_proceedings",
        ["body_name", "meeting_date"],
        schema="staging",
    )

    # --- staging.proceeding_extractions (LLM-extracted records from meetings) ---
    op.create_table(
        "proceeding_extractions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("proceeding_id", sa.Integer, nullable=False),
        sa.Column("extraction_type", sa.Text, nullable=False),
        sa.Column("applicant_name", sa.Text),
        sa.Column("parcel_reference", sa.Text),
        sa.Column("current_zoning", sa.Text),
        sa.Column("proposed_zoning", sa.Text),
        sa.Column("decision", sa.Text),
        sa.Column("conditions", JSONB),
        sa.Column("supporting_text", sa.Text),
        sa.Column("extraction_confidence", sa.Float),
        sa.Column("model_used", sa.Text),
        sa.Column("page_number", sa.Integer),
        sa.ForeignKeyConstraint(["proceeding_id"], ["staging.public_proceedings.id"], name="fk_extraction_proceeding"),
        schema="staging",
    )
    op.create_index(
        "idx_proceeding_extractions_applicant",
        "proceeding_extractions",
        ["applicant_name"],
        schema="staging",
    )
    op.create_index(
        "idx_proceeding_extractions_parcel",
        "proceeding_extractions",
        ["parcel_reference"],
        schema="staging",
    )

    # =====================================================================
    # PUBLIC SCHEMA -- Intelligence output tables
    # =====================================================================

    # --- public.evidence (validated signal evidence) ---
    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pidn", sa.Text, nullable=False),
        sa.Column("signal_key", sa.Text, nullable=False),
        sa.Column("claim", sa.Text),
        sa.Column("evidence_data", JSONB),
        sa.Column("source_url", sa.Text),
        sa.Column("internal_url", sa.Text),
        sa.Column("validation_status", sa.Text),
        sa.Column("adjusted_significance", sa.Text),
        sa.Column("validation_reasoning", sa.Text),
        sa.Column("cross_references", JSONB),
        sa.Column("validated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("pidn", "signal_key", name="uq_evidence_pidn_signal"),
        schema="public",
    )
    op.create_index(
        "idx_evidence_pidn",
        "evidence",
        ["pidn"],
        schema="public",
    )

    # --- public.parcel_briefs (intelligence briefs) ---
    op.create_table(
        "parcel_briefs",
        sa.Column("pidn", sa.Text, primary_key=True),
        sa.Column("brief_text", sa.Text),
        sa.Column("assessment", sa.Text),
        sa.Column("assessment_reasoning", sa.Text),
        sa.Column("key_questions", sa.ARRAY(sa.Text)),
        sa.Column("signal_count", sa.Integer),
        sa.Column("citations", JSONB),
        sa.Column("brief_version", sa.Integer, server_default="1"),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("pass_metadata", JSONB),
        schema="public",
    )

    # --- public.county_narratives (cross-parcel narratives) ---
    op.create_table(
        "county_narratives",
        sa.Column("narrative_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("narrative_type", sa.Text, nullable=False),
        sa.Column("trajectory", sa.Text),
        sa.Column("affected_pidns", sa.ARRAY(sa.Text)),
        sa.Column("key_entities", sa.ARRAY(sa.Text)),
        sa.Column("citations", JSONB),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        schema="public",
    )

    # --- public.entity_graph (verified entity relationships) ---
    op.create_table(
        "entity_graph",
        sa.Column("entity_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("canonical_name", sa.Text, nullable=False),
        sa.Column("entity_type", sa.Text),
        sa.Column("linked_names", sa.ARRAY(sa.Text)),
        sa.Column("linked_sources", JSONB),
        sa.Column("relationships", JSONB),
        sa.Column("verification_status", sa.Text),
        sa.Column("verification_reasoning", sa.Text),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        schema="public",
    )
    op.create_index(
        "idx_entity_graph_canonical_name",
        "entity_graph",
        ["canonical_name"],
        schema="public",
    )

    # =====================================================================
    # META SCHEMA -- Pass tracking
    # =====================================================================

    # --- meta.intelligence_passes (pass tracking) ---
    op.create_table(
        "intelligence_passes",
        sa.Column("pidn", sa.Text, nullable=False),
        sa.Column("pass_number", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("input_hash", sa.Text),
        sa.Column("error_message", sa.Text),
        sa.PrimaryKeyConstraint("pidn", "pass_number"),
        schema="meta",
    )


def downgrade() -> None:
    # Meta tables
    op.drop_table("intelligence_passes", schema="meta")

    # Public tables (reverse order)
    op.drop_index("idx_entity_graph_canonical_name", table_name="entity_graph", schema="public")
    op.drop_table("entity_graph", schema="public")
    op.drop_table("county_narratives", schema="public")
    op.drop_table("parcel_briefs", schema="public")
    op.drop_index("idx_evidence_pidn", table_name="evidence", schema="public")
    op.drop_table("evidence", schema="public")

    # Staging tables (reverse order, drop indexes first)
    op.drop_index("idx_proceeding_extractions_parcel", table_name="proceeding_extractions", schema="staging")
    op.drop_index("idx_proceeding_extractions_applicant", table_name="proceeding_extractions", schema="staging")
    op.drop_table("proceeding_extractions", schema="staging")
    op.drop_index("idx_public_proceedings_body_date", table_name="public_proceedings", schema="staging")
    op.drop_table("public_proceedings", schema="staging")
    op.drop_index("idx_corporate_entities_agent", table_name="corporate_entities", schema="staging")
    op.drop_index("idx_corporate_entities_current", table_name="corporate_entities", schema="staging")
    op.drop_table("corporate_entities", schema="staging")
