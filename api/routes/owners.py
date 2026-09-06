"""Owner profile and portfolio endpoints.

public.owners is the single owner identity space: owner_resolution folds
entity-graph aliases, relationships, and verification metadata onto the
resolved owner row, and owner_id is stable across rebuilds.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query

from api.lib.inference_provenance import (
    BRIEF_SIGNAL_VERSIONS_CURRENT_SQL,
    SUPPORTING_PROCEEDINGS_CURRENT_SQL,
    owner_context_is_current,
)
from api.lib.database import get_cursor
from api.lib.development_radar import sanitize_signals_for_public
from api.lib.evidence import evidence_item
from api.lib.rate_limit import enforce_sensitive_read_limit
from api.lib.serialization import serialize_temporal_fields
from api.lib.settings import open_data_source_key, restricted_distress_enabled
from api.lib.source_policy import require_source_use, source_use_allowed

router = APIRouter(
    tags=["owners"],
    dependencies=[Depends(enforce_sensitive_read_limit)],
)


def _fetch_owner_brief(cur, canonical_name: str) -> dict | None:
    """Portfolio-level LLM brief for this owner, if one has been generated."""
    cur.execute(
        f"""
        SELECT
            brief_text, portfolio_strategy, concentration_notes, key_pattern,
            recommendation, urgency, top_risk, evidence_strength,
            citations, parcel_citations,
            n_parcels, confidence, n_trials, trial_agreement,
            model_version, prompt_version, brief_version, generated_at,
            (SELECT evidence_refs FROM meta.intelligence_inference_history
             WHERE inference_id=brief.active_inference_id) AS dependency_refs
        FROM public.owner_briefs brief
        WHERE canonical_name = %(name)s
          AND {BRIEF_SIGNAL_VERSIONS_CURRENT_SQL}
          AND NOT EXISTS (
              SELECT 1 FROM jsonb_array_elements_text(COALESCE(brief.citations, '[]'::jsonb)) citation(signal_key)
              WHERE NOT EXISTS (
                  SELECT 1 FROM public.evidence supporting
                  WHERE supporting.signal_key = citation.signal_key
                    AND supporting.pidn IN (
                        SELECT jsonb_array_elements_text(COALESCE(brief.parcel_citations, '[]'::jsonb))
                    )
                    AND supporting.validation_status IN ('confirmed', 'upgraded', 'downgraded')
                    AND {SUPPORTING_PROCEEDINGS_CURRENT_SQL}
              )
          )
        """,
        {
            "name": canonical_name,
            "brief_kind": "owner_brief",
            "brief_subject": "owner_brief:"
            + hashlib.sha256(canonical_name.encode("utf-8")).hexdigest()[:20],
        },
    )
    row = cur.fetchone()
    if not row:
        return None
    brief = dict(row)
    dependency_refs = brief.pop("dependency_refs") or []
    if not owner_context_is_current(cur, canonical_name, dependency_refs):
        return None
    if brief.get("confidence") is not None:
        brief["confidence"] = float(brief["confidence"])
    if brief.get("trial_agreement") is not None:
        brief["trial_agreement"] = float(brief["trial_agreement"])
    brief["citations"] = list(brief.get("citations") or [])
    brief["parcel_citations"] = list(brief.get("parcel_citations") or [])
    brief["citation_evidence"] = _fetch_owner_brief_evidence(cur, brief)
    serialize_temporal_fields(brief, "generated_at")
    return brief


def _fetch_owner_brief_evidence(cur, brief: dict) -> list[dict]:
    """Resolve stored signal/PIDN citations into customer-facing receipts."""

    signal_keys = [str(value) for value in brief.get("citations") or [] if str(value)]
    pidns = [str(value) for value in brief.get("parcel_citations") or [] if str(value)]
    items: list[dict] = []
    resolved_signal_keys: set[str] = set()

    if signal_keys and pidns:
        cur.execute(
            """
            SELECT pidn, signal_key, claim, evidence_data, source_url,
                   internal_url, validation_status, adjusted_significance,
                   validation_reasoning, validated_at, confidence
            FROM public.evidence
            WHERE pidn = ANY(%(pidns)s)
              AND signal_key = ANY(%(signal_keys)s)
            ORDER BY pidn, signal_key
            """,
            {"pidns": pidns, "signal_keys": signal_keys},
        )
        for row in cur.fetchall():
            record = dict(row)
            safe_signal = (
                sanitize_signals_for_public(
                    {
                        "signal": {
                            "claim": record.get("claim"),
                            "validation_reasoning": record.get("validation_reasoning"),
                            "evidence": record.get("evidence_data") or {},
                        }
                    },
                )
                or {}
            )
            signal = safe_signal.get("signal")
            if not isinstance(signal, dict):
                signal = {}
            facts = dict(signal.get("evidence") or {})
            for key in ("claim", "validation_reasoning"):
                if signal.get(key) is not None:
                    facts[key] = signal[key]
            facts["validation_status"] = record.get("validation_status")
            facts["adjusted_significance"] = record.get("adjusted_significance")
            signal_key = str(record["signal_key"])
            pidn = str(record["pidn"])
            resolved_signal_keys.add(signal_key)
            items.append(
                evidence_item(
                    scope=f"owner-brief:{pidn}",
                    citation_key=f"signal:{signal_key}",
                    label=f"{signal_key.replace('_', ' ').title()} · {pidn}",
                    source_kind="validated_signal",
                    source_record_id=f"{pidn}:{signal_key}",
                    url=record.get("source_url"),
                    internal_url=record.get("internal_url") or f"/property/{pidn}",
                    details=facts,
                    observed_at=record.get("validated_at"),
                    method="CountyIQ validated this portfolio signal against the linked source facts before generating the brief.",
                    confidence=record.get("confidence"),
                )
            )

    for signal_key in signal_keys:
        if signal_key in resolved_signal_keys:
            continue
        items.append(
            evidence_item(
                scope="owner-brief",
                citation_key=f"signal:{signal_key}",
                label=signal_key.replace("_", " ").title(),
                source_kind="validated_signal",
                source_record_id=signal_key,
                method="This stored citation identifies the validated signal used by the portfolio brief.",
                caveat="The current serving rows do not contain a more specific external record for this citation.",
            )
        )

    if pidns:
        cur.execute(
            """
            SELECT pidn, propadr, municipality, aprtotal, saledt, price,
                   source_url, valid_from
            FROM staging.parcels
            WHERE pidn = ANY(%(pidns)s) AND valid_to IS NULL
            ORDER BY pidn
            """,
            {"pidns": pidns},
        )
        for row in cur.fetchall():
            record = dict(row)
            pidn = str(record["pidn"])
            item = evidence_item(
                scope="owner-brief",
                citation_key=f"parcel:{pidn}",
                label=f"Parcel {pidn}",
                source_kind="official_parcel_record",
                source_record_id=pidn,
                url=record.get("source_url"),
                internal_url=f"/property/{pidn}",
                details={
                    key: record.get(key)
                    for key in (
                        "propadr",
                        "municipality",
                        "aprtotal",
                        "saledt",
                        "price",
                    )
                    if record.get(key) is not None
                },
                effective_at=record.get("valid_from"),
                observed_at=record.get("valid_from"),
                method="CountyIQ linked this exact PIDN from the versioned county parcel record to the portfolio brief.",
            )
            serialize_temporal_fields(item, "effective_at", "observed_at")
            items.append(item)
    for item in items:
        serialize_temporal_fields(item, "effective_at", "observed_at")
        if item.get("confidence") is not None:
            item["confidence"] = float(item["confidence"])
    return items


def _fetch_entity_verification_evidence(
    cur,
    canonical_name: str,
    *,
    allow_corporate_evidence: bool,
) -> list[dict]:
    """Expose the governed record identifiers used to verify an entity merge."""

    cur.execute(
        """
        SELECT linked_sources, verified_at
        FROM public.entity_graph
        WHERE canonical_name = %(name)s
        ORDER BY verified_at DESC NULLS LAST
        LIMIT 1
        """,
        {"name": canonical_name},
    )
    graph = cur.fetchone()
    if not graph or not isinstance(graph.get("linked_sources"), dict):
        return []

    # Each source family needs its own customer-display decision. Parcels are
    # governed above; business records are included only when their separate
    # policy permits derived-product use. Other graph groups stay backend-only
    # until their own policy is checked here explicitly.
    allowed_groups = {"parcels"}
    if allow_corporate_evidence:
        allowed_groups.add("corporate_entities")
    linked_sources = {
        str(group): [str(value) for value in values[:25]]
        for group, values in graph["linked_sources"].items()
        if group in allowed_groups and isinstance(values, list)
    }
    verified_at = graph.get("verified_at")
    items: list[dict] = []
    parcel_ids = linked_sources.get("parcels", [])
    parcel_by_id: dict[str, dict] = {}
    if parcel_ids:
        cur.execute(
            """
            SELECT pidn, propadr, municipality, source_url, valid_from
            FROM staging.parcels
            WHERE pidn = ANY(%(pidns)s) AND valid_to IS NULL
            """,
            {"pidns": parcel_ids},
        )
        parcel_by_id = {str(row["pidn"]): dict(row) for row in cur.fetchall()}

    corporate_names = linked_sources.get("corporate_entities", [])
    corporate_by_name: dict[str, dict] = {}
    if corporate_names and allow_corporate_evidence:
        cur.execute(
            """
            SELECT entity_name, entity_number, status, formation_date,
                   office_address, source_url, valid_from
            FROM staging.corporate_entities
            WHERE entity_name = ANY(%(names)s) AND valid_to IS NULL
            """,
            {"names": corporate_names},
        )
        corporate_by_name = {
            str(row["entity_name"]): dict(row) for row in cur.fetchall()
        }

    for group, identifiers in linked_sources.items():
        for identifier in identifiers:
            record = (
                parcel_by_id.get(identifier) or corporate_by_name.get(identifier) or {}
            )
            citation_key = f"evidence:{group}:{identifier}"
            if group == "parcels":
                label = f"County parcel {identifier}"
                internal_url = f"/property/{identifier}"
                source_kind = "official_parcel_record"
                details = {
                    key: record.get(key)
                    for key in ("propadr", "municipality")
                    if record.get(key) is not None
                }
            elif group == "corporate_entities":
                label = f"Pennsylvania business record · {identifier}"
                internal_url = None
                source_kind = "official_business_record"
                details = {
                    key: record.get(key)
                    for key in (
                        "entity_number",
                        "status",
                        "formation_date",
                        "office_address",
                    )
                    if record.get(key) is not None
                }
            else:
                label = f"{group.replace('_', ' ').title()} · {identifier}"
                internal_url = None
                source_kind = "governed_record_reference"
                details = {"record_group": group, "record_identifier": identifier}
            item = evidence_item(
                scope=f"entity:{canonical_name}",
                citation_key=citation_key,
                label=label,
                source_kind=source_kind,
                source_record_id=record.get("entity_number") or identifier,
                url=record.get("source_url"),
                internal_url=internal_url,
                details=details,
                effective_at=record.get("valid_from"),
                observed_at=verified_at,
                method="CountyIQ used this exact governed record identifier in the entity-verification decision.",
                caveat=(
                    None
                    if record.get("source_url") or internal_url
                    else "Row-level source display is unavailable under the current source-use policy."
                ),
            )
            serialize_temporal_fields(item, "effective_at", "observed_at")
            items.append(item)
    return items


def _linked_relationships(
    cur,
    raw_relationships: object,
) -> list[dict]:
    """Normalize relationship JSON and attach stable entity IDs when known."""
    relationships: list[dict] = []
    if isinstance(raw_relationships, list):
        relationships = [
            dict(item) for item in raw_relationships if isinstance(item, dict)
        ]
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
    return relationships


@router.get("/top")
def top_owners(
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    """Top property owners by parcel count."""
    with get_cursor() as cur:
        parcel_source = open_data_source_key()
        require_source_use(cur, parcel_source, "derived_product", conceal=False)
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
            ORDER BY parcel_count DESC, canonical_name
            LIMIT %(limit)s
            """,
            {"limit": limit},
        )
        return [dict(row) for row in cur.fetchall()]


@router.get("/{owner_id}")
def owner_profile(owner_id: int) -> dict:
    """Full owner profile: portfolio, delinquency, licenses, brief."""
    with get_cursor(snapshot=True) as cur:
        parcel_source = open_data_source_key()
        require_source_use(cur, parcel_source, "derived_product", conceal=False)
        allow_corporate_evidence = source_use_allowed(
            cur, "data_pa_businesses", "derived_product"
        )
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
        # Exact claim rows are a restricted, separately gated surface. The
        # response says so explicitly so the UI never renders "$0 owed" as a
        # fact when the rows were merely withheld.
        delinquency_detail_available = (
            restricted_distress_enabled()
            and source_use_allowed(cur, "tax_claims", "derived_product")
        )
        if delinquency_detail_available:
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
            cur, owner.pop("relationships", None) or []
        )
        verification_evidence = _fetch_entity_verification_evidence(
            cur,
            owner["canonical_name"],
            allow_corporate_evidence=allow_corporate_evidence,
        )
        brief = _fetch_owner_brief(cur, owner["canonical_name"])

        return {
            "owner": {
                **owner,
                "aliases": owner.get("aliases") or [],
            },
            "relationships": relationships,
            "verification_evidence": verification_evidence,
            "brief": brief,
            "portfolio": {
                "parcel_count": len(parcels),
                "total_assessed": total_assessed,
                "parcels": parcels,
            },
            "delinquency": {
                "detail_available": delinquency_detail_available,
                "total_owed": total_delinquent,
                "delinquent_parcels": delinquent_pidns,
                "records": tax_claims,
            },
            "licenses": licenses,
        }
