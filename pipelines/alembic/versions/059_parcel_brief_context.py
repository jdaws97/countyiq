"""Centralize the source context and fingerprint for parcel briefs."""
from alembic import op

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION meta.parcel_brief_sources(requested_pidn text)
        RETURNS jsonb LANGUAGE sql STABLE AS $body$
        WITH parcel AS (
            SELECT pidn,owner_full,propadr,aprtotal,acres,class,saledt,price,
                   prev_owner,municipality,school_dis
            FROM staging.parcels
            WHERE pidn=requested_pidn AND valid_to IS NULL
        ), entity AS (
            SELECT g.entity_id,g.canonical_name,g.entity_type,g.linked_names,
                   g.relationships,g.verification_status,g.active_inference_id
            FROM public.entity_graph g
            WHERE g.canonical_name=COALESCE((SELECT owner_full FROM parcel),'')
               OR COALESCE((SELECT owner_full FROM parcel),'')=ANY(g.linked_names)
            ORDER BY (g.canonical_name=COALESCE((SELECT owner_full FROM parcel),'')) DESC,
                     g.entity_id
            LIMIT 1
        ), resolved_owner AS (
            SELECT o.canonical_name,o.aliases
            FROM public.owner_source_links osl
            JOIN public.owners o ON o.owner_id=osl.owner_id
            WHERE osl.source_type='parcel' AND osl.source_id=requested_pidn
            ORDER BY o.owner_id LIMIT 1
        ), names AS (
            SELECT DISTINCT name FROM (
                SELECT owner_full AS name FROM parcel
                UNION ALL SELECT canonical_name FROM resolved_owner
                UNION ALL SELECT unnest(aliases) FROM resolved_owner
                UNION ALL SELECT unnest(linked_names) FROM entity
            ) candidates WHERE name IS NOT NULL AND name <> ''
        ), portfolio AS (
            SELECT pidn,aprtotal FROM staging.parcels
            WHERE valid_to IS NULL AND owner_full IN (SELECT name FROM names)
        )
        SELECT jsonb_build_object(
            'parcel',(SELECT to_jsonb(parcel) FROM parcel),
            'entity',(SELECT to_jsonb(entity) FROM entity),
            'resolved_names',COALESCE((SELECT jsonb_agg(name ORDER BY name) FROM names),'[]'::jsonb),
            'portfolio_pidns',COALESCE((SELECT jsonb_agg(pidn ORDER BY pidn) FROM portfolio),'[]'::jsonb),
            'portfolio',jsonb_build_object(
                'portfolio_count',(SELECT count(*) FROM portfolio),
                'portfolio_value',COALESCE((SELECT sum(aprtotal) FROM portfolio),0),
                'portfolio_delinquency',COALESCE((
                    SELECT sum(total) FROM staging.tax_claims
                    WHERE valid_to IS NULL AND pidn IN (SELECT pidn FROM portfolio)
                ),0)
            )
        )
        $body$;

        CREATE FUNCTION meta.parcel_brief_source_fingerprint(requested_pidn text)
        RETURNS text LANGUAGE sql STABLE AS $body$
            SELECT encode(sha256(convert_to(
                meta.parcel_brief_sources(requested_pidn)::text,'UTF8'
            )),'hex')
        $body$;
    """)


def downgrade():
    op.execute("""
        DROP FUNCTION meta.parcel_brief_source_fingerprint(text);
        DROP FUNCTION meta.parcel_brief_sources(text);
    """)
