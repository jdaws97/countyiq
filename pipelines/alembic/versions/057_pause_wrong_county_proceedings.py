"""Pause misidentified municipal sources without deleting retained evidence."""

from alembic import op

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE meta.municipality_source_rights
        SET rights_status = 'paused',
            acquisition_allowed = FALSE,
            derived_product_allowed = FALSE,
            raw_export_allowed = FALSE,
            allowed_methods = ARRAY[]::TEXT[],
            evidence = evidence || jsonb_build_object(
                'jurisdiction_reviewed_on', '2026-09-04',
                'jurisdiction_review', 'Configured Penn domain is Butler County; configured Paradise domain is Lancaster County, not York',
                'jurisdiction_evidence_penn', 'https://penntownship.org/',
                'jurisdiction_evidence_paradise', 'https://paradisetownship.org/wp-content/uploads/2025/02/ZHB-Notice-01152026.pdf'
            ),
            notes = concat_ws(E'\n', notes,
                'Paused for wrong-county source identity. Preserve raw evidence. Resume only after reviewed York sources and affected records/derivatives are repaired.'),
            updated_at = NOW()
        WHERE source_key IN (
            'penn_twp_board_of_supervisors', 'penn_twp_planning_commission',
            'penn_twp_zoning_hearing_board', 'paradise_twp_board_of_supervisors',
            'paradise_twp_planning_commission', 'paradise_twp_zoning_hearing_board'
        );
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Wrong-county source use cannot be restored by downgrade; repair and re-review in a forward migration."
    )
