"""Entity resolution — match owners across parcels, tax claims, PLCB, PA businesses.

Populates public.owners and public.owner_source_links with:
- Name normalization (strip suffixes, standardize format)
- Entity type classification (person / business / trust / government)
- Shared-mailing-address ambiguity detection (address alone never merges owners)
- Entity-graph merge: Pass 1 (entity_verification) linked_names collapse
  into the same owner, carrying verification metadata and relationships
- Stable owner_id: owners upsert by canonical_name; the sequence is never
  restarted, so profile URLs survive rebuilds
- Municipality-scoped PLCB matching driven by the pg_trgm index
"""

import json
import re

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)
from psycopg2.extras import execute_values

from countyiq.lib.entity_types import (
    BUSINESS_INDICATORS,
    GOVERNMENT_INDICATORS,
    TRUST_INDICATORS,
    classify_entity,
)
from countyiq.resources.database import DatabaseResource

__all__ = ["classify_entity", "classify_group", "owners"]

# Suffixes to strip for normalization
_ENTITY_SUFFIXES = re.compile(
    r"\s+(LLC|INC|CORP|CORPORATION|LTD|LP|LLP|LLLP|PA|"
    r"TRUST|ESTATE|EST|ETAL|ET\s*AL|"
    r"JR|SR|II|III|IV|MD|ESQ|PHD|DDS|"
    r"CO|COMPANY|ASSOC|ASSOCIATION|FOUNDATION|"
    r"REVOCABLE|IRREVOCABLE|LIVING|FAMILY)\s*\.?\s*$",
    re.IGNORECASE,
)

# Name-type indicators live in countyiq.lib.entity_types so the Pass 1
# cluster selector and owner resolution agree on what an organization is.
_GOVERNMENT_INDICATORS = GOVERNMENT_INDICATORS
_TRUST_INDICATORS = TRUST_INDICATORS
_BUSINESS_INDICATORS = BUSINESS_INDICATORS

# Minimum useful mailing address for ambiguity detection; anything shorter is
# likely a fragment ("YORK PA") and not a meaningful comparison key.
_MIN_MAIL_ADDR_LEN = 8

# Confidence by how a raw name reached its owner cluster.
_TIER_CONFIDENCE = {
    "normalized": 1.0,
    "entity_graph": 0.9,
}


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
    n = re.sub(r"\([^)]*\)", "", n)
    # Strip entity suffixes (iteratively — "SMITH LLC INC" → "SMITH")
    for _ in range(3):
        prev = n
        n = _ENTITY_SUFFIXES.sub("", n).strip()
        if n == prev:
            break
    # Collapse whitespace
    n = re.sub(r"\s+", " ", n).strip()
    # Remove trailing punctuation
    n = n.rstrip(".,;:&-")
    return n.strip()


def normalize_mail_addr(addr: str | None) -> str:
    """Normalize a mailing address for cluster merging.

    Uppercase, collapse whitespace, strip punctuation. Returns "" when the
    address is too short to be a safe merge key.
    """
    if not addr:
        return ""
    a = re.sub(r"[^A-Z0-9 ]", " ", addr.upper())
    a = re.sub(r"\s+", " ", a).strip()
    return a if len(a) >= _MIN_MAIL_ADDR_LEN else ""


# Ordered most-specific first: a group with any government variant is
# government, else trust, else business, else person.
_TYPE_PRIORITY = ("government", "trust", "business", "person")


def classify_group(raw_names) -> str:
    """Classify a group of raw name variants by priority vote."""
    types = {classify_entity(raw) for raw in raw_names}
    for entity_type in _TYPE_PRIORITY:
        if entity_type in types:
            return entity_type
    return "unknown"


def _shared_business_address_groups(
    norm_groups: dict[str, list[str]],
    group_type: dict[str, str],
    mail_addrs: dict[str, str],
) -> dict[str, list[str]]:
    """Return ambiguous business-name groups without treating them as identity.

    Registered agents, law firms, accountants, and virtual offices routinely
    host unrelated businesses at one address. Shared address is useful review
    evidence, but it is not sufficient evidence for an automatic union.
    """
    addr_index: dict[str, set[str]] = {}
    for key, raws in norm_groups.items():
        if group_type.get(key) != "business":
            continue
        for address in {mail_addrs.get(raw, "") for raw in raws}:
            if address:
                addr_index.setdefault(address, set()).add(key)
    return {
        address: sorted(keys) for address, keys in addr_index.items() if len(keys) >= 2
    }


class _UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        if x not in self.parent:
            self.parent[x] = x
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[ra] = rb
        return True


@asset(
    group_name="enrichment",
    deps=["municipality_join", "entity_verification"],
    description=(
        "Entity resolution — single owner identity space across parcels, "
        "tax claims, PLCB licenses, and the Pass 1 entity graph"
    ),
    kinds={"postgres"},
)
def owner_resolution(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    """Resolve owner entities and upsert public.owners with stable IDs."""

    log = context.log
    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        log.info("Starting entity resolution...")

        # ------------------------------------------------------------------
        # Step 1: load raw owner names with parcel counts + dominant mail addr
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT
                owner_full,
                COUNT(*) AS parcel_count,
                mode() WITHIN GROUP (ORDER BY NULLIF(TRIM(mail_addr_full), '')) AS mail_addr
            FROM staging.parcels
            WHERE valid_to IS NULL
              AND owner_full IS NOT NULL AND TRIM(owner_full) != ''
            GROUP BY owner_full
        """)
        raw_rows = cur.fetchall()

        parcel_counts: dict[str, int] = {}
        mail_addrs: dict[str, str] = {}
        norm_groups: dict[str, list[str]] = {}
        for raw, count, mail in raw_rows:
            parcel_counts[raw] = count
            mail_addrs[raw] = normalize_mail_addr(mail)
            normed = normalize_name(raw)
            if normed:
                norm_groups.setdefault(normed, []).append(raw)

        log.info(
            f"Normalized {len(raw_rows)} raw names into {len(norm_groups)} name groups"
        )

        # ------------------------------------------------------------------
        # Step 2: detect shared business addresses, but do not merge on address
        # alone. Registered-agent and virtual-office addresses are common.
        # ------------------------------------------------------------------
        uf = _UnionFind()
        group_type = {key: classify_group(raws) for key, raws in norm_groups.items()}
        ambiguous_addresses = _shared_business_address_groups(
            norm_groups, group_type, mail_addrs
        )
        ambiguous_business_groups = sum(
            len(keys) for keys in ambiguous_addresses.values()
        )
        log.info(
            "Shared-address review evidence: %d addresses across %d business groups; "
            "0 automatic merges",
            len(ambiguous_addresses),
            ambiguous_business_groups,
        )
        for address, keys in sorted(
            ambiguous_addresses.items(), key=lambda item: len(item[1]), reverse=True
        )[:5]:
            log.warning(
                "Mailing address is shared by %d business groups and was not merged: %s",
                len(keys),
                address[:60],
            )

        # ------------------------------------------------------------------
        # Step 3: fold in the Pass 1 entity graph (linked_names merge +
        # verification metadata carried onto the resolved owner)
        # ------------------------------------------------------------------
        graph_merged: set[str] = set()
        graph_meta: dict[str, dict] = {}  # group key -> latest graph row
        cur.execute("""
            SELECT canonical_name, linked_names, relationships,
                   verification_status, verification_reasoning, verified_at
            FROM public.entity_graph
        """)
        graph_rows = cur.fetchall()
        graph_merges = 0
        for (
            g_canonical,
            linked,
            relationships,
            status,
            reasoning,
            verified_at,
        ) in graph_rows:
            names = [g_canonical] + list(linked or [])
            keys = []
            for name in names:
                normed = normalize_name(name or "")
                if normed in norm_groups:
                    keys.append(normed)
            keys = list(dict.fromkeys(keys))
            if not keys:
                continue
            meta = {
                "linked_names": [n for n in names if n],
                "relationships": relationships,
                "verification_status": status,
                "verification_reasoning": reasoning,
                "verified_at": verified_at,
            }
            for key in keys:
                existing = graph_meta.get(key)
                if not existing or _graph_meta_newer(meta, existing):
                    graph_meta[key] = meta
            for other in keys[1:]:
                if uf.union(keys[0], other):
                    graph_merges += 1
                graph_merged.add(other)
            if len(keys) > 1:
                graph_merged.add(keys[0])
        log.info(
            f"Entity-graph merge: {len(graph_rows)} graph rows, {graph_merges} group merges"
        )

        # ------------------------------------------------------------------
        # Step 4: build final clusters
        # ------------------------------------------------------------------
        clusters: dict[str, list[str]] = {}  # root group key -> member group keys
        for key in norm_groups:
            clusters.setdefault(uf.find(key), []).append(key)

        map_rows = []  # (raw_name, canonical_name, match_tier, confidence)
        cluster_rows = []  # per-owner metadata
        for members in clusters.values():
            raws = [raw for key in members for raw in norm_groups[key]]
            # Canonical = variant holding the most parcels; tie → shortest name
            canonical = min(raws, key=lambda r: (-parcel_counts[r], len(r)))
            canonical_key = normalize_name(canonical)
            entity_type = classify_group(raws)

            # Latest graph metadata across member groups, if any
            metas = [graph_meta[key] for key in members if key in graph_meta]
            meta = None
            if metas:
                meta = max(
                    metas,
                    key=lambda m: (m["verified_at"] is not None, m["verified_at"]),
                )

            alias_pool = [r for r in raws if r != canonical]
            if meta:
                alias_pool.extend(
                    n for n in meta["linked_names"] if n != canonical and n not in raws
                )
            aliases = list(dict.fromkeys(alias_pool)) or None

            cluster_rows.append(
                (
                    canonical,
                    entity_type,
                    aliases,
                    _json_or_none(meta["relationships"]) if meta else None,
                    meta["verification_status"] if meta else None,
                    meta["verification_reasoning"] if meta else None,
                    meta["verified_at"] if meta else None,
                )
            )

            for key in members:
                if key in graph_merged and key != canonical_key:
                    tier = "entity_graph"
                else:
                    tier = "normalized"
                for raw in norm_groups[key]:
                    map_rows.append((raw, canonical, tier, _TIER_CONFIDENCE[tier]))

        log.info(f"{len(clusters)} resolved owners from {len(norm_groups)} name groups")

        # ------------------------------------------------------------------
        # Step 5: stage the mapping and upsert owners (stable owner_id —
        # no delete-all, no sequence restart)
        # ------------------------------------------------------------------
        cur.execute("""
            CREATE TEMP TABLE _owner_name_map (
                raw_name TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                match_tier TEXT NOT NULL,
                confidence NUMERIC(3, 2) NOT NULL
            ) ON COMMIT DROP
        """)
        execute_values(
            cur,
            "INSERT INTO _owner_name_map (raw_name, canonical_name, match_tier, confidence) VALUES %s",
            map_rows,
            page_size=5000,
        )

        cur.execute("""
            CREATE TEMP TABLE _owner_clusters (
                canonical_name TEXT PRIMARY KEY,
                entity_type TEXT,
                aliases TEXT[],
                relationships JSONB,
                verification_status TEXT,
                verification_reasoning TEXT,
                verified_at TIMESTAMPTZ
            ) ON COMMIT DROP
        """)
        execute_values(
            cur,
            """INSERT INTO _owner_clusters
               (canonical_name, entity_type, aliases, relationships,
                verification_status, verification_reasoning, verified_at)
               VALUES %s""",
            cluster_rows,
            page_size=5000,
        )

        cur.execute("DELETE FROM public.owner_source_links")

        cur.execute("""
            INSERT INTO public.owners (
                canonical_name, entity_type, parcel_count, municipality,
                canonical_addr, aliases, relationships,
                verification_status, verification_reasoning, verified_at,
                first_seen, last_seen
            )
            SELECT
                c.canonical_name, c.entity_type, s.parcel_count, s.municipality,
                s.canonical_addr, c.aliases, c.relationships,
                c.verification_status, c.verification_reasoning, c.verified_at,
                CURRENT_DATE, CURRENT_DATE
            FROM _owner_clusters c
            JOIN (
                SELECT
                    m.canonical_name,
                    COUNT(p.pidn) AS parcel_count,
                    mode() WITHIN GROUP (ORDER BY p.municipality) AS municipality,
                    mode() WITHIN GROUP (ORDER BY NULLIF(TRIM(p.mail_addr_full), '')) AS canonical_addr
                FROM _owner_name_map m
                JOIN staging.parcels p
                    ON p.owner_full = m.raw_name AND p.valid_to IS NULL
                GROUP BY m.canonical_name
            ) s USING (canonical_name)
            ON CONFLICT (canonical_name) DO UPDATE SET
                entity_type            = EXCLUDED.entity_type,
                parcel_count           = EXCLUDED.parcel_count,
                municipality           = EXCLUDED.municipality,
                canonical_addr         = EXCLUDED.canonical_addr,
                aliases                = EXCLUDED.aliases,
                relationships          = EXCLUDED.relationships,
                verification_status    = EXCLUDED.verification_status,
                verification_reasoning = EXCLUDED.verification_reasoning,
                verified_at            = EXCLUDED.verified_at,
                last_seen              = CURRENT_DATE,
                updated_at             = NOW()
        """)
        owner_count = cur.rowcount

        cur.execute("""
            DELETE FROM public.owners o
            WHERE NOT EXISTS (
                SELECT 1 FROM _owner_clusters c
                WHERE c.canonical_name = o.canonical_name
            )
        """)
        owners_removed = cur.rowcount
        log.info(
            f"Upserted {owner_count} owners, removed {owners_removed} stale owners"
        )

        # ------------------------------------------------------------------
        # Step 6: link parcels to owners
        # ------------------------------------------------------------------
        cur.execute("""
            INSERT INTO public.owner_source_links
                (owner_id, source_type, source_id, source_name, source_address,
                 match_tier, confidence)
            SELECT
                o.owner_id, 'parcel', p.pidn, p.owner_full, p.propadr,
                m.match_tier, m.confidence
            FROM _owner_name_map m
            JOIN public.owners o ON o.canonical_name = m.canonical_name
            JOIN staging.parcels p
                ON p.owner_full = m.raw_name AND p.valid_to IS NULL
            ON CONFLICT (source_type, source_id) DO NOTHING
        """)
        parcel_links = cur.rowcount
        log.info(f"Linked {parcel_links} parcel records")

        # Step 7: match tax claims via PIDN join (high confidence)
        cur.execute("""
            INSERT INTO public.owner_source_links
                (owner_id, source_type, source_id, source_name, source_address,
                 match_tier, confidence)
            SELECT DISTINCT
                osl.owner_id,
                'tax_claim',
                tc.pidn || ':' || tc.tax_year::text || ':' || tc.authority_name,
                tc.owner_name,
                tc.property_address,
                'pidn_join',
                0.95
            FROM public.owner_source_links osl
            JOIN staging.tax_claims tc
                ON tc.pidn = osl.source_id AND tc.valid_to IS NULL AND tc.total > 0
            WHERE osl.source_type = 'parcel'
            ON CONFLICT (source_type, source_id) DO NOTHING
        """)
        tax_links = cur.rowcount
        log.info(f"Linked {tax_links} tax claim records via PIDN")

        # ------------------------------------------------------------------
        # Step 8: PLCB licensees. The % operator honors
        # pg_trgm.similarity_threshold and lets the planner drive the match
        # from the small license table through idx_owners_name (GIN trgm)
        # instead of computing similarity() across the full cross product.
        # ------------------------------------------------------------------
        cur.execute("SET LOCAL pg_trgm.similarity_threshold = 0.6")
        cur.execute("""
            INSERT INTO public.owner_source_links
                (owner_id, source_type, source_id, source_name, source_address,
                 match_tier, confidence)
            SELECT DISTINCT ON (p.lid)
                o.owner_id,
                'plcb_license',
                p.lid,
                COALESCE(p.premises_owner, p.licensee),
                p.premises_address,
                'fuzzy_name_scoped',
                similarity(o.canonical_name, COALESCE(p.premises_owner, p.licensee))
            FROM staging.plcb_licenses p
            JOIN public.owners o
                ON o.canonical_name % COALESCE(p.premises_owner, p.licensee)
            JOIN public.owner_source_links osl
                ON o.owner_id = osl.owner_id AND osl.source_type = 'parcel'
            JOIN staging.parcels par
                ON par.pidn = osl.source_id AND par.valid_to IS NULL
            WHERE p.valid_to IS NULL AND UPPER(p.status) = 'ACTIVE'
              AND UPPER(p.municipality) LIKE UPPER(COALESCE(par.municipality, '___NOMATCH___')) || '%%'
            ORDER BY p.lid, similarity(o.canonical_name, COALESCE(p.premises_owner, p.licensee)) DESC
            ON CONFLICT (source_type, source_id) DO NOTHING
        """)
        plcb_scoped = cur.rowcount
        log.info(
            f"Linked {plcb_scoped} PLCB licenses via municipality-scoped matching (>0.6)"
        )

        # Fallback: unscoped at a higher threshold for licenses not matched above
        cur.execute("SET LOCAL pg_trgm.similarity_threshold = 0.75")
        cur.execute("""
            INSERT INTO public.owner_source_links
                (owner_id, source_type, source_id, source_name, source_address,
                 match_tier, confidence)
            SELECT DISTINCT ON (p.lid)
                o.owner_id,
                'plcb_license',
                p.lid,
                COALESCE(p.premises_owner, p.licensee),
                p.premises_address,
                'fuzzy_name_unscoped',
                similarity(o.canonical_name, COALESCE(p.premises_owner, p.licensee)) * 0.8
            FROM staging.plcb_licenses p
            JOIN public.owners o
                ON o.canonical_name % COALESCE(p.premises_owner, p.licensee)
            WHERE p.valid_to IS NULL AND UPPER(p.status) = 'ACTIVE'
            ORDER BY p.lid, similarity(o.canonical_name, COALESCE(p.premises_owner, p.licensee)) DESC
            ON CONFLICT (source_type, source_id) DO NOTHING
        """)
        plcb_unscoped = cur.rowcount
        log.info(
            f"Linked {plcb_unscoped} additional PLCB licenses via unscoped matching (>0.75)"
        )

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
            "owners_removed": MetadataValue.int(owners_removed),
            "addr_group_merges": MetadataValue.int(0),
            "ambiguous_shared_addresses": MetadataValue.int(len(ambiguous_addresses)),
            "ambiguous_business_groups": MetadataValue.int(ambiguous_business_groups),
            "graph_group_merges": MetadataValue.int(graph_merges),
            "parcel_links": MetadataValue.int(parcel_links),
            "tax_claim_links": MetadataValue.int(tax_links),
            "plcb_scoped_links": MetadataValue.int(plcb_scoped),
            "plcb_unscoped_links": MetadataValue.int(plcb_unscoped),
        }
    )


def _json_or_none(value):
    """psycopg2 needs JSON-typed params as strings; pass through NULLs."""
    if value is None:
        return None
    return json.dumps(value)


def _graph_meta_newer(candidate: dict, existing: dict) -> bool:
    """Prefer graph rows with a verified_at, then the most recent one."""
    if existing["verified_at"] is None:
        return candidate["verified_at"] is not None
    if candidate["verified_at"] is None:
        return False
    return candidate["verified_at"] > existing["verified_at"]
