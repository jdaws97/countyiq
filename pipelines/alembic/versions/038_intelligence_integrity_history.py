"""add immutable intelligence history and contradiction gates

Revision ID: 038
Revises: 037
Create Date: 2026-08-31
"""

from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE meta.intelligence_inference_history (
            inference_id BIGSERIAL PRIMARY KEY,
            subject_key TEXT NOT NULL,
            pass_number SMALLINT NOT NULL CHECK (pass_number BETWEEN 0 AND 4),
            output_kind TEXT NOT NULL CHECK (output_kind IN (
                'proceeding_extraction',
                'entity_verification',
                'signal_validation',
                'parcel_brief',
                'owner_brief'
            )),
            decision_key TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            requested_model TEXT NOT NULL,
            served_model TEXT,
            provider TEXT,
            prompt_version TEXT NOT NULL,
            output_hash TEXT NOT NULL,
            decision_fingerprint TEXT NOT NULL,
            payload JSONB NOT NULL,
            citations JSONB NOT NULL DEFAULT '[]'::jsonb,
            evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
            disposition TEXT NOT NULL CHECK (disposition IN ('accepted', 'quarantined')),
            supersedes_inference_id BIGINT REFERENCES meta.intelligence_inference_history(inference_id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (jsonb_typeof(citations) = 'array'),
            CHECK (jsonb_typeof(evidence_refs) = 'array')
        );

        CREATE INDEX idx_intelligence_history_subject
            ON meta.intelligence_inference_history (
                pass_number, output_kind, subject_key, decision_key, inference_id DESC
            );
        CREATE INDEX idx_intelligence_history_source
            ON meta.intelligence_inference_history (
                pass_number, output_kind, subject_key, decision_key, source_hash
            );
        CREATE INDEX idx_intelligence_history_quarantined
            ON meta.intelligence_inference_history (created_at DESC)
            WHERE disposition = 'quarantined';

        CREATE TABLE meta.intelligence_contradictions (
            contradiction_id BIGSERIAL PRIMARY KEY,
            pass_number SMALLINT NOT NULL CHECK (pass_number BETWEEN 0 AND 4),
            output_kind TEXT NOT NULL,
            subject_key TEXT NOT NULL,
            decision_key TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            prior_inference_id BIGINT NOT NULL
                REFERENCES meta.intelligence_inference_history(inference_id),
            challenger_inference_id BIGINT NOT NULL
                REFERENCES meta.intelligence_inference_history(inference_id),
            prior_fingerprint TEXT NOT NULL,
            challenger_fingerprint TEXT NOT NULL,
            reason TEXT NOT NULL,
            detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (prior_inference_id, challenger_inference_id),
            CHECK (prior_inference_id <> challenger_inference_id)
        );

        CREATE INDEX idx_intelligence_contradictions_subject
            ON meta.intelligence_contradictions (
                pass_number, output_kind, subject_key, detected_at DESC
            );

        CREATE TABLE meta.intelligence_contradiction_resolutions (
            resolution_id BIGSERIAL PRIMARY KEY,
            contradiction_id BIGINT NOT NULL UNIQUE
                REFERENCES meta.intelligence_contradictions(contradiction_id),
            resolution TEXT NOT NULL CHECK (resolution IN (
                'accept_prior', 'accept_challenger', 'discard_both'
            )),
            resolved_by TEXT NOT NULL,
            rationale TEXT NOT NULL,
            resolved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE OR REPLACE FUNCTION meta.reject_intelligence_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME;
        END;
        $$;

        CREATE TRIGGER trg_intelligence_history_append_only
            BEFORE UPDATE OR DELETE ON meta.intelligence_inference_history
            FOR EACH ROW EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();
        CREATE TRIGGER trg_intelligence_contradictions_append_only
            BEFORE UPDATE OR DELETE ON meta.intelligence_contradictions
            FOR EACH ROW EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();
        CREATE TRIGGER trg_intelligence_resolutions_append_only
            BEFORE UPDATE OR DELETE ON meta.intelligence_contradiction_resolutions
            FOR EACH ROW EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();

        ALTER TABLE staging.proceeding_extractions
            ADD COLUMN active_inference_id BIGINT
            REFERENCES meta.intelligence_inference_history(inference_id);
        ALTER TABLE public.entity_graph
            ADD COLUMN active_inference_id BIGINT
            REFERENCES meta.intelligence_inference_history(inference_id);
        ALTER TABLE public.evidence
            ADD COLUMN active_inference_id BIGINT
            REFERENCES meta.intelligence_inference_history(inference_id);
        ALTER TABLE public.parcel_briefs
            ADD COLUMN active_inference_id BIGINT
            REFERENCES meta.intelligence_inference_history(inference_id);
        ALTER TABLE public.owner_briefs
            ADD COLUMN active_inference_id BIGINT
            REFERENCES meta.intelligence_inference_history(inference_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE public.owner_briefs DROP COLUMN IF EXISTS active_inference_id;
        ALTER TABLE public.parcel_briefs DROP COLUMN IF EXISTS active_inference_id;
        ALTER TABLE public.evidence DROP COLUMN IF EXISTS active_inference_id;
        ALTER TABLE public.entity_graph DROP COLUMN IF EXISTS active_inference_id;
        ALTER TABLE staging.proceeding_extractions DROP COLUMN IF EXISTS active_inference_id;

        DROP TRIGGER IF EXISTS trg_intelligence_resolutions_append_only
            ON meta.intelligence_contradiction_resolutions;
        DROP TRIGGER IF EXISTS trg_intelligence_contradictions_append_only
            ON meta.intelligence_contradictions;
        DROP TRIGGER IF EXISTS trg_intelligence_history_append_only
            ON meta.intelligence_inference_history;
        DROP FUNCTION IF EXISTS meta.reject_intelligence_audit_mutation();
        DROP TABLE IF EXISTS meta.intelligence_contradiction_resolutions;
        DROP TABLE IF EXISTS meta.intelligence_contradictions;
        DROP TABLE IF EXISTS meta.intelligence_inference_history;
        """
    )
