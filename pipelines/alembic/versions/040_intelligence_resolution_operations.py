"""add operable intelligence contradiction resolution and health

Revision ID: 040
Revises: 039
Create Date: 2026-08-31
"""

from alembic import op

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE meta.intelligence_inference_history
            ADD COLUMN decision_origin TEXT NOT NULL DEFAULT 'model'
                CHECK (decision_origin IN (
                    'model', 'human_resolution', 'legacy_unverified'
                )),
            ADD COLUMN resolution_source_inference_id BIGINT
                REFERENCES meta.intelligence_inference_history(inference_id);

        ALTER TABLE meta.intelligence_contradiction_resolutions
            ADD COLUMN resolved_inference_id BIGINT
                REFERENCES meta.intelligence_inference_history(inference_id);

        -- Rows created before revision 038 cannot prove that they crossed the
        -- current evidence/citation gates. Preserve their exact payloads in the
        -- immutable ledger, then fail closed by retracting those projections.
        WITH legacy AS (
            SELECT
                'proceeding:' || proceeding_id AS subject_key,
                proceeding_id,
                jsonb_build_object(
                    'extractions', jsonb_agg(
                        to_jsonb(pe) - 'active_inference_id'
                        ORDER BY pe.id
                    )
                ) AS payload,
                COALESCE(MAX(model_used), 'legacy-unknown') AS model_used,
                COALESCE(
                    jsonb_agg(supporting_text) FILTER (WHERE supporting_text IS NOT NULL),
                    '[]'::jsonb
                ) AS citations
            FROM staging.proceeding_extractions pe
            WHERE active_inference_id IS NULL
            GROUP BY proceeding_id
        )
        INSERT INTO meta.intelligence_inference_history (
            subject_key, pass_number, output_kind, decision_key,
            source_hash, input_hash, requested_model, prompt_version,
            output_hash, decision_fingerprint, payload, citations,
            evidence_refs, disposition, decision_origin
        )
        SELECT
            subject_key, 0, 'proceeding_extraction', 'legacy_document',
            'legacy-unverified:' || proceeding_id,
            'legacy-unverified:' || proceeding_id,
            model_used, 'legacy-unverified', md5(payload::text), md5(payload::text),
            payload, citations, '[]'::jsonb, 'quarantined', 'legacy_unverified'
        FROM legacy;

        INSERT INTO meta.intelligence_inference_history (
            subject_key, pass_number, output_kind, decision_key,
            source_hash, input_hash, requested_model, prompt_version,
            output_hash, decision_fingerprint, payload, citations,
            evidence_refs, disposition, decision_origin
        )
        SELECT
            'legacy-entity:' || entity_id, 1, 'entity_verification', 'legacy_entity',
            'legacy-unverified:' || entity_id, 'legacy-unverified:' || entity_id,
            'legacy-unknown', 'legacy-unverified',
            md5((to_jsonb(eg) - 'active_inference_id')::text),
            md5((to_jsonb(eg) - 'active_inference_id')::text),
            to_jsonb(eg) - 'active_inference_id', '[]'::jsonb, '[]'::jsonb,
            'quarantined', 'legacy_unverified'
        FROM public.entity_graph eg
        WHERE active_inference_id IS NULL;

        INSERT INTO meta.intelligence_inference_history (
            subject_key, pass_number, output_kind, decision_key,
            source_hash, input_hash, requested_model, prompt_version,
            output_hash, decision_fingerprint, payload, citations,
            evidence_refs, disposition, decision_origin
        )
        SELECT
            pidn, 2, 'signal_validation', 'legacy_signal:' || signal_key,
            'legacy-unverified:' || id, 'legacy-unverified:' || id,
            COALESCE(model_version, 'legacy-unknown'),
            COALESCE(prompt_version, 'legacy-unverified'),
            md5((to_jsonb(e) - 'active_inference_id')::text),
            md5((to_jsonb(e) - 'active_inference_id')::text),
            to_jsonb(e) - 'active_inference_id', '[]'::jsonb,
            COALESCE(cross_references, '[]'::jsonb),
            'quarantined', 'legacy_unverified'
        FROM public.evidence e
        WHERE active_inference_id IS NULL;

        INSERT INTO meta.intelligence_inference_history (
            subject_key, pass_number, output_kind, decision_key,
            source_hash, input_hash, requested_model, prompt_version,
            output_hash, decision_fingerprint, payload, citations,
            evidence_refs, disposition, decision_origin
        )
        SELECT
            pidn, 3, 'parcel_brief', 'legacy_brief',
            'legacy-unverified:' || pidn, 'legacy-unverified:' || pidn,
            COALESCE(model_version, 'legacy-unknown'),
            COALESCE(prompt_version, 'legacy-unverified'),
            md5((to_jsonb(pb) - 'active_inference_id')::text),
            md5((to_jsonb(pb) - 'active_inference_id')::text),
            to_jsonb(pb) - 'active_inference_id',
            COALESCE(citations, '[]'::jsonb), '[]'::jsonb,
            'quarantined', 'legacy_unverified'
        FROM public.parcel_briefs pb
        WHERE active_inference_id IS NULL;

        INSERT INTO meta.intelligence_inference_history (
            subject_key, pass_number, output_kind, decision_key,
            source_hash, input_hash, requested_model, prompt_version,
            output_hash, decision_fingerprint, payload, citations,
            evidence_refs, disposition, decision_origin
        )
        SELECT
            'legacy-owner:' || md5(canonical_name),
            3, 'owner_brief', 'legacy_brief',
            'legacy-unverified:' || md5(canonical_name),
            'legacy-unverified:' || md5(canonical_name),
            COALESCE(model_version, 'legacy-unknown'),
            COALESCE(prompt_version, 'legacy-unverified'),
            md5((to_jsonb(ob) - 'active_inference_id')::text),
            md5((to_jsonb(ob) - 'active_inference_id')::text),
            to_jsonb(ob) - 'active_inference_id',
            COALESCE(citations, '[]'::jsonb),
            COALESCE(parcel_citations, '[]'::jsonb),
            'quarantined', 'legacy_unverified'
        FROM public.owner_briefs ob
        WHERE active_inference_id IS NULL;

        DELETE FROM staging.proceeding_extractions WHERE active_inference_id IS NULL;
        DELETE FROM public.entity_graph WHERE active_inference_id IS NULL;
        DELETE FROM public.evidence WHERE active_inference_id IS NULL;
        DELETE FROM public.parcel_briefs WHERE active_inference_id IS NULL;
        DELETE FROM public.owner_briefs WHERE active_inference_id IS NULL;

        CREATE VIEW meta.intelligence_integrity_status AS
        WITH projection_refs AS (
            SELECT 0::smallint AS expected_pass,
                   'proceeding_extraction'::text AS expected_kind,
                   active_inference_id
            FROM staging.proceeding_extractions
            UNION ALL
            SELECT 1::smallint, 'entity_verification'::text, active_inference_id
            FROM public.entity_graph
            UNION ALL
            SELECT 2::smallint, 'signal_validation'::text, active_inference_id
            FROM public.evidence
            UNION ALL
            SELECT 3::smallint, 'parcel_brief'::text, active_inference_id
            FROM public.parcel_briefs
            UNION ALL
            SELECT 3::smallint, 'owner_brief'::text, active_inference_id
            FROM public.owner_briefs
        ),
        projection_health AS (
            SELECT
                COUNT(*) AS projection_count,
                COUNT(*) FILTER (
                    WHERE refs.active_inference_id IS NULL
                ) AS unlinked_projection_count,
                COUNT(*) FILTER (
                    WHERE refs.active_inference_id IS NOT NULL
                      AND (
                          history.inference_id IS NULL
                          OR history.disposition <> 'accepted'
                          OR history.pass_number <> refs.expected_pass
                          OR history.output_kind <> refs.expected_kind
                      )
                ) AS projection_mismatch_count
            FROM projection_refs refs
            LEFT JOIN meta.intelligence_inference_history history
              ON history.inference_id = refs.active_inference_id
        ),
        history_health AS (
            SELECT
                COUNT(*) AS history_count,
                COUNT(*) FILTER (WHERE disposition = 'accepted') AS accepted_count,
                COUNT(*) FILTER (WHERE disposition = 'quarantined') AS quarantined_count,
                COUNT(*) FILTER (
                    WHERE decision_origin = 'human_resolution'
                ) AS human_resolution_inference_count
            FROM meta.intelligence_inference_history
        ),
        contradiction_health AS (
            SELECT
                COUNT(*) AS contradiction_count,
                COUNT(*) FILTER (
                    WHERE resolutions.contradiction_id IS NULL
                ) AS unresolved_contradiction_count,
                COUNT(resolutions.contradiction_id) AS resolved_contradiction_count,
                MIN(contradictions.detected_at) FILTER (
                    WHERE resolutions.contradiction_id IS NULL
                ) AS oldest_unresolved_at
            FROM meta.intelligence_contradictions contradictions
            LEFT JOIN meta.intelligence_contradiction_resolutions resolutions
              USING (contradiction_id)
        )
        SELECT
            history_health.history_count,
            history_health.accepted_count,
            history_health.quarantined_count,
            history_health.human_resolution_inference_count,
            contradiction_health.contradiction_count,
            contradiction_health.unresolved_contradiction_count,
            contradiction_health.resolved_contradiction_count,
            contradiction_health.oldest_unresolved_at,
            projection_health.projection_count,
            projection_health.unlinked_projection_count,
            projection_health.projection_mismatch_count
        FROM history_health, contradiction_health, projection_health;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP VIEW IF EXISTS meta.intelligence_integrity_status;
        ALTER TABLE meta.intelligence_contradiction_resolutions
            DROP COLUMN IF EXISTS resolved_inference_id;
        ALTER TABLE meta.intelligence_inference_history
            DROP COLUMN IF EXISTS resolution_source_inference_id,
            DROP COLUMN IF EXISTS decision_origin;
        """
    )
