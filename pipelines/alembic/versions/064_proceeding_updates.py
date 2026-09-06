"""Allow source-backed municipal updates alongside scoped decisions.

Existing rows are unchanged. Downgrade deliberately refuses while newer event
types remain; operators must review those projections before reverting code.
"""

from alembic import op

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None

LEGACY_TYPES = (
    "transfer",
    "value_change",
    "structure_change",
    "delinquency_change",
    "application",
    "hearing",
    "revision",
    "continuance",
    "approval",
    "denial",
    "condition",
    "upcoming_decision",
)
NEW_TYPES = (
    "policy_action",
    "recommendation",
    "update",
    "withdrawn",
    "removed",
    "scoped_decision",
)


def _replace(types):
    allowed = ", ".join("'" + value + "'" for value in types)
    op.execute(
        "ALTER TABLE public.intelligence_events DROP CONSTRAINT chk_intelligence_events_type"
    )
    op.execute(
        "ALTER TABLE public.intelligence_events ADD CONSTRAINT "
        "chk_intelligence_events_type CHECK (event_type IN (" + allowed + "))"
    )


def upgrade():
    _replace(LEGACY_TYPES + NEW_TYPES)


def downgrade():
    # Restores revision 063 and fails atomically while update records exist.
    # Do not silently relabel source-backed updates during rollback.
    _replace(LEGACY_TYPES + tuple(value for value in NEW_TYPES if value != "update"))
