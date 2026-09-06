"""owner briefs: portfolio-level intelligence output (Pass 3 owner-rollup)

Adds ``public.owner_briefs`` — one row per resolved owner with a
portfolio-level narrative, structured recommendation/urgency/strategy
fields, and the same trust metadata as parcel_briefs (model_version,
prompt_version, confidence).

Keyed on ``canonical_name``, NOT ``owner_id``: ``public.owners`` is
truncated and rebuilt (sequence restarted) on every owner_resolution
run, so owner_id is not stable across runs and an FK into it would make
the rebuild fail once a brief exists. ``owner_id`` is stored as a
convenience column refreshed on each upsert.

Evidence: ``docs/decisions.md`` — owner rollup won
4/4 blind judge runs on pattern_insight (1.00 → 4.75).

Revision ID: 022
Revises: 021
Create Date: 2026-04-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owner_briefs",
        sa.Column("canonical_name", sa.Text(), primary_key=True),
        sa.Column("owner_id", sa.Integer()),
        sa.Column("brief_text", sa.Text()),
        sa.Column(
            "portfolio_strategy", sa.Text()
        ),  # accumulator|flipper|holder|distressed|institutional|unclear
        sa.Column("concentration_notes", sa.Text()),
        sa.Column("key_pattern", sa.Text()),
        sa.Column(
            "recommendation", sa.Text()
        ),  # pursue_acquisition|monitor|compete|none
        sa.Column("urgency", sa.Text()),
        sa.Column("top_risk", sa.Text()),
        sa.Column("evidence_strength", sa.Text()),  # strong|moderate|weak
        sa.Column("citations", JSONB()),
        sa.Column("parcel_citations", JSONB()),
        sa.Column("n_parcels", sa.Integer()),
        sa.Column("model_version", sa.Text()),
        sa.Column("prompt_version", sa.Text()),
        sa.Column("n_trials", sa.Integer()),
        sa.Column("trial_agreement", sa.Numeric(3, 2)),
        sa.Column("confidence", sa.Numeric(3, 2)),
        sa.Column("brief_version", sa.Integer(), server_default="1"),
        sa.Column("pass_metadata", JSONB()),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="owner_briefs_confidence_01",
        ),
        sa.CheckConstraint(
            "trial_agreement IS NULL OR (trial_agreement >= 0 AND trial_agreement <= 1)",
            name="owner_briefs_agreement_01",
        ),
        schema="public",
    )

    op.create_index(
        "idx_owner_briefs_confidence",
        "owner_briefs",
        ["confidence"],
        schema="public",
        postgresql_where=sa.text("confidence IS NOT NULL"),
    )
    op.create_index(
        "idx_owner_briefs_strategy",
        "owner_briefs",
        ["portfolio_strategy"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("idx_owner_briefs_strategy", "owner_briefs", schema="public")
    op.drop_index("idx_owner_briefs_confidence", "owner_briefs", schema="public")
    op.drop_table("owner_briefs", schema="public")
