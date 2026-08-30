"""remove unused legacy metadata tables

The initial schema created three speculative observability tables that no
asset, sensor, API route, or frontend surface ever used. Dagster owns pipeline
run state in its separate database, while CountyIQ health uses live source
tables and asset checks. Keeping the empty tables implies a capability that
does not exist and invites new code to depend on a dead contract.

The upgrade refuses to discard a deployed table that contains data. Operators
must inspect and deliberately migrate any unexpected rows before retrying.

Revision ID: 030
Revises: 029
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM meta.pipeline_status LIMIT 1) THEN
                RAISE EXCEPTION
                    'refusing to drop non-empty legacy table meta.pipeline_status';
            END IF;
            IF EXISTS (SELECT 1 FROM meta.infra_metrics LIMIT 1) THEN
                RAISE EXCEPTION
                    'refusing to drop non-empty legacy table meta.infra_metrics';
            END IF;
            IF EXISTS (SELECT 1 FROM meta.data_quality_checks LIMIT 1) THEN
                RAISE EXCEPTION
                    'refusing to drop non-empty legacy table meta.data_quality_checks';
            END IF;
        END
        $$;
        """
    )
    op.drop_table("data_quality_checks", schema="meta")
    op.drop_table("infra_metrics", schema="meta")
    op.drop_table("pipeline_status", schema="meta")


def downgrade() -> None:
    op.create_table(
        "pipeline_status",
        sa.Column("source_name", sa.Text, primary_key=True),
        sa.Column("schedule_type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("duration_seconds", sa.Integer),
        sa.Column("record_count", sa.Integer),
        sa.Column("prev_record_count", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("next_scheduled_run", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="meta",
    )
    op.create_check_constraint(
        "chk_schedule_type",
        "pipeline_status",
        "schedule_type IN ('daily', 'weekly', 'monthly', 'on_demand')",
        schema="meta",
    )
    op.create_check_constraint(
        "chk_status",
        "pipeline_status",
        "status IN ('SUCCESS', 'FAILURE', 'IN_PROGRESS')",
        schema="meta",
    )
    op.create_check_constraint(
        "chk_duration",
        "pipeline_status",
        "duration_seconds >= 0",
        schema="meta",
    )
    op.create_check_constraint(
        "chk_record_count",
        "pipeline_status",
        "record_count >= 0",
        schema="meta",
    )
    op.create_check_constraint(
        "chk_prev_count",
        "pipeline_status",
        "prev_record_count >= 0",
        schema="meta",
    )

    op.create_table(
        "infra_metrics",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("metrics", JSONB, nullable=False),
        schema="meta",
    )
    op.create_index(
        "idx_infra_metrics_checked",
        "infra_metrics",
        ["checked_at"],
        schema="meta",
    )

    op.create_table(
        "data_quality_checks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("check_name", sa.Text, nullable=False),
        sa.Column("passed", sa.Boolean, nullable=False),
        sa.Column("details", sa.Text),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="meta",
    )
    op.create_check_constraint(
        "chk_check_name",
        "data_quality_checks",
        "check_name IN ('record_count_nonzero', 'schema_valid', 'freshness_ok', "
        "'row_count_delta')",
        schema="meta",
    )
    op.create_index(
        "idx_dq_checks_source",
        "data_quality_checks",
        ["source_name", sa.text("checked_at DESC")],
        schema="meta",
    )
