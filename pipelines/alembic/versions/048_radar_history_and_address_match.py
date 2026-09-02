"""Radar score history, address normalization, and pass-config fingerprints.

Revision ID: 048
Revises: 047
Create Date: 2026-09-02

Three deterministic changes that support the score-version-6 radar:

1. ``public.development_momentum_history`` keeps one row per parcel per
   rebuild so the radar can show movers ("rose 18 points since last week",
   "new on radar") instead of a stateless weekly snapshot. The momentum
   table gains the previous-snapshot columns the movers view reads.
2. ``public.normalize_street_address`` gives municipal minutes and the
   assessment file one address spelling (suffix abbreviation, direction
   abbreviation, unit stripping) so extraction-to-parcel linking is no longer
   exact-string only. An expression index on current parcels backs the join.
3. ``meta.pass_config_fingerprints`` records the model/prompt fingerprint a
   pass last completed with. When it is unchanged the Pass 2 candidate query
   can take the timestamp fast path instead of re-gathering context for every
   signalled parcel just to compute a hash and skip.
"""

from alembic import op

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION public.normalize_street_address(raw text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE STRICT PARALLEL SAFE
        AS $fn$
            WITH cleaned AS (
                SELECT regexp_replace(
                    regexp_replace(upper(raw), '[^A-Z0-9 ]', ' ', 'g'),
                    '\s+(APT|APARTMENT|UNIT|SUITE|STE|LOT|BLDG|BUILDING|FL|FLOOR|REAR|#)\s+.*$',
                    '',
                    'g'
                ) AS value
            ),
            tokens AS (
                SELECT tok, ord
                FROM cleaned,
                     regexp_split_to_table(regexp_replace(value, '\s+', ' ', 'g'), ' ')
                         WITH ORDINALITY AS split(tok, ord)
                WHERE tok <> ''
            )
            SELECT NULLIF(string_agg(
                CASE tok
                    WHEN 'STREET' THEN 'ST'
                    WHEN 'ROAD' THEN 'RD'
                    WHEN 'AVENUE' THEN 'AVE'
                    WHEN 'AV' THEN 'AVE'
                    WHEN 'DRIVE' THEN 'DR'
                    WHEN 'LANE' THEN 'LN'
                    WHEN 'COURT' THEN 'CT'
                    WHEN 'BOULEVARD' THEN 'BLVD'
                    WHEN 'HIGHWAY' THEN 'HWY'
                    WHEN 'CIRCLE' THEN 'CIR'
                    WHEN 'PLACE' THEN 'PL'
                    WHEN 'TERRACE' THEN 'TER'
                    WHEN 'PARKWAY' THEN 'PKWY'
                    WHEN 'TRAIL' THEN 'TRL'
                    WHEN 'TURNPIKE' THEN 'TPKE'
                    WHEN 'ROUTE' THEN 'RT'
                    WHEN 'RTE' THEN 'RT'
                    WHEN 'NORTH' THEN 'N'
                    WHEN 'SOUTH' THEN 'S'
                    WHEN 'EAST' THEN 'E'
                    WHEN 'WEST' THEN 'W'
                    ELSE tok
                END,
                ' ' ORDER BY ord
            ), '')
            FROM tokens
        $fn$;

        CREATE INDEX IF NOT EXISTS idx_parcels_normalized_propadr
            ON staging.parcels (public.normalize_street_address(propadr))
            WHERE valid_to IS NULL AND propadr IS NOT NULL;

        CREATE TABLE IF NOT EXISTS public.development_momentum_history (
            pidn VARCHAR(13) NOT NULL,
            computed_at TIMESTAMPTZ NOT NULL,
            score INTEGER NOT NULL,
            opportunity_score INTEGER NOT NULL,
            site_readiness_score INTEGER NOT NULL DEFAULT 0,
            signal_count INTEGER NOT NULL DEFAULT 0,
            top_signal TEXT,
            score_version INTEGER NOT NULL,
            PRIMARY KEY (pidn, computed_at)
        );
        CREATE INDEX IF NOT EXISTS idx_dev_momentum_history_computed_at
            ON public.development_momentum_history (computed_at);

        ALTER TABLE public.development_momentum
            ADD COLUMN IF NOT EXISTS previous_score INTEGER,
            ADD COLUMN IF NOT EXISTS previous_opportunity_score INTEGER,
            ADD COLUMN IF NOT EXISTS previous_site_readiness_score INTEGER,
            ADD COLUMN IF NOT EXISTS previous_computed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS score_delta INTEGER,
            ADD COLUMN IF NOT EXISTS opportunity_delta INTEGER,
            ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS is_new BOOLEAN NOT NULL DEFAULT FALSE;

        CREATE INDEX IF NOT EXISTS idx_dev_momentum_opportunity_delta
            ON public.development_momentum (opportunity_delta DESC NULLS LAST)
            WHERE eligible = TRUE;
        CREATE INDEX IF NOT EXISTS idx_dev_momentum_score_delta
            ON public.development_momentum (score_delta DESC NULLS LAST)
            WHERE eligible = TRUE;

        CREATE TABLE IF NOT EXISTS meta.pass_config_fingerprints (
            pass_number INTEGER PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS meta.pass_config_fingerprints;
        DROP INDEX IF EXISTS public.idx_dev_momentum_score_delta;
        DROP INDEX IF EXISTS public.idx_dev_momentum_opportunity_delta;
        ALTER TABLE public.development_momentum
            DROP COLUMN IF EXISTS is_new,
            DROP COLUMN IF EXISTS first_seen_at,
            DROP COLUMN IF EXISTS opportunity_delta,
            DROP COLUMN IF EXISTS score_delta,
            DROP COLUMN IF EXISTS previous_computed_at,
            DROP COLUMN IF EXISTS previous_site_readiness_score,
            DROP COLUMN IF EXISTS previous_opportunity_score,
            DROP COLUMN IF EXISTS previous_score;
        DROP TABLE IF EXISTS public.development_momentum_history;
        DROP INDEX IF EXISTS staging.idx_parcels_normalized_propadr;
        DROP FUNCTION IF EXISTS public.normalize_street_address(text);
        """
    )
