"""Entity resolution — match owners across parcels, tax claims, PLCB, PA businesses.

Populates public.owners and public.owner_source_links with:
- Name normalization (strip suffixes, standardize format)
- Entity type classification (person vs business)
- Municipality-scoped matching for PLCB (reduces false positives)
- Tiered confidence scoring
"""

import re

from dagster import (
    asset,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.resources.database import DatabaseResource


# Suffixes to strip for normalization
_ENTITY_SUFFIXES = re.compile(
    r'\s+(LLC|INC|CORP|CORPORATION|LTD|LP|LLP|LLLP|PA|'
    r'TRUST|ESTATE|EST|ETAL|ET\s*AL|'
    r'JR|SR|II|III|IV|MD|ESQ|PHD|DDS|'
    r'CO|COMPANY|ASSOC|ASSOCIATION|FOUNDATION|'
    r'REVOCABLE|IRREVOCABLE|LIVING|FAMILY)\s*\.?\s*$',
    re.IGNORECASE,
)

_BUSINESS_INDICATORS = re.compile(
    r'\b(LLC|INC|CORP|CORPORATION|LTD|LP|LLP|TRUST|ESTATE|'
    r'ASSOCIATES|ASSOCIATION|FOUNDATION|PROPERTIES|REALTY|'
    r'INVESTMENTS|HOLDINGS|PARTNERS|GROUP|ENTERPRISES|'
    r'CAPITAL|MANAGEMENT|DEVELOPMENT|VENTURES|BANK|'
    r'COUNTY OF|COMMONWEALTH|TOWNSHIP|BOROUGH|AUTHORITY|'
    r'CHURCH|SYNAGOGUE|MOSQUE|SOCIETY|CLUB|LODGE|'
    r'SCHOOL|UNIVERSITY|COLLEGE|HOSPITAL)\b',
    re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    """Normalize an owner name for matching.

    - Strip common suffixes (LLC, JR, TRUST, etc.)
    - Collapse whitespace
    - Uppercase
    """
    if not name:
        return ""
    n = name.upper().strip()
    # Remove content in parentheses
    n = re.sub(r'\([^)]*\)', '', n)
    # Strip entity suffixes (iteratively — "SMITH LLC INC" → "SMITH")
    for _ in range(3):
        prev = n
        n = _ENTITY_SUFFIXES.sub('', n).strip()
        if n == prev:
            break
    # Collapse whitespace
    n = re.sub(r'\s+', ' ', n).strip()
    # Remove trailing punctuation
    n = n.rstrip('.,;:&-')
    return n.strip()


def classify_entity(name: str) -> str:
    """Classify owner as 'person' or 'business'."""
    if not name:
        return "unknown"
    if _BUSINESS_INDICATORS.search(name):
        return "business"
    # Names with "&" between two name-like parts are joint persons
    # "SMITH JOHN & MARY" = person, "SMITH & JONES LLC" = business
    return "person"


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

        # Step 1: Clear and rebuild
        cur.execute("DELETE FROM public.owner_source_links")
        cur.execute("DELETE FROM public.owners")
        cur.execute("ALTER SEQUENCE owners_owner_id_seq RESTART WITH 1")

        # Step 2: Create normalized owner entities from parcels
        # Group by normalized name (merges "SMITH JOHN A" and "SMITH JOHN A JR")
        cur.execute("SELECT DISTINCT owner_full FROM staging.parcels WHERE valid_to IS NULL AND owner_full IS NOT NULL AND TRIM(owner_full) != ''")
        raw_names = [r[0] for r in cur.fetchall()]

        # Build normalized name → list of raw names mapping
        norm_groups: dict[str, list[str]] = {}
        for raw in raw_names:
            normed = normalize_name(raw)
            if normed:
                norm_groups.setdefault(normed, []).append(raw)

        context.log.info(f"Normalized {len(raw_names)} raw names into {len(norm_groups)} entities")

        # Insert owners with entity type and municipality
        owner_count = 0
        for normed, raw_list in norm_groups.items():
            entity_type = classify_entity(raw_list[0])
            # Use the shortest raw name as canonical (least suffixes)
            canonical = min(raw_list, key=len)

            cur.execute("""
                INSERT INTO public.owners (canonical_name, entity_type, parcel_count, first_seen, last_seen)
                SELECT
                    %(canonical)s,
                    %(entity_type)s,
                    COUNT(*),
                    CURRENT_DATE,
                    CURRENT_DATE
                FROM staging.parcels
                WHERE valid_to IS NULL AND owner_full = ANY(%(raw_list)s)
            """, {"canonical": canonical, "entity_type": entity_type, "raw_list": raw_list})
            owner_count += 1

        context.log.info(f"Created {owner_count} owner entities")

        # Step 3: Link parcels to owners (using normalized name grouping)
        parcel_links = 0
        for normed, raw_list in norm_groups.items():
            cur.execute("""
                INSERT INTO public.owner_source_links (owner_id, source_type, source_id, source_name, source_address, match_tier, confidence)
                SELECT
                    (SELECT owner_id FROM public.owners WHERE canonical_name = %(canonical)s LIMIT 1),
                    'parcel',
                    p.pidn,
                    p.owner_full,
                    p.propadr,
                    'exact',
                    1.0
                FROM staging.parcels p
                WHERE p.valid_to IS NULL AND p.owner_full = ANY(%(raw_list)s)
                ON CONFLICT (source_type, source_id) DO NOTHING
            """, {"canonical": min(raw_list, key=len), "raw_list": raw_list})
            parcel_links += cur.rowcount

        context.log.info(f"Linked {parcel_links} parcel records")

        # Step 4: Match tax claims via PIDN join (high confidence)
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

        # Step 5: Match PLCB licensees — municipality-scoped + higher threshold
        # Only match PLCB licenses where the municipality overlaps with the owner's
        # parcel locations AND name similarity is > 0.6 (stricter than before)
        cur.execute("""
            INSERT INTO public.owner_source_links (owner_id, source_type, source_id, source_name, source_address, match_tier, confidence)
            SELECT DISTINCT ON (p.lid)
                o.owner_id,
                'plcb_license',
                p.lid,
                COALESCE(p.premises_owner, p.licensee),
                p.premises_address,
                'fuzzy_name_scoped',
                similarity(o.canonical_name, COALESCE(p.premises_owner, p.licensee))
            FROM public.owners o
            JOIN public.owner_source_links osl ON o.owner_id = osl.owner_id AND osl.source_type = 'parcel'
            JOIN staging.parcels par ON par.pidn = osl.source_id AND par.valid_to IS NULL
            JOIN staging.plcb_licenses p ON p.valid_to IS NULL AND UPPER(p.status) = 'ACTIVE'
            WHERE similarity(o.canonical_name, COALESCE(p.premises_owner, p.licensee)) > 0.6
              AND UPPER(p.municipality) LIKE UPPER(COALESCE(par.municipality, '___NOMATCH___')) || '%%'
            ORDER BY p.lid, similarity(o.canonical_name, COALESCE(p.premises_owner, p.licensee)) DESC
            ON CONFLICT (source_type, source_id) DO NOTHING
        """)
        plcb_scoped = cur.rowcount
        context.log.info(f"Linked {plcb_scoped} PLCB licenses via municipality-scoped name matching (>0.6)")

        # Step 5b: Fallback — unscoped PLCB matching at even higher threshold (0.75)
        # for licenses that didn't match in the scoped pass
        cur.execute("""
            INSERT INTO public.owner_source_links (owner_id, source_type, source_id, source_name, source_address, match_tier, confidence)
            SELECT DISTINCT ON (p.lid)
                o.owner_id,
                'plcb_license',
                p.lid,
                COALESCE(p.premises_owner, p.licensee),
                p.premises_address,
                'fuzzy_name_unscoped',
                similarity(o.canonical_name, COALESCE(p.premises_owner, p.licensee)) * 0.8
            FROM public.owners o
            JOIN staging.plcb_licenses p ON p.valid_to IS NULL AND UPPER(p.status) = 'ACTIVE'
            WHERE similarity(o.canonical_name, COALESCE(p.premises_owner, p.licensee)) > 0.75
            ORDER BY p.lid, similarity(o.canonical_name, COALESCE(p.premises_owner, p.licensee)) DESC
            ON CONFLICT (source_type, source_id) DO NOTHING
        """)
        plcb_unscoped = cur.rowcount
        context.log.info(f"Linked {plcb_unscoped} additional PLCB licenses via unscoped matching (>0.75)")

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
            "plcb_scoped_links": MetadataValue.int(plcb_scoped),
            "plcb_unscoped_links": MetadataValue.int(plcb_unscoped),
        }
    )
