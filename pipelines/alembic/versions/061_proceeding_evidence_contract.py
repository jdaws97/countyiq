"""Evidence spans and conservative shared proceeding-to-parcel attribution."""

from alembic import op

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
        ALTER TABLE staging.proceeding_extractions
            ADD COLUMN extraction_details jsonb NOT NULL DEFAULT '{}'::jsonb;

        CREATE TABLE meta.proceeding_project_aliases (
            alias text PRIMARY KEY,
            project_key text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT NOW()
        );

        CREATE FUNCTION public.proceeding_parcel_matches(refs jsonb, meeting_body text)
        RETURNS TABLE(pidn text, match_method text) LANGUAGE sql STABLE AS $body$
        WITH refs AS (
            SELECT upper(value) AS ref
            FROM jsonb_array_elements_text(
                CASE WHEN jsonb_typeof(refs) = 'array' THEN refs ELSE '[]'::jsonb END
            )
            WHERE value IS NOT NULL
        ), explicit_ids AS (
            SELECT DISTINCT public.normalize_parcel_reference(m[1]) AS pidn
            FROM refs, LATERAL regexp_matches(ref,
                '\m([0-9]{2}-[0-9]{3}-[A-Z0-9]{2}-[A-Z0-9]{4}[.][A-Z0-9]{2}[.-][0-9]{5}|[0-9]{5}[A-Z0-9]{7,8})\M', 'g') m
        ), addresses AS (
            SELECT DISTINCT public.normalize_street_address(
                split_part(split_part(split_part(ref, ';', 1), '(', 1), ',', 1)
            ) AS address
            FROM refs
            -- Never turn a street, intersection, range or multi-address shorthand
            -- into one particular parcel. Explicit ID references take precedence.
            WHERE NOT EXISTS (SELECT 1 FROM explicit_ids)
              AND ref ~ '^[0-9]+[A-Z]? +[A-Z]'
              AND ref !~ '(^[0-9]+ *[-/&]|[&]| INTERSECTION | CORNER )'
        ), candidates AS (
            SELECT p.pidn, 'pidn'::text AS match_method, p.propadr
            FROM explicit_ids i JOIN staging.parcels p ON p.pidn=i.pidn
            WHERE p.valid_to IS NULL
              AND EXISTS (SELECT 1 FROM meta.municipality_source_rights s
                  WHERE s.body_name=meeting_body AND s.municipality_name=p.municipality
                    AND s.derived_product_allowed)
            UNION ALL
            SELECT p.pidn, 'address'::text, a.address
            FROM addresses a JOIN staging.parcels p
              ON public.normalize_street_address(p.propadr)=a.address
            WHERE p.valid_to IS NULL
              AND a.address ~ '^[0-9]+[A-Z]? +[A-Z]'
              AND EXISTS (SELECT 1 FROM meta.municipality_source_rights s
                  WHERE s.body_name=meeting_body AND s.municipality_name=p.municipality
                    AND s.derived_product_allowed)
        )
        SELECT DISTINCT c.pidn, c.match_method FROM candidates c
        WHERE c.match_method='pidn' OR (
            SELECT count(DISTINCT d.pidn) FROM candidates d
            WHERE d.match_method='address' AND d.propadr=c.propadr
        )=1
        $body$;
    """)


def downgrade():
    # Original inference history remains authoritative; pair with old application.
    op.execute("""
        DROP FUNCTION public.proceeding_parcel_matches(jsonb, text);
        DROP TABLE meta.proceeding_project_aliases;
        ALTER TABLE staging.proceeding_extractions DROP COLUMN extraction_details;
    """)
