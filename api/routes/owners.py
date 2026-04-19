"""Owner profile and portfolio endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.lib.database import get_cursor

router = APIRouter(tags=["owners"])

ENTITY_OWNER_ID_OFFSET = 1_000_000_000


def _encode_entity_owner_id(entity_id: int) -> int:
    return ENTITY_OWNER_ID_OFFSET + entity_id


def _is_encoded_entity_owner_id(owner_id: int) -> bool:
    return owner_id >= ENTITY_OWNER_ID_OFFSET


def _fetch_entity_graph_row(cur, *, entity_id: int | None = None, owner_name: str | None = None):
    if entity_id is not None:
        cur.execute(
            """
            SELECT
                entity_id,
                canonical_name,
                entity_type,
                linked_names,
                relationships,
                verification_status,
                verification_reasoning,
                verified_at
            FROM public.entity_graph
            WHERE entity_id = %(entity_id)s
            """,
            {"entity_id": entity_id},
        )
        return cur.fetchone()

    if not owner_name:
        return None

    cur.execute(
        """
        SELECT
            entity_id,
            canonical_name,
            entity_type,
            linked_names,
            relationships,
            verification_status,
            verification_reasoning,
            verified_at
        FROM public.entity_graph
        WHERE canonical_name = %(owner_name)s
           OR %(owner_name)s = ANY(COALESCE(linked_names, ARRAY[]::text[]))
        ORDER BY
            (canonical_name = %(owner_name)s) DESC,
            verified_at DESC NULLS LAST,
            entity_id
        LIMIT 1
        """,
        {"owner_name": owner_name},
    )
    return cur.fetchone()


def _entity_names(entity_row: dict) -> list[str]:
    names: list[str] = []
    canonical = entity_row.get("canonical_name")
    if isinstance(canonical, str) and canonical.strip():
        names.append(canonical.strip())
    for name in entity_row.get("linked_names") or []:
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return list(dict.fromkeys(names))


def _primary_municipality(parcels: list[dict]) -> str | None:
    for parcel in parcels:
        municipality = parcel.get("municipality")
        if municipality:
            return municipality
    return None


def _fetch_entity_graph_profile(cur, entity_row: dict) -> dict:
    names = _entity_names(entity_row)

    cur.execute(
        """
        WITH direct_name_matches AS (
            SELECT
                p.pidn, p.owner_full, p.propadr, p.class, p.aprtotal, p.acres,
                p.saledt, p.price, p.school_dis, p.municipality
            FROM staging.parcels p
            WHERE p.valid_to IS NULL
              AND p.owner_full = ANY(%(names)s)
        ),
        linked_owner_matches AS (
            SELECT
                p.pidn, p.owner_full, p.propadr, p.class, p.aprtotal, p.acres,
                p.saledt, p.price, p.school_dis, p.municipality
            FROM public.owners o
            JOIN public.owner_source_links osl
                ON o.owner_id = osl.owner_id
               AND osl.source_type = 'parcel'
            JOIN staging.parcels p
                ON p.pidn = osl.source_id
               AND p.valid_to IS NULL
            WHERE o.canonical_name = ANY(%(names)s)
        )
        SELECT DISTINCT ON (pidn)
            pidn, owner_full, propadr, class, aprtotal, acres,
            saledt, price, school_dis, municipality
        FROM (
            SELECT * FROM direct_name_matches
            UNION ALL
            SELECT * FROM linked_owner_matches
        ) parcel_matches
        ORDER BY pidn, aprtotal::numeric DESC NULLS LAST
        """,
        {"names": names},
    )
    parcels = [dict(row) for row in cur.fetchall()]
    pidns = [parcel["pidn"] for parcel in parcels]

    tax_claims: list[dict] = []
    if pidns:
        cur.execute(
            """
            SELECT
                tc.pidn,
                tc.tax_year,
                tc.authority_name,
                tc.total,
                tc.property_address
            FROM staging.tax_claims tc
            WHERE tc.valid_to IS NULL
              AND tc.total > 0
              AND tc.pidn = ANY(%(pidns)s)
            ORDER BY tc.total DESC, tc.tax_year DESC
            """,
            {"pidns": pidns},
        )
        tax_claims = [dict(row) for row in cur.fetchall()]

    cur.execute(
        """
        WITH fuzzy_links AS (
            SELECT DISTINCT
                osl.source_name,
                osl.source_address,
                osl.confidence,
                osl.match_tier
            FROM public.owners o
            JOIN public.owner_source_links osl
                ON o.owner_id = osl.owner_id
               AND osl.source_type = 'plcb_license'
            WHERE o.canonical_name = ANY(%(names)s)
        ),
        exact_links AS (
            SELECT DISTINCT
                COALESCE(p.premises_name, p.licensee) AS source_name,
                p.premises_address AS source_address,
                NULL::numeric AS confidence,
                'exact_name'::text AS match_tier
            FROM staging.plcb_licenses p
            WHERE p.valid_to IS NULL
              AND (
                  p.licensee = ANY(%(names)s)
                  OR p.premises_owner = ANY(%(names)s)
              )
        )
        SELECT DISTINCT
            source_name,
            source_address,
            confidence,
            match_tier
        FROM (
            SELECT * FROM fuzzy_links
            UNION ALL
            SELECT * FROM exact_links
        ) license_matches
        ORDER BY source_name, source_address
        """,
        {"names": names},
    )
    licenses = [dict(row) for row in cur.fetchall()]

    total_assessed = sum(float(parcel["aprtotal"] or 0) for parcel in parcels)
    total_delinquent = sum(float(claim["total"] or 0) for claim in tax_claims)
    delinquent_pidns = len({claim["pidn"] for claim in tax_claims})

    canonical_name = entity_row.get("canonical_name") or "Unknown"
    aliases = [name for name in names if name != canonical_name]

    return {
        "owner": {
            "owner_id": _encode_entity_owner_id(entity_row["entity_id"]),
            "canonical_name": canonical_name,
            "entity_type": entity_row.get("entity_type") or "unknown",
            "parcel_count": len(parcels),
            "municipality": _primary_municipality(parcels),
            "source_mode": "entity_graph",
            "aliases": aliases,
            "verification_status": entity_row.get("verification_status"),
            "verification_reasoning": entity_row.get("verification_reasoning"),
            "verified_at": entity_row.get("verified_at"),
        },
        "portfolio": {
            "parcel_count": len(parcels),
            "total_assessed": total_assessed,
            "parcels": parcels,
        },
        "delinquency": {
            "total_owed": total_delinquent,
            "delinquent_parcels": delinquent_pidns,
            "records": tax_claims,
        },
        "licenses": licenses,
    }


def _fetch_legacy_owner_profile(cur, owner_id: int) -> dict:
    cur.execute(
        """
        SELECT owner_id, canonical_name, entity_type, parcel_count, municipality
        FROM public.owners
        WHERE owner_id = %(id)s
        """,
        {"id": owner_id},
    )
    owner = cur.fetchone()
    if not owner:
        raise HTTPException(status_code=404, detail=f"Owner not found: {owner_id}")

    entity_row = _fetch_entity_graph_row(cur, owner_name=owner["canonical_name"])
    if entity_row:
        return _fetch_entity_graph_profile(cur, entity_row)

    cur.execute(
        """
        SELECT p.pidn, p.owner_full, p.propadr, p.class, p.aprtotal, p.acres,
               p.saledt, p.price, p.school_dis, p.municipality
        FROM public.owner_source_links osl
        JOIN staging.parcels p ON p.pidn = osl.source_id AND p.valid_to IS NULL
        WHERE osl.owner_id = %(id)s AND osl.source_type = 'parcel'
        ORDER BY p.aprtotal::numeric DESC NULLS LAST
        """,
        {"id": owner_id},
    )
    parcels = [dict(row) for row in cur.fetchall()]

    cur.execute(
        """
        SELECT tc.pidn, tc.tax_year, tc.authority_name, tc.total, tc.property_address
        FROM public.owner_source_links osl
        JOIN staging.tax_claims tc ON tc.pidn = osl.source_id AND tc.valid_to IS NULL AND tc.total > 0
        WHERE osl.owner_id = %(id)s AND osl.source_type = 'parcel'
        ORDER BY tc.total DESC
        """,
        {"id": owner_id},
    )
    tax_claims = [dict(row) for row in cur.fetchall()]

    cur.execute(
        """
        SELECT osl.source_name, osl.source_address, osl.confidence, osl.match_tier
        FROM public.owner_source_links osl
        WHERE osl.owner_id = %(id)s AND osl.source_type = 'plcb_license'
        ORDER BY osl.source_name
        """,
        {"id": owner_id},
    )
    licenses = [dict(row) for row in cur.fetchall()]

    total_assessed = sum(float(parcel["aprtotal"] or 0) for parcel in parcels)
    total_delinquent = sum(float(claim["total"] or 0) for claim in tax_claims)
    delinquent_pidns = len({claim["pidn"] for claim in tax_claims})

    return {
        "owner": {
            **dict(owner),
            "source_mode": "owner_resolution",
            "aliases": [],
            "verification_status": None,
            "verification_reasoning": None,
            "verified_at": None,
        },
        "portfolio": {
            "parcel_count": len(parcels),
            "total_assessed": total_assessed,
            "parcels": parcels,
        },
        "delinquency": {
            "total_owed": total_delinquent,
            "delinquent_parcels": delinquent_pidns,
            "records": tax_claims,
        },
        "licenses": licenses,
    }


@router.get("/top")
def top_owners(
    limit: int = Query(default=50, le=200),
) -> list[dict]:
    """Top property owners, preferring graph-backed entities when available."""
    with get_cursor() as cur:
        cur.execute(
            """
            WITH owner_matches AS (
                SELECT
                    o.owner_id,
                    o.canonical_name AS owner_canonical_name,
                    o.entity_type AS owner_entity_type,
                    o.parcel_count,
                    o.municipality,
                    eg.entity_id,
                    eg.canonical_name AS graph_canonical_name,
                    eg.entity_type AS graph_entity_type
                FROM public.owners o
                LEFT JOIN LATERAL (
                    SELECT
                        eg.entity_id,
                        eg.canonical_name,
                        eg.entity_type
                    FROM public.entity_graph eg
                    WHERE o.canonical_name = eg.canonical_name
                       OR o.canonical_name = ANY(COALESCE(eg.linked_names, ARRAY[]::text[]))
                    ORDER BY
                        (eg.canonical_name = o.canonical_name) DESC,
                        eg.verified_at DESC NULLS LAST,
                        eg.entity_id
                    LIMIT 1
                ) eg ON TRUE
            )
            SELECT
                CASE
                    WHEN entity_id IS NOT NULL THEN %(offset)s + entity_id
                    ELSE owner_id
                END AS owner_id,
                COALESCE(graph_canonical_name, owner_canonical_name) AS canonical_name,
                COALESCE(NULLIF(graph_entity_type, ''), owner_entity_type, 'unknown') AS entity_type,
                SUM(parcel_count)::int AS parcel_count,
                MIN(municipality) FILTER (WHERE municipality IS NOT NULL) AS municipality
            FROM owner_matches
            GROUP BY
                CASE
                    WHEN entity_id IS NOT NULL THEN %(offset)s + entity_id
                    ELSE owner_id
                END,
                COALESCE(graph_canonical_name, owner_canonical_name),
                COALESCE(NULLIF(graph_entity_type, ''), owner_entity_type, 'unknown')
            ORDER BY parcel_count DESC, canonical_name
            LIMIT %(limit)s
            """,
            {"limit": limit, "offset": ENTITY_OWNER_ID_OFFSET},
        )
        return [dict(row) for row in cur.fetchall()]


@router.get("/{owner_id}")
def owner_profile(owner_id: int) -> dict:
    """Full owner profile with entity-graph-backed consolidation when available."""
    with get_cursor() as cur:
        if _is_encoded_entity_owner_id(owner_id):
            entity_row = _fetch_entity_graph_row(cur, entity_id=owner_id - ENTITY_OWNER_ID_OFFSET)
            if not entity_row:
                raise HTTPException(status_code=404, detail=f"Owner not found: {owner_id}")
            return _fetch_entity_graph_profile(cur, entity_row)

        return _fetch_legacy_owner_profile(cur, owner_id)
