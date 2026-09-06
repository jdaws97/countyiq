"""Add an index for the mapped-address fuzzy search expression.

Revision ID: 044
Revises: 043
Create Date: 2026-09-01
"""

from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


ADDRESS_EXPRESSION = """
    (COALESCE(add_number::text, '') || ' ' ||
     COALESCE(street_name, '') || ' ' ||
     COALESCE(st_pos_typ, ''))
"""


def upgrade() -> None:
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_address_points_search_trgm
        ON staging.address_points
        USING gin ({ADDRESS_EXPRESSION} gin_trgm_ops)
        WHERE valid_to IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS staging.idx_address_points_search_trgm")
