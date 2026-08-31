"""Owner profile and portfolio endpoints.

public.owners is the single owner identity space: owner_resolution folds
entity-graph aliases, relationships, and verification metadata onto the
resolved owner row, and owner_id is stable across rebuilds.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.lib.database import get_cursor
from api.lib.rate_limit import enforce_sensitive_read_limit
from api.lib.settings import open_data_source_key, restricted_distress_enabled
from api.lib.source_policy import (
    PUBLIC_ORGANIZATION_TYPES,
    is_public_organization,
    require_source_use,
    source_use_allowed,
)

router = APIRouter(
    tags=["owners"],
    dependencies=[Depends(enforce_sensitive_read_limit)],
)


def _fetch_owner_brief(cur, canonical_name: str) -> dict | None:
    """Portfolio-level LLM brief for this owner, if one has been generated."""
    cur.execute(
        """
        SELECT
            brief_text, portfolio_strategy, concentration_notes, key_pattern,
            recommendation, urgency, top_risk, evidence_strength,
            n_parcels, confidence, n_trials, trial_agreement,
            model_version, generated_at
        FROM public.owner_briefs
        WHERE canonical_name = %(name)s
        """,
        {"name": canonical_name},
    )
    row = cur.fetchone()
    if not row:
        return None
    brief = dict(row)
    if brief.get("confidence") is not None:
        brief["confidence"] = float(brief["confidence"])
    if brief.get("trial_agreement") is not None:
        brief["trial_agreement"] = float(brief["trial_agreement"])
    return brief


def _linked_relationships(
    cur,
    raw_relationships: object,
    *,
    allow_people: bool = False,
) -> list[dict]:
    """Normalize relationship JSON and attach stable entity IDs when known."""
    relationships: list[dict] = []
    if isinstance(raw_relationships, list):
        relationships = [dict(item) for item in raw_relationships if isinstance(item, dict)]
    elif isinstance(raw_relationships, dict):
        for relationship_type, names in raw_relationships.items():
            candidates = names if isinstance(names, list) else [names]
            for name in candidates:
                if isinstance(name, str) and name.strip():
                    relationships.append(
                        {
                            "related_entity": name.strip(),
                            "relationship_type": str(relationship_type),
                        }
                    )

    names = [
        str(item.get("related_entity", "")).strip()
        for item in relationships
        if str(item.get("related_entity", "")).strip()
    ]
    if not names:
        return relationships

    cur.execute(
        """
        SELECT owner_id, canonical_name, aliases, entity_type, verification_status
        FROM public.owners
        WHERE lower(canonical_name) = ANY(%(names)s)
           OR EXISTS (
                SELECT 1 FROM unnest(COALESCE(aliases, ARRAY[]::text[])) alias
                WHERE lower(alias) = ANY(%(names)s)
           )
        """,
        {"names": [name.lower() for name in names]},
    )
    owner_by_name: dict[str, dict] = {}
    for owner in cur.fetchall():
        for name in [owner["canonical_name"], *(owner.get("aliases") or [])]:
            owner_by_name[str(name).strip().lower()] = owner

    for relationship in relationships:
        name = str(relationship.get("related_entity", "")).strip().lower()
        related_owner = owner_by_name.get(name)
        if related_owner:
            relationship["related_owner_id"] = related_owner["owner_id"]
            relationship["related_canonical_name"] = related_owner["canonical_name"]
            relationship["related_verification_status"] = related_owner.get(
                "verification_status"
            )
            relationship["related_entity_type"] = related_owner.get("entity_type")
    if allow_people:
        return relationships
    return [
        relationship
        for relationship in relationships
        if is_public_organization(relationship.get("related_entity_type"))
    ]


@router.get("/top")
def top_owners(
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    """Top property owners by parcel count."""
    with get_cursor() as cur:
        parcel_source = open_data_source_key()
        require_source_use(cur, parcel_source, "derived_product", conceal=False)
        show_people = source_use_allowed(cur, parcel_source, "person_level_display")
        cur.execute(
            """
            SELECT
                owner_id,
                canonical_name,
                COALESCE(NULLIF(entity_type, ''), 'unknown') AS entity_type,
                parcel_count,
                municipality,
                aliases,
                verification_status
            FROM public.owners
            WHERE %(show_people)s
               OR lower(COALESCE(entity_type, '')) = ANY(%(organization_types)s)
            ORDER BY parcel_count DESC, canonical_name
            LIMIT %(limit)s
            """,
            {
                "limit": limit,
                "show_people": show_people,
                "organization_types": list(PUBLIC_ORGANIZATION_TYPES),
            },
        )
        return [dict(row) for row in cur.fetchall()]


@router.get("/{owner_id}")
def owner_profile(owner_id: int) -> dict:
    """Full owner profile: portfolio, delinquency, licenses, brief."""
    with get_cursor() as cur:
        parcel_source = open_data_source_key()
        require_source_use(cur, parcel_source, "derived_product", conceal=False)
        show_people = source_use_allowed(cur, parcel_source, "person_level_display")
        cur.execute(
            """
            SELECT
                owner_id, canonical_name, entity_type, parcel_count,
                municipality, aliases, relationships,
                verification_status, verification_reasoning, verified_at
            FROM public.owners
            WHERE owner_id = %(id)s
            """,
            {"id": owner_id},
        )
        owner = cur.fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail=f"Owner not found: {owner_id}")
        owner = dict(owner)
        if not show_people and not is_public_organization(owner.get("entity_type")):
            raise HTTPException(status_code=404, detail=f"Owner not found: {owner_id}")
        if not show_people:
            owner["verification_reasoning"] = None

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

        tax_claims = []
        if restricted_distress_enabled() and source_use_allowed(
            cur, "tax_claims", "derived_product"
        ):
            cur.execute(
                """
                SELECT tc.pidn, tc.tax_year, tc.authority_name, tc.total,
                       tc.property_address
                FROM public.owner_source_links osl
                JOIN staging.tax_claims tc
                    ON tc.pidn = osl.source_id AND tc.valid_to IS NULL AND tc.total > 0
                WHERE osl.owner_id = %(id)s AND osl.source_type = 'parcel'
                ORDER BY tc.total DESC, tc.tax_year DESC
                """,
                {"id": owner_id},
            )
            tax_claims = [dict(row) for row in cur.fetchall()]

        licenses = []
        if source_use_allowed(cur, "plcb_licenses", "derived_product"):
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

        relationships = _linked_relationships(
            cur,
            owner.pop("relationships", None) or [],
            allow_people=show_people,
        )

        return {
            "owner": {
                **owner,
                "aliases": owner.get("aliases") or [],
            },
            "relationships": relationships,
            # Existing LLM prose was generated before the person-redaction
            # contract and may mention people beyond this legal organization.
            "brief": (
                _fetch_owner_brief(cur, owner["canonical_name"])
                if show_people
                else None
            ),
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
