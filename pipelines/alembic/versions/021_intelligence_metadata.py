"""intelligence metadata: confidence, versioning, trial agreement

Adds trust-metadata columns to evidence, parcel_briefs, and county_narratives
so every AI-derived output carries generated_at, model_version, prompt_version,
n_trials, trial_agreement, and a derived confidence score. See
``docs/decisions.md`` for the evidence behind this change.

Revision ID: 021
Revises: 020
Create Date: 2026-04-19
"""

from alembic import op
import sqlalchemy as sa


revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


# -----------------------------------------------------------------------------
# Shared columns — attached to every AI-derived output table.
# -----------------------------------------------------------------------------

_COMMON_COLUMNS = [
    ("model_version",  sa.Text(),                           True),
    ("prompt_version", sa.Text(),                           True),
    ("n_trials",       sa.Integer(),                        True),
    ("trial_agreement", sa.Numeric(3, 2),                   True),
    ("confidence",     sa.Numeric(3, 2),                    True),
]


def _add(table: str, schema: str = "public") -> None:
    for name, col_type, nullable in _COMMON_COLUMNS:
        op.add_column(table, sa.Column(name, col_type, nullable=nullable), schema=schema)


def _drop(table: str, schema: str = "public") -> None:
    for name, _, _ in reversed(_COMMON_COLUMNS):
        op.drop_column(table, name, schema=schema)


def upgrade() -> None:
    # evidence already has validated_at; add the trust columns.
    _add("evidence")

    # parcel_briefs already has generated_at; add the trust columns.
    _add("parcel_briefs")

    # county_narratives — keep parity so the ops dashboard can render a
    # uniform confidence badge across pass outputs.
    _add("county_narratives")

    # CHECK constraints — keep values coherent even if a future bug tries
    # to write negatives or >1.
    for tbl in ("evidence", "parcel_briefs", "county_narratives"):
        op.create_check_constraint(
            f"{tbl}_n_trials_nonneg",
            tbl,
            "n_trials IS NULL OR n_trials >= 0",
            schema="public",
        )
        op.create_check_constraint(
            f"{tbl}_agreement_01",
            tbl,
            "trial_agreement IS NULL OR (trial_agreement >= 0 AND trial_agreement <= 1)",
            schema="public",
        )
        op.create_check_constraint(
            f"{tbl}_confidence_01",
            tbl,
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            schema="public",
        )

    # Index on confidence for dashboard filtering ("show me only high-confidence rows").
    op.create_index(
        "idx_evidence_confidence",
        "evidence",
        ["confidence"],
        schema="public",
        postgresql_where=sa.text("confidence IS NOT NULL"),
    )
    op.create_index(
        "idx_parcel_briefs_confidence",
        "parcel_briefs",
        ["confidence"],
        schema="public",
        postgresql_where=sa.text("confidence IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_parcel_briefs_confidence", "parcel_briefs", schema="public")
    op.drop_index("idx_evidence_confidence", "evidence", schema="public")

    for tbl in ("county_narratives", "parcel_briefs", "evidence"):
        op.drop_constraint(f"{tbl}_confidence_01", tbl, schema="public")
        op.drop_constraint(f"{tbl}_agreement_01", tbl, schema="public")
        op.drop_constraint(f"{tbl}_n_trials_nonneg", tbl, schema="public")

    _drop("county_narratives")
    _drop("parcel_briefs")
    _drop("evidence")
