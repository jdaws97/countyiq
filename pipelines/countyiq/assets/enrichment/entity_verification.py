"""Pass 1 — Entity Verification Dagster Asset.

Cross-references owner identities across all data sources and produces a
relationship graph stored in public.entity_graph.

Two stages:
  A) SQL pre-filter — finds candidate entity clusters via pg_trgm similarity
     and shared corporate office addresses.
  B) LLM reasoning — verifies each cluster, grouping records to the same
     entity, identifying relationship structures, and flagging rejected
     matches.

Controlled by COUNTYIQ_PASS1_MODEL or COUNTYIQ_OPENROUTER_MODEL.
If neither is set, returns status="skipped".
"""

import json
import traceback
from datetime import datetime, timezone

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.intelligence_common import compute_input_hash
from countyiq.lib.pass_llm_config import PassHarnessUnavailable, resolve_pass_harness
from countyiq.lib.pass1_entity_verification import (
    CANDIDATE_CLUSTERS_QUERY,
    build_entity_cluster_prompt,
    gather_cluster_records,
    parse_entity_verification_output,
    stable_cluster_key,
)
from countyiq.resources.database import DatabaseResource


# ---------------------------------------------------------------------------
# Union-Find cluster builder
# ---------------------------------------------------------------------------

def _build_clusters(pairs) -> list[list[str]]:
    """Build connected components from name pairs using union-find.

    Args:
        pairs: Iterable of rows. Each row is either a tuple/list
               (name_a, name_b, ...) or a dict with name_a/name_b keys.

    Returns:
        List of clusters, where each cluster is a list of name strings.
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        if x not in parent:
            parent[x] = x
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for row in pairs:
        name_a = row[0] if isinstance(row, (list, tuple)) else row.get("name_a", "")
        name_b = row[1] if isinstance(row, (list, tuple)) else row.get("name_b", "")
        if name_a and name_b:
            union(name_a, name_b)

    groups: dict[str, list[str]] = {}
    for name in parent:
        root = find(name)
        groups.setdefault(root, []).append(name)
    return list(groups.values())


# ---------------------------------------------------------------------------
# Dagster Asset
# ---------------------------------------------------------------------------

@asset(
    group_name="enrichment",
    description=(
        "Pass 1: cross-reference owner identities across parcels, tax claims, "
        "PLCB licenses, corporate entities, and proceedings to produce a "
        "verified entity relationship graph"
    ),
    deps=["pa_dos_entities", "proceeding_extraction", "development_signals"],
    kinds={"postgres", "llm"},
)
def entity_verification(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    log = context.log

    try:
        config, invoke_with_retry = resolve_pass_harness(
            log,
            pass_number=1,
            archive_label="pass1_entity",
            default_max_tokens=8192,
            default_thinking=True,
        )
    except PassHarnessUnavailable as exc:
        return _skipped_result(exc.reason)

    # ------------------------------------------------------------------
    # Stage A: Find candidate clusters
    # ------------------------------------------------------------------
    log.info("Stage A: executing candidate clusters query")
    pairs = database.execute(CANDIDATE_CLUSTERS_QUERY)

    if not pairs:
        log.info("No candidate entity clusters found.")
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("complete"),
                "clusters_processed": MetadataValue.int(0),
                "entities_created": MetadataValue.int(0),
                "errors": MetadataValue.int(0),
            }
        )

    clusters = _build_clusters(pairs)
    log.info("Stage A complete: %d pairs → %d clusters", len(pairs), len(clusters))

    # ------------------------------------------------------------------
    # Stage B: Verify each cluster via LLM
    # ------------------------------------------------------------------
    clusters_processed = 0
    entities_created = 0
    skipped = 0
    errors = 0

    for i, cluster_names in enumerate(clusters, 1):
        input_hash: str | None = None
        cluster_key = stable_cluster_key(cluster_names)
        try:
            # Gather records for this cluster using the public dict_cursor
            with database.dict_cursor() as cur:
                records = gather_cluster_records(cur, cluster_names)

            # Compute input hash for change detection
            input_hash = compute_input_hash(records)

            # Check if we've already processed this exact input
            existing = database.execute(
                """
                SELECT input_hash FROM meta.intelligence_passes
                WHERE pidn = %(cluster_key)s
                  AND pass_number = 1
                  AND status = 'complete'
                """,
                {"cluster_key": cluster_key},
            )
            prior_hash = None
            if existing:
                row = existing[0]
                prior_hash = row[0] if not isinstance(row, dict) else row.get("input_hash")
            if prior_hash == input_hash:
                log.debug("Cluster %s unchanged, skipping", cluster_key)
                skipped += 1
                continue

            # Build prompt and invoke LLM
            prompt = build_entity_cluster_prompt(records)
            result = invoke_with_retry(
                config, prompt, retries=1, archive_key=cluster_key,
            )

            if not result.success:
                log.warning(
                    "LLM failed for cluster %s: %s",
                    cluster_names[:2], result.error,
                )
                _update_pass_status(
                    database, cluster_key, 1, "error",
                    input_hash, result.error,
                )
                errors += 1
                continue

            # Parse and validate output
            parsed = parse_entity_verification_output(result.parsed or {})
            if "error" in parsed:
                log.warning(
                    "Invalid LLM output for cluster %s: %s",
                    cluster_names[:2], parsed["error"],
                )
                _update_pass_status(
                    database, cluster_key, 1, "error",
                    input_hash, parsed["error"],
                )
                errors += 1
                continue

            # Upsert entities to public.entity_graph.
            # Inject cluster_names so _upsert_entity can include the original
            # name variants (the SQL candidate cluster) in linked_names for
            # downstream entity lookup.
            matched_entity_ids: set[int] = set()
            for entity in parsed.get("entities", []):
                entity["cluster_names"] = cluster_names
                entity_id = _upsert_entity(
                    database,
                    entity,
                    exclude_entity_ids=matched_entity_ids,
                )
                if entity_id is not None:
                    matched_entity_ids.add(entity_id)
                entities_created += 1

            # Update pass tracking
            _update_pass_status(
                database, cluster_key, 1, "complete", input_hash,
            )
            clusters_processed += 1

            log.info(
                "Cluster [%s] complete: %d entities",
                ", ".join(cluster_names[:3]),
                len(parsed.get("entities", [])),
            )

            if (i % 25) == 0:
                log.info(
                    f"Progress: {i}/{len(clusters)} clusters "
                    f"({clusters_processed} processed, {skipped} skipped, {errors} errors)"
                )

        except Exception as exc:
            log.warning(
                f"Error processing cluster {cluster_names[:2]}: {exc}\n"
                f"{traceback.format_exc()}"
            )
            _update_pass_status(
                database, cluster_key, 1, "error",
                input_hash or "", str(exc),
            )
            errors += 1

    log.info(
        "Pass 1 complete: %d clusters processed, %d entities created, "
        "%d skipped, %d errors",
        clusters_processed, entities_created, skipped, errors,
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "model": MetadataValue.text(config.model_path),
            "thinking": MetadataValue.bool(config.thinking),
            "total_clusters": MetadataValue.int(len(clusters)),
            "clusters_processed": MetadataValue.int(clusters_processed),
            "clusters_skipped": MetadataValue.int(skipped),
            "entities_created": MetadataValue.int(entities_created),
            "errors": MetadataValue.int(errors),
        }
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_unique_strings(*groups) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group or []:
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            if not cleaned:
                continue
            if cleaned in seen:
                continue
            seen.add(cleaned)
            merged.append(cleaned)
    return merged


def _merge_linked_sources(existing: dict | None, incoming: dict | None) -> dict:
    merged: dict[str, list[str]] = {}
    for payload in (existing or {}, incoming or {}):
        if not isinstance(payload, dict):
            continue
        for key, values in payload.items():
            if isinstance(values, list):
                merged[key] = _merge_unique_strings(merged.get(key, []), values)
    return merged


def _merge_relationships(existing, incoming) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rel_list in (existing or [], incoming or []):
        if not isinstance(rel_list, list):
            continue
        for rel in rel_list:
            if not isinstance(rel, dict):
                continue
            key = (
                str(rel.get("relationship_type", "")).strip(),
                str(rel.get("related_entity", "")).strip(),
            )
            if not key[0] or not key[1] or key in seen:
                continue
            seen.add(key)
            merged.append(rel)
    return merged


def _candidate_names(entity: dict) -> list[str]:
    linked_records = entity.get("linked_records", {})
    return _merge_unique_strings(
        [entity.get("canonical_name", "")],
        linked_records.get("corporate_entities", []),
        linked_records.get("proceedings", []),
        entity.get("cluster_names", []),
    )


def _find_existing_entity_row(
    database: DatabaseResource,
    names: list[str],
    preferred_name: str,
    exclude_entity_ids: set[int] | None = None,
):
    if not names:
        return None

    exclude = list(exclude_entity_ids or [])
    with database.dict_cursor() as cur:
        cur.execute(
            """
            SELECT
                entity_id,
                canonical_name,
                entity_type,
                linked_names,
                linked_sources,
                relationships,
                verification_status,
                verification_reasoning,
                verified_at
            FROM public.entity_graph
            WHERE (
                canonical_name = ANY(%(names)s)
                OR COALESCE(linked_names, ARRAY[]::text[]) && %(names)s::text[]
            )
              AND (
                %(exclude_entity_ids)s::int[] = ARRAY[]::int[]
                OR entity_id <> ALL(%(exclude_entity_ids)s::int[])
              )
            ORDER BY
                (canonical_name = %(preferred_name)s) DESC,
                verified_at DESC NULLS LAST,
                entity_id
            LIMIT 1
            """,
            {
                "names": names,
                "preferred_name": preferred_name,
                "exclude_entity_ids": exclude,
            },
        )
        return cur.fetchone()


def _upsert_entity(
    database: DatabaseResource,
    entity: dict,
    exclude_entity_ids: set[int] | None = None,
) -> int | None:
    """Insert or update an entity in public.entity_graph."""
    linked_records = entity.get("linked_records", {})
    candidate_names = _candidate_names(entity)
    existing = _find_existing_entity_row(
        database,
        candidate_names,
        entity.get("canonical_name", ""),
        exclude_entity_ids=exclude_entity_ids,
    )

    canonical_name = (
        existing.get("canonical_name")
        if existing and existing.get("canonical_name")
        else entity.get("canonical_name", "")
    )
    linked_names = _merge_unique_strings(
        existing.get("linked_names") if existing else [],
        candidate_names,
    ) or None
    linked_sources = _merge_linked_sources(
        existing.get("linked_sources") if existing else {},
        linked_records,
    )
    relationships = _merge_relationships(
        existing.get("relationships") if existing else [],
        entity.get("relationships", []),
    )

    params = {
        "canonical_name": canonical_name,
        "entity_type": entity.get("entity_type", "unknown"),
        "linked_names": linked_names,
        "linked_sources": json.dumps(linked_sources),
        "relationships": json.dumps(relationships),
        "verification_status": "verified" if entity.get("confidence", 0) >= 0.7 else "tentative",
        "verification_reasoning": entity.get("reasoning", ""),
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }

    if existing:
        database.execute(
            """
            UPDATE public.entity_graph
            SET canonical_name = %(canonical_name)s,
                entity_type = %(entity_type)s,
                linked_names = %(linked_names)s,
                linked_sources = %(linked_sources)s::jsonb,
                relationships = %(relationships)s::jsonb,
                verification_status = %(verification_status)s,
                verification_reasoning = %(verification_reasoning)s,
                verified_at = %(verified_at)s
            WHERE entity_id = %(entity_id)s
            """,
            {**params, "entity_id": existing["entity_id"]},
        )
        return existing["entity_id"]

    rows = database.execute(
        """
        INSERT INTO public.entity_graph
            (canonical_name, entity_type, linked_names, linked_sources,
             relationships, verification_status, verification_reasoning, verified_at)
        VALUES
            (%(canonical_name)s, %(entity_type)s, %(linked_names)s,
             %(linked_sources)s::jsonb, %(relationships)s::jsonb,
             %(verification_status)s, %(verification_reasoning)s, %(verified_at)s)
        RETURNING entity_id
        """,
        params,
    ) or []
    return rows[0][0] if rows else None


def _update_pass_status(
    database: DatabaseResource,
    cluster_key: str,
    pass_number: int,
    status: str,
    input_hash: str,
    error_message: str | None = None,
) -> None:
    """Insert or update meta.intelligence_passes for a cluster."""
    database.execute(
        """
        INSERT INTO meta.intelligence_passes
            (pidn, pass_number, status, last_run_at, input_hash, error_message)
        VALUES
            (%(pidn)s, %(pass_number)s, %(status)s, NOW(), %(input_hash)s, %(error_message)s)
        ON CONFLICT (pidn, pass_number)
        DO UPDATE SET
            status = EXCLUDED.status,
            last_run_at = EXCLUDED.last_run_at,
            input_hash = EXCLUDED.input_hash,
            error_message = EXCLUDED.error_message
        """,
        {
            "pidn": cluster_key,
            "pass_number": pass_number,
            "status": status,
            "input_hash": input_hash,
            "error_message": error_message,
        },
    )


def _skipped_result(reason: str) -> MaterializeResult:
    """Return a MaterializeResult indicating the asset was skipped."""
    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("skipped"),
            "reason": MetadataValue.text(reason),
            "clusters_processed": MetadataValue.int(0),
            "entities_created": MetadataValue.int(0),
            "errors": MetadataValue.int(0),
        }
    )
