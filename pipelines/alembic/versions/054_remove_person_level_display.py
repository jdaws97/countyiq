"""Remove the person-level display switch.

Revision ID: 054
Revises: 053
Create Date: 2026-09-03

Product decision (docs/decisions.md, "Owner names are public record"): county
parcel owner names, previous owners, mailing addresses, and proceeding
applicants are public assessment and meeting records, and CountyIQ shows
them. The per-source ``person_level_display_allowed`` switch existed to hold
that display behind a terms review. The review concluded the names are
public, and the switch is removed rather than flipped so no route can
silently withhold owner identity again. ``derived_product_allowed`` remains
the single serving gate; exact tax-claim balances stay behind the separate
restricted-distress setting because that is debt detail, not identity.
"""

from alembic import op

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None

_TABLES = (
    "meta.source_rights",
    "meta.municipality_source_rights",
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"ALTER TABLE {table} DROP COLUMN IF EXISTS person_level_display_allowed;"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"""
            ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS person_level_display_allowed
                    BOOLEAN NOT NULL DEFAULT FALSE;
            """
        )
