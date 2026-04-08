"""Pass 1 — Entity Verification Dagster Asset.

Cross-references owner identities across all data sources and produces a
relationship graph stored in public.entity_graph.

Two stages:
  A) SQL pre-filter — finds candidate entity clusters via pg_trgm similarity
     and shared corporate office addresses.
  B) LLM reasoning — verifies each cluster, grouping records to the same
     entity, identifying relationship structures, and flagging rejected
     matches.

Controlled by COUNTYIQ_OPENROUTER_MODEL (API slug) or COUNTYIQ_TEXT_MODEL
(local GGUF path). If neither is set, returns status="skipped".
"""

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.intelligence_common import compute_input_hash
from countyiq.lib.pass1_entity_verification import (
    CANDIDATE_CLUSTERS_QUERY,
    build_entity_cluster_prompt,
    gather_cluster_records,
    parse_entity_verification_output,
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

    # ------------------------------------------------------------------
    # Resolve backend and model (same pattern as signal_validation_batched)
    # ------------------------------------------------------------------
    openrouter_model = os.environ.get("COUNTYIQ_OPENROUTER_MODEL")
    local_model = os.environ.get("COUNTYIQ_TEXT_MODEL")

    if openrouter_model:
        backend = "openrouter"
        model_path = openrouter_model
    elif local_model:
        backend = "llama_cpp"
        model_path = local_model
    else:
        log.info(
            "Neither COUNTYIQ_OPENROUTER_MODEL nor COUNTYIQ_TEXT_MODEL is set — "
            "skipping Pass 1 entity verification."
        )
        return _skipped_result("no model configured")

    log.info(f"Pass 1: backend={backend} model={model_path}")

    # ------------------------------------------------------------------
    # Guard: llm_harness must be importable
    # ------------------------------------------------------------------
    try:
        from countyiq.lib.llm_harness import (
            HarnessConfig,
            get_preset_for_model,
            invoke_with_retry,
        )
    except ImportError as exc:
        log.warning("llm_harness import failed (%s) — skipping", exc)
        return _skipped_result("llm_harness import failed")

    thinking_enabled = os.environ.get("COUNTYIQ_THINKING", "true").lower() in ("1", "true", "yes")
    preset = get_preset_for_model(model_path, thinking=thinking_enabled, reasoning_task=True)

    config = HarnessConfig(
        model_path=model_path,
        backend=backend,
        max_tokens=8192,  # Entity resolution needs more output for large portfolios
        thinking=thinking_enabled,
        archive_label="pass1_entity",
        **preset,
    )

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
        cluster_key = cluster_names[0]  # first name in cluster is the tracking key
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
            for entity in parsed.get("entities", []):
                entity["cluster_names"] = cluster_names
                _upsert_entity(database, entity, Path(model_path).name)
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
            try:
                _update_pass_status(
                    database, cluster_key, 1, "error",
                    input_hash or "", str(exc),
                )
            except Exception:
                pass  # don't let status-write failure break the loop
            errors += 1

    log.info(
        "Pass 1 complete: %d clusters processed, %d entities created, "
        "%d skipped, %d errors",
        clusters_processed, entities_created, skipped, errors,
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "backend": MetadataValue.text(backend),
            "model": MetadataValue.text(model_path),
            "thinking": MetadataValue.bool(thinking_enabled),
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

def _upsert_entity(database: DatabaseResource, entity: dict, model_name: str) -> None:
    """Insert or update an entity in public.entity_graph."""
    database.execute(
        """
        INSERT INTO public.entity_graph
            (canonical_name, entity_type, linked_names, linked_sources,
             relationships, verification_status, verification_reasoning, verified_at)
        VALUES
            (%(canonical_name)s, %(entity_type)s, %(linked_names)s,
             %(linked_sources)s::jsonb, %(relationships)s::jsonb,
             %(verification_status)s, %(verification_reasoning)s, %(verified_at)s)
        ON CONFLICT (canonical_name)
        DO UPDATE SET
            entity_type = EXCLUDED.entity_type,
            linked_names = EXCLUDED.linked_names,
            linked_sources = EXCLUDED.linked_sources,
            relationships = EXCLUDED.relationships,
            verification_status = EXCLUDED.verification_status,
            verification_reasoning = EXCLUDED.verification_reasoning,
            verified_at = EXCLUDED.verified_at
        """,
        {
            "canonical_name": entity.get("canonical_name", ""),
            "entity_type": entity.get("entity_type", "unknown"),
            # linked_names must contain OWNER NAME ALIASES so that
            # ENTITY_GRAPH_QUERY (WHERE %(name)s = ANY(linked_names))
            # resolves entity lookups by name. The old code put PIDNs here
            # which would never match an owner_full string.
            #
            # Sources of name aliases:
            #   - corporate_entities: actual entity name strings
            #   - proceedings: applicant name strings
            #   - cluster_names: the original name variants from the SQL
            #     candidate cluster (the names that were similar enough to
            #     group together in the first place)
            "linked_names": list(
                set(
                    entity.get("linked_records", {}).get("corporate_entities", [])
                    + entity.get("linked_records", {}).get("proceedings", [])
                    + entity.get("cluster_names", [])
                )
            ) or None,
            "linked_sources": json.dumps(entity.get("linked_records", {})),
            "relationships": json.dumps(entity.get("relationships", [])),
            "verification_status": "verified" if entity.get("confidence", 0) >= 0.7 else "tentative",
            "verification_reasoning": entity.get("reasoning", ""),
            "verified_at": datetime.now(timezone.utc).isoformat(),
        },
    )


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
