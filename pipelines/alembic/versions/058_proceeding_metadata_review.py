"""Quarantine additional wrong-county sources and record metadata review provenance."""
from alembic import op

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE staging.public_proceedings
            ADD COLUMN metadata_quality JSONB NOT NULL DEFAULT '{"status":"unreviewed"}'::jsonb,
            ADD CONSTRAINT proceeding_metadata_status CHECK (
                metadata_quality->>'status' IS NOT NULL AND
                metadata_quality->>'status' IN ('unreviewed','ready','review_required','quarantined')
            );
        CREATE TABLE meta.proceeding_metadata_reviews (
            id BIGSERIAL PRIMARY KEY,
            proceeding_id INTEGER NOT NULL REFERENCES staging.public_proceedings(id),
            replacement_id INTEGER REFERENCES staging.public_proceedings(id),
            review_version TEXT NOT NULL,
            source_fingerprint TEXT NOT NULL,
            original_metadata JSONB NOT NULL,
            review JSONB NOT NULL,
            action TEXT NOT NULL CHECK (action IN ('annotated','superseded','quarantined')),
            reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (proceeding_id, review_version, source_fingerprint)
        );
        CREATE FUNCTION meta.proceeding_metadata_review_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Proceeding metadata reviews are append-only';
        END;
        $$;
        CREATE TRIGGER proceeding_metadata_review_immutable
            BEFORE UPDATE OR DELETE ON meta.proceeding_metadata_reviews
            FOR EACH ROW EXECUTE FUNCTION meta.proceeding_metadata_review_immutable();
        UPDATE meta.municipality_source_rights
        SET rights_status = 'paused', acquisition_allowed = FALSE,
            derived_product_allowed = FALSE, raw_export_allowed = FALSE,
            allowed_methods = ARRAY[]::TEXT[],
            evidence = evidence || jsonb_build_object(
                'jurisdiction_reviewed_on', '2026-09-04',
                'jurisdiction_review', 'Windsor configured source is Eaton County Michigan; Jackson configured source is Huntingdon County Pennsylvania, not York County',
                'replacement_identity_windsor', 'https://windsortwp.com/',
                'replacement_identity_jackson', 'https://jacksontwpyork.org/'
            ),
            notes = concat_ws(E'\\n', notes,
                'Wrong-jurisdiction source paused. Retain evidence; replacement collection requires separate source review.'),
            updated_at = NOW()
        WHERE source_key IN (
            'windsor_twp_board_of_supervisors', 'windsor_twp_planning_commission',
            'jackson_twp_board_of_supervisors'
        );
    """)


def downgrade() -> None:
    raise RuntimeError("Metadata history and wrong-county source protections require a forward migration.")
