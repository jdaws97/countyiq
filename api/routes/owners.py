"""Owner profile and portfolio endpoints."""

from fastapi import APIRouter, HTTPException, Query

from api.lib.database import get_cursor

router = APIRouter(tags=["owners"])


@router.get("/top")
def top_owners(
    limit: int = Query(default=50, le=200),
) -> list[dict]:
    """Top property owners by parcel count."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT owner_id, canonical_name, entity_type, parcel_count
            FROM public.owners
            ORDER BY parcel_count DESC
            LIMIT %(limit)s
        """, {"limit": limit})
        return [dict(r) for r in cur.fetchall()]


@router.get("/{owner_id}")
def owner_profile(owner_id: int) -> dict:
    """Full owner profile with all linked properties and source data."""
    with get_cursor() as cur:
        # Owner record
        cur.execute("""
            SELECT owner_id, canonical_name, entity_type, parcel_count, municipality
            FROM public.owners WHERE owner_id = %(id)s
        """, {"id": owner_id})
        owner = cur.fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail=f"Owner not found: {owner_id}")

        # All parcels owned
        cur.execute("""
            SELECT p.pidn, p.owner_full, p.propadr, p.class, p.aprtotal, p.acres,
                   p.saledt, p.price, p.school_dis
            FROM public.owner_source_links osl
            JOIN staging.parcels p ON p.pidn = osl.source_id AND p.valid_to IS NULL
            WHERE osl.owner_id = %(id)s AND osl.source_type = 'parcel'
            ORDER BY p.aprtotal::numeric DESC NULLS LAST
        """, {"id": owner_id})
        parcels = cur.fetchall()

        # Tax delinquency across all parcels
        cur.execute("""
            SELECT tc.pidn, tc.tax_year, tc.authority_name, tc.total, tc.property_address
            FROM public.owner_source_links osl
            JOIN staging.tax_claims tc ON tc.pidn = osl.source_id AND tc.valid_to IS NULL AND tc.total > 0
            WHERE osl.owner_id = %(id)s AND osl.source_type = 'parcel'
            ORDER BY tc.total DESC
        """, {"id": owner_id})
        tax_claims = cur.fetchall()

        # PLCB licenses linked
        cur.execute("""
            SELECT osl.source_name, osl.source_address, osl.confidence, osl.match_tier
            FROM public.owner_source_links osl
            WHERE osl.owner_id = %(id)s AND osl.source_type = 'plcb_license'
        """, {"id": owner_id})
        licenses = cur.fetchall()

    total_assessed = sum(float(p["aprtotal"] or 0) for p in parcels)
    total_delinquent = sum(float(t["total"] or 0) for t in tax_claims)
    delinquent_pidns = len({t["pidn"] for t in tax_claims})

    return {
        "owner": dict(owner),
        "portfolio": {
            "parcel_count": len(parcels),
            "total_assessed": total_assessed,
            "parcels": [dict(p) for p in parcels],
        },
        "delinquency": {
            "total_owed": total_delinquent,
            "delinquent_parcels": delinquent_pidns,
            "records": [dict(t) for t in tax_claims],
        },
        "licenses": [dict(l) for l in licenses],
    }
