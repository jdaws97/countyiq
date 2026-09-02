"""Track when a PA DOS name was last re-queried, independent of its SCD2 version.

Revision ID: 046
Revises: 045
Create Date: 2026-09-02

The PA DOS refresh selects owner names whose current record is older than a
TTL. Unchanged records never received a new SCD2 version, so their
``valid_from`` never advanced: once more names had aged past the TTL than the
per-run cap, the same alphabetical prefix was re-queried on every run and later
owner names were never looked up. ``last_checked_at`` is refreshed in place by
the loader on every lookup and drives the TTL instead.
"""

import sqlalchemy as sa
from alembic import op

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "corporate_entities",
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        schema="staging",
    )
    # Existing rows were checked when they were written.
    op.execute(
        "UPDATE staging.corporate_entities SET last_checked_at = valid_from "
        "WHERE last_checked_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("corporate_entities", "last_checked_at", schema="staging")
