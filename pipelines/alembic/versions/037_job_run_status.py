"""persist latest Dagster job outcomes for application health

Revision ID: 037
Revises: 036
Create Date: 2026-08-30
"""

from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE meta.job_run_status (
            job_name TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('success', 'failure')),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ NOT NULL,
            last_success_at TIMESTAMPTZ,
            error_message TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS meta.job_run_status")
