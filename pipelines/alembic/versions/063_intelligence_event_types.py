"""Allow governed policy, recommendation and scoped-decision events."""

from alembic import op

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None

_BASE = "'transfer', 'value_change', 'structure_change', 'delinquency_change', 'application', 'hearing', 'revision', 'continuance', 'approval', 'denial', 'condition', 'upcoming_decision'"
_NEW = "'policy_action', 'recommendation', 'withdrawn', 'removed', 'scoped_decision'"


def _replace(types):
    op.execute(
        "ALTER TABLE public.intelligence_events DROP CONSTRAINT chk_intelligence_events_type"
    )
    op.execute(
        "ALTER TABLE public.intelligence_events ADD CONSTRAINT chk_intelligence_events_type CHECK (event_type IN ("
        + types
        + "))"
    )


def upgrade():
    _replace(_BASE + ", " + _NEW)


def downgrade():
    # Validation intentionally refuses downgrade while newer event types remain.
    # Never silently delete or relabel source-backed customer events.
    _replace(_BASE)
