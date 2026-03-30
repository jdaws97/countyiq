"""Entity resolution — match owners across parcels, tax claims, PLCB, PA businesses.

Populates public.owners and public.owner_source_links by matching
owner names across available staging tables using PIDN joins and
pg_trgm fuzzy name matching.

MVP scope: parcels + tax claims (PIDN join) + PLCB (name match).
"""

from dagster import (
    asset,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.resources.database import DatabaseResource


@asset(
    group_name="enrichment",
    description="Entity resolution — match owners across parcels, tax claims, and PLCB licenses",
    kinds={"postgres"},
)
def owner_resolution(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    """Match owner entities across data sources and populate public.owners."""

    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        context.log.info("Starting entity resolution...")

        # Step 1: Clear and rebuild public.owners from parcels
        cur.execute("DELETE FROM public.owner_source_links")
        cur.execute("DELETE FROM public.owners")
        cur.execute("ALTER SEQUENCE owners_owner_id_seq RESTART WITH 1")

        cur.execute("""
            INSERT INTO public.owners (canonical_name, municipality, parcel_count, first_seen, last_seen)
            SELECT
                owner_full AS canonical_name,
                MODE() WITHIN GROUP (ORDER BY municipality) AS municipality,
                COUNT(*) AS parcel_count,
                CURRENT_DATE AS first_seen,
                CURRENT_DATE AS last_seen
            FROM staging.parcels
            WHERE valid_to IS NULL
              AND owner_full IS NOT NULL
              AND TRIM(owner_full) != ''
            GROUP BY owner_full
        """)
        owner_count = cur.rowcount
        context.log.info(f"Created {owner_count} owner entities from parcels")

        # Step 2: Link parcels to owners
        cur.execute("""
            INSERT INTO public.owner_source_links (owner_id, source_type, source_id, source_name, source_address, match_tier, confidence)
            SELECT
                o.owner_id,
                'parcel',
                p.pidn,
                p.owner_full,
                p.propadr,
                'exact',
                1.0
            FROM public.owners o
            JOIN staging.parcels p ON p.owner_full = o.canonical_name AND p.valid_to IS NULL
        """)
        parcel_links = cur.rowcount
        context.log.info(f"Linked {parcel_links} parcel records")

        # Step 3: Match tax claims via PIDN join (high confidence)
        # For each parcel link, find tax claims on the same PIDN
        cur.execute("""
            INSERT INTO public.owner_source_links (owner_id, source_type, source_id, source_name, source_address, match_tier, confidence)
            SELECT DISTINCT
                osl.owner_id,
                'tax_claim',
                tc.pidn || ':' || tc.tax_year::text || ':' || tc.authority_name,
                tc.owner_name,
                tc.property_address,
                'pidn_join',
                0.95
            FROM public.owner_source_links osl
            JOIN staging.tax_claims tc ON tc.pidn = osl.source_id AND tc.valid_to IS NULL AND tc.total > 0
            WHERE osl.source_type = 'parcel'
            ON CONFLICT (source_type, source_id) DO NOTHING
        """)
        tax_links = cur.rowcount
        context.log.info(f"Linked {tax_links} tax claim records via PIDN")

        # Step 4: Match PLCB licensees via pg_trgm name similarity
        cur.execute("""
            INSERT INTO public.owner_source_links (owner_id, source_type, source_id, source_name, source_address, match_tier, confidence)
            SELECT DISTINCT ON (p.lid)
                o.owner_id,
                'plcb_license',
                p.lid,
                COALESCE(p.premises_owner, p.licensee),
                p.premises_address,
                'fuzzy_name',
                similarity(o.canonical_name, COALESCE(p.premises_owner, p.licensee))
            FROM public.owners o
            JOIN staging.plcb_licenses p ON p.valid_to IS NULL AND UPPER(p.status) = 'ACTIVE'
            WHERE similarity(o.canonical_name, COALESCE(p.premises_owner, p.licensee)) > 0.4
            ORDER BY p.lid, similarity(o.canonical_name, COALESCE(p.premises_owner, p.licensee)) DESC
            ON CONFLICT (source_type, source_id) DO NOTHING
        """)
        plcb_links = cur.rowcount
        context.log.info(f"Linked {plcb_links} PLCB licenses via name matching")

        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        if was_autocommit:
            conn.autocommit = True
        cur.close()

    return MaterializeResult(
        metadata={
            "owner_count": MetadataValue.int(owner_count),
            "parcel_links": MetadataValue.int(parcel_links),
            "tax_claim_links": MetadataValue.int(tax_links),
            "plcb_links": MetadataValue.int(plcb_links),
        }
    )
