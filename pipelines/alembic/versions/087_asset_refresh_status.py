"""Record source asset outcomes independently of grouped Dagster runs."""

from alembic import op

revision = "087"
down_revision = "086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE meta.asset_refresh_status (
            asset_key text PRIMARY KEY,
            job_name text NOT NULL,
            run_id text NOT NULL,
            status text NOT NULL CHECK (status IN ('success', 'failure')),
            finished_at timestamptz NOT NULL,
            last_success_at timestamptz,
            record_count bigint CHECK (record_count >= 0),
            failure_reason text CHECK (
                failure_reason IN ('step_failed', 'empty_result', 'unverified_result')
            ),
            updated_at timestamptz NOT NULL DEFAULT NOW(),
            CHECK (
                (status = 'success' AND record_count IS NOT NULL
                    AND record_count > 0 AND last_success_at IS NOT NULL
                    AND failure_reason IS NULL)
                OR (status = 'failure' AND failure_reason IS NOT NULL)
            )
        );
        COMMENT ON TABLE meta.asset_refresh_status IS
            'Latest source asset attempt and latest verified nonempty materialization. '
            'A successful sibling asset does not inherit another step failure. '
            'Timestamps describe acquisition, not source publication or map effectiveness.';
    """)


def downgrade() -> None:
    op.execute("DROP TABLE meta.asset_refresh_status")
