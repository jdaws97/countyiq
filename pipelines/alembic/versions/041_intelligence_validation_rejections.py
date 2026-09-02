"""add immutable intelligence validation rejection telemetry

Revision ID: 041
Revises: 040
Create Date: 2026-08-31
"""

from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE meta.intelligence_validation_rejections (
            rejection_id BIGSERIAL PRIMARY KEY,
            subject_key TEXT NOT NULL,
            pass_number SMALLINT NOT NULL CHECK (pass_number BETWEEN 0 AND 3),
            output_kind TEXT NOT NULL CHECK (output_kind IN (
                'proceeding_extraction', 'entity_verification',
                'signal_validation', 'parcel_brief', 'owner_brief'
            )),
            source_hash TEXT,
            input_hash TEXT,
            requested_model TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            validation_errors JSONB NOT NULL,
            rejected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (jsonb_typeof(validation_errors) = 'array'),
            CHECK (jsonb_array_length(validation_errors) > 0)
        );

        CREATE INDEX idx_intelligence_validation_rejections_recent
            ON meta.intelligence_validation_rejections (rejected_at DESC);
        CREATE INDEX idx_intelligence_validation_rejections_subject
            ON meta.intelligence_validation_rejections (
                pass_number, output_kind, subject_key, rejection_id DESC
            );

        CREATE TRIGGER trg_intelligence_validation_rejections_append_only
            BEFORE UPDATE OR DELETE ON meta.intelligence_validation_rejections
            FOR EACH ROW EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();
        CREATE TRIGGER trg_intelligence_validation_rejections_no_truncate
            BEFORE TRUNCATE ON meta.intelligence_validation_rejections
            FOR EACH STATEMENT EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();

        CREATE VIEW meta.intelligence_validation_rejection_status AS
        SELECT
            COUNT(*) AS rejection_count,
            COUNT(*) FILTER (
                WHERE rejected_at >= NOW() - INTERVAL '24 hours'
            ) AS rejections_last_24h,
            MAX(rejected_at) AS latest_rejection_at
        FROM meta.intelligence_validation_rejections;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP VIEW IF EXISTS meta.intelligence_validation_rejection_status;
        DROP TRIGGER IF EXISTS trg_intelligence_validation_rejections_no_truncate
            ON meta.intelligence_validation_rejections;
        DROP TRIGGER IF EXISTS trg_intelligence_validation_rejections_append_only
            ON meta.intelligence_validation_rejections;
        DROP TABLE IF EXISTS meta.intelligence_validation_rejections;
        """
    )
