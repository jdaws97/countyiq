"""Canonical parcel-reference normalization for proceeding linking.

Revision ID: 053
Revises: 052
Create Date: 2026-09-03

York PIDNs are alphanumeric: 72,083 of 175,928 current parcels carry a
letter in the map or sub-parcel position (``20000NC0073A0``). The municipal
proceeding linkers compared ``REGEXP_REPLACE(parcel_reference, '[^0-9]', '')``
to ``staging.parcels.pidn``, so a minute that cited one of those parcels by
PIDN could never link, in the ``municipal_action`` signal, the intelligence
ledger, Pass 2 revalidation, or the property page.

``public.normalize_parcel_reference`` gives every linker one rule:

* strip a leading label ("Parcel ID:", "Tax Map No.", "PIDN #");
* keep letters and digits, upper-cased;
* fold the 18-character tax-claim form (13-character PIDN plus a 5-character
  unit suffix) back to the 13-character PIDN.

An expression index on current extractions backs the per-parcel property
page lookup.
"""

from alembic import op

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION public.normalize_parcel_reference(raw text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE STRICT PARALLEL SAFE
        AS $fn$
            WITH compact AS (
                SELECT regexp_replace(
                    regexp_replace(
                        upper(raw),
                        -- Plain groups only: SQLAlchemy would read "(?:" as a bind parameter.
                        '^\s*(TAX\s+)?(UNIFORM\s+)?(PARCEL|PIDN|MAP)?\s*(IDENTIFIER|ID|NUMBER|NO\.?|#)?\s*[:#\-]?\s*',
                        ''
                    ),
                    '[^A-Z0-9]',
                    '',
                    'g'
                ) AS value
            )
            SELECT NULLIF(
                CASE WHEN length(value) = 18 THEN left(value, 13) ELSE value END,
                ''
            )
            FROM compact
        $fn$;

        CREATE INDEX IF NOT EXISTS idx_proceeding_extractions_normalized_reference
            ON staging.proceeding_extractions (public.normalize_parcel_reference(parcel_reference))
            WHERE parcel_reference IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS staging.idx_proceeding_extractions_normalized_reference;
        DROP FUNCTION IF EXISTS public.normalize_parcel_reference(text);
        """
    )
