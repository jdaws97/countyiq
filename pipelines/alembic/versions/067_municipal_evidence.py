"""Allow immutable municipal source selections in the inference ledger.

The existing ledger supplies history and contradiction protection. Serving
selects the latest accepted document read only while its source is current;
there is no second copy of the cards to synchronize.
"""

from alembic import op

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None


def _replace_constraint(include_evidence: bool) -> None:
    kinds = [
        "proceeding_extraction",
        "entity_verification",
        "signal_validation",
        "parcel_brief",
        "owner_brief",
    ]
    if include_evidence:
        kinds.append("municipal_evidence")
    allowed = ", ".join("'" + value + "'" for value in kinds)
    op.execute(
        "ALTER TABLE meta.intelligence_inference_history DROP CONSTRAINT "
        "intelligence_inference_history_output_kind_check"
    )
    op.execute(
        "ALTER TABLE meta.intelligence_inference_history ADD CONSTRAINT "
        "intelligence_inference_history_output_kind_check CHECK "
        "(output_kind IN (" + allowed + "))"
    )


def upgrade() -> None:
    _replace_constraint(True)


def downgrade() -> None:
    # Refuse to discard or relabel immutable evidence when reverting.
    _replace_constraint(False)
