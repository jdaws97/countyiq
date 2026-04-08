"""add cross_signal_insight and partial-failure tracking to meta.intelligence_passes

Revision ID: 014
Revises: 013
Create Date: 2026-04-05

Adds columns to capture cross-signal reasoning output and partial-failure
state from batched Pass 2 validation, so that:

  1. The cross_signal_insight text produced by the LLM is persisted instead
     of being discarded (previously the prompt asked for it, spent tokens
     generating it, and the asset threw it away).

  2. Signal keys that the LLM did not return or failed to validate in a
     batched call are recorded, enabling targeted re-runs instead of
     silently losing them.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "intelligence_passes",
        sa.Column("cross_signal_insight", sa.Text, nullable=True),
        schema="meta",
    )
    op.add_column(
        "intelligence_passes",
        sa.Column("missing_signal_keys", JSONB, nullable=True),
        schema="meta",
    )
    op.add_column(
        "intelligence_passes",
        sa.Column("error_signal_keys", JSONB, nullable=True),
        schema="meta",
    )
    op.add_column(
        "intelligence_passes",
        sa.Column("signals_validated_count", sa.Integer, nullable=True),
        schema="meta",
    )


def downgrade() -> None:
    op.drop_column("intelligence_passes", "signals_validated_count", schema="meta")
    op.drop_column("intelligence_passes", "error_signal_keys", schema="meta")
    op.drop_column("intelligence_passes", "missing_signal_keys", schema="meta")
    op.drop_column("intelligence_passes", "cross_signal_insight", schema="meta")
