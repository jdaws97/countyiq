"""Auto-resolution ledger, review queue, and sampled audit reviews.

Revision ID: 047
Revises: 046
Create Date: 2026-09-02

Contradictions used to wait for a human CLI resolution one by one. Now a
deterministic policy (plus an optional judge model) resolves the routine ones
and records every decision here; only consequential flips and rule-versus-judge
disagreements stay in the human queue. Sampled audit reviews of accepted
outputs are recorded in the same append-only style and feed the eval corpus.
"""

from alembic import op

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE meta.intelligence_inference_history
            DROP CONSTRAINT IF EXISTS intelligence_inference_history_decision_origin_check;
        ALTER TABLE meta.intelligence_inference_history
            ADD CONSTRAINT intelligence_inference_history_decision_origin_check
            CHECK (decision_origin IN (
                'model', 'human_resolution', 'auto_resolution', 'legacy_unverified'
            ));

        CREATE TABLE meta.intelligence_auto_resolutions (
            auto_resolution_id BIGSERIAL PRIMARY KEY,
            contradiction_id BIGINT NOT NULL
                REFERENCES meta.intelligence_contradictions(contradiction_id),
            assessment JSONB NOT NULL,
            consequential BOOLEAN NOT NULL,
            version_upgrade BOOLEAN NOT NULL,
            rule_default TEXT NOT NULL CHECK (rule_default IN (
                'accept_prior', 'accept_challenger'
            )),
            judge_model TEXT,
            judge_verdict TEXT CHECK (judge_verdict IN ('prior', 'challenger', 'unclear')),
            judge_confidence DOUBLE PRECISION,
            judge_reason TEXT,
            outcome TEXT NOT NULL CHECK (outcome IN (
                'auto_resolved', 'queued_consequential', 'queued_disagreement',
                'queued_judge_unavailable'
            )),
            -- Deliberately not a foreign key: the resolutions ledger is
            -- protected by append-only triggers, and a referencing FK would
            -- turn its TRUNCATE guard into a different error class.
            resolution_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_intelligence_auto_resolutions_contradiction
            ON meta.intelligence_auto_resolutions (contradiction_id, auto_resolution_id DESC);
        CREATE TRIGGER trg_intelligence_auto_resolutions_append_only
            BEFORE UPDATE OR DELETE ON meta.intelligence_auto_resolutions
            FOR EACH ROW EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();

        CREATE TABLE meta.intelligence_audit_reviews (
            review_id BIGSERIAL PRIMARY KEY,
            inference_id BIGINT NOT NULL
                REFERENCES meta.intelligence_inference_history(inference_id),
            verdict TEXT NOT NULL CHECK (verdict IN ('approved', 'rejected')),
            reviewer TEXT NOT NULL,
            notes TEXT,
            sampled_reason TEXT,
            gold_candidate_path TEXT,
            reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_intelligence_audit_reviews_inference
            ON meta.intelligence_audit_reviews (inference_id, review_id DESC);
        CREATE TRIGGER trg_intelligence_audit_reviews_append_only
            BEFORE UPDATE OR DELETE ON meta.intelligence_audit_reviews
            FOR EACH ROW EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();

        -- The human queue: unresolved contradictions with the reason the policy
        -- left them for a person, oldest first.
        CREATE VIEW meta.intelligence_review_queue AS
        SELECT
            c.contradiction_id, c.pass_number, c.output_kind, c.subject_key,
            c.detected_at,
            latest_auto.outcome AS queue_reason,
            latest_auto.assessment,
            latest_auto.judge_verdict,
            latest_auto.judge_reason
        FROM meta.intelligence_contradictions c
        LEFT JOIN meta.intelligence_contradiction_resolutions r USING (contradiction_id)
        LEFT JOIN LATERAL (
            SELECT outcome, assessment, judge_verdict, judge_reason
            FROM meta.intelligence_auto_resolutions a
            WHERE a.contradiction_id = c.contradiction_id
            ORDER BY a.auto_resolution_id DESC
            LIMIT 1
        ) latest_auto ON TRUE
        WHERE r.contradiction_id IS NULL
        ORDER BY c.detected_at, c.contradiction_id;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP VIEW IF EXISTS meta.intelligence_review_queue;
        DROP TRIGGER IF EXISTS trg_intelligence_audit_reviews_append_only
            ON meta.intelligence_audit_reviews;
        DROP TABLE IF EXISTS meta.intelligence_audit_reviews;
        DROP TRIGGER IF EXISTS trg_intelligence_auto_resolutions_append_only
            ON meta.intelligence_auto_resolutions;
        DROP TABLE IF EXISTS meta.intelligence_auto_resolutions;
        ALTER TABLE meta.intelligence_inference_history
            DROP CONSTRAINT IF EXISTS intelligence_inference_history_decision_origin_check;
        ALTER TABLE meta.intelligence_inference_history
            ADD CONSTRAINT intelligence_inference_history_decision_origin_check
            CHECK (decision_origin IN (
                'model', 'human_resolution', 'legacy_unverified'
            ));
        """
    )
