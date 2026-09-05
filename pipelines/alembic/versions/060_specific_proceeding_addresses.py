"""Require specific, unambiguous addresses for proceeding-to-parcel links."""
from alembic import op

revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION public.proceeding_address_pidn(reference text, municipality_name text)
        RETURNS text LANGUAGE sql STABLE STRICT AS $body$
            WITH address AS (
                SELECT public.normalize_street_address(reference) AS normalized
            )
            SELECT CASE WHEN count(*)=1 THEN min(p.pidn)::text END
            FROM staging.parcels p
            JOIN address a ON public.normalize_street_address(p.propadr)=a.normalized
            WHERE p.valid_to IS NULL
              AND p.municipality=municipality_name
              AND a.normalized ~ '^[1-9][0-9]*[A-Z]? [A-Z0-9]'
        $body$;
    """)


def downgrade():
    op.execute("DROP FUNCTION public.proceeding_address_pidn(text,text)")
