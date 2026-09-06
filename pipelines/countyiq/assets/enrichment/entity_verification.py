"""Pass 1 — Entity Verification Dagster Asset.

Cross-references owner identities across all data sources and produces a
relationship graph stored in public.entity_graph.

Two stages:
  A) SQL pre-filter — finds candidate entity clusters via pg_trgm similarity
     and shared corporate office addresses.
  B) LLM reasoning — verifies each cluster, grouping records to the same
     entity, identifying relationship structures, and flagging rejected
     matches.

Requires ``COUNTYIQ_PASS1_ENABLED=true``; model selection is independent.
"""

import json
import os
import traceback
from datetime import UTC, datetime

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.error_budget import check_error_budget
from countyiq.lib.intelligence_autoresolve import auto_resolve_contradiction
from countyiq.lib.intelligence_common import (
    compute_input_hash,
    fetch_prior_pass_attempts,
    fetch_reusable_pass_hashes,
    pass_attempt_priority,
)
from countyiq.lib.intelligence_integrity import (
    entity_semantic_decision,
    inference_input_hash,
    record_inference_decision,
    record_validation_rejection,
    validate_entity_membership,
)
from countyiq.lib.pass1_entity_verification import (
    CANDIDATE_CLUSTERS_QUERY,
    DETERMINISTIC_VARIANT_VERSION,
    ENTITY_CANDIDATE_PAIRS_READY_QUERY,
    ENTITY_VERIFICATION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_deterministic_entity_resolution,
    build_entity_cluster_prompt,
    entity_trial_majority_decided,
    gather_cluster_records,
    merge_entity_trial_partitions,
    parse_entity_verification_output,
    select_pass1_clusters,
    stable_cluster_key,
)
from countyiq.lib.pass_llm_config import (
    PassHarnessUnavailable,
    PassItemBudget,
    PassSpendLimitExceeded,
    resolve_escalation_config,
    resolve_pass_harness,
)
from countyiq.lib.pass_schemas import PASS1_ENTITY_VERIFICATION_SCHEMA
from countyiq.resources.database import DatabaseResource

# A connected candidate component is an input unit, not an identity decision.
# Do not split oversized components: that would change the candidate graph.
# Defer them before dispatch so an incomplete prompt can neither spend money nor
# replace the existing entity projection.
MAX_CANDIDATE_NAMES_PER_CONTEXT = 40
MAX_DYNAMIC_PROMPT_CHARACTERS = 64_000

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
    deps=[
        "pa_dos_entities",
        "proceeding_extraction",
        "development_signals",
        "entity_candidate_pairs_refresh",
    ],
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
            # Static block goes out as a byte-identical system message so
            # providers with implicit prompt caching can reuse it per cluster.
            system_prompt=ENTITY_VERIFICATION_SYSTEM_PROMPT,
            json_schema=PASS1_ENTITY_VERIFICATION_SCHEMA,
            schema_name="pass1_entity_verification",
        )
    except PassHarnessUnavailable as exc:
        return _skipped_result(exc.reason)
    item_budget = PassItemBudget(1)

    # ------------------------------------------------------------------
    # Stage A: Find candidate clusters
    # ------------------------------------------------------------------
    ready_rows = database.execute(ENTITY_CANDIDATE_PAIRS_READY_QUERY) or []
    if not ready_rows or not bool(ready_rows[0][0]):
        raise RuntimeError(
            "public.entity_candidate_pairs is not populated; run "
            "entity_candidate_pairs_refresh before enabling Pass 1"
        )

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

    clusters, person_only_skipped = select_pass1_clusters(_build_clusters(pairs))
    log.info(
        "Stage A complete: %d pairs → %d clusters (%d person-only clusters skipped)",
        len(pairs),
        len(clusters),
        person_only_skipped,
    )

    # One upfront fetch of prior input hashes replaces a per-cluster SELECT
    # inside the loop.
    prior_hashes = fetch_reusable_pass_hashes(database, pass_number=1)
    prior_attempts = fetch_prior_pass_attempts(database, pass_number=1)
    clusters.sort(
        key=lambda names: pass_attempt_priority(
            stable_cluster_key(names), prior_attempts
        )
    )

    # N-trial partition voting (docs/decisions.md 2026-08-06): majority
    # pair-vote across trials, disagreement → abstain. Default 3 per the
    # selected lineup (stability probe: 97% pair agreement, ~$1.92/mo);
    # set COUNTYIQ_PASS1_TRIALS=1 to disable voting.
    n_trials = max(1, int(os.environ.get("COUNTYIQ_PASS1_TRIALS", "3")))
    adaptive_voting = os.environ.get(
        "COUNTYIQ_PASS1_ADAPTIVE_VOTING", "true"
    ).strip().lower() in {"1", "true", "yes", "on"}

    # Optional escalation cascade (docs/open-items.md): clusters the primary
    # model abstains on are re-run through a stronger model. Off unless
    # COUNTYIQ_PASS1_ESCALATION_MODEL is set.
    escalation_config = resolve_escalation_config(config, pass_number=1)
    if n_trials > 1:
        log.info("Pass 1: N=%d trial partition voting enabled", n_trials)
    if escalation_config is not None:
        log.info(
            "Pass 1: escalation cascade enabled → %s",
            escalation_config.model_path,
        )

    # ------------------------------------------------------------------
    # Stage B: Verify each cluster via LLM
    # ------------------------------------------------------------------
    clusters_processed = 0
    entities_created = 0
    abstentions_total = 0
    demotions_total = 0
    trial_calls = 0
    voting_early_stops = 0
    voting_calls_saved = 0
    escalations = 0
    deterministic_clusters = 0
    skipped = 0
    errors = 0
    clusters_deferred_context = 0
    spend_limit_reached = False

    for i, cluster_names in enumerate(clusters, 1):
        input_hash: str | None = None
        cluster_key = stable_cluster_key(cluster_names)
        try:
            if len(cluster_names) > MAX_CANDIDATE_NAMES_PER_CONTEXT:
                message = (
                    "deferred: context exceeds reviewed limits: "
                    f"candidate_names={len(cluster_names)} "
                    f"limit={MAX_CANDIDATE_NAMES_PER_CONTEXT}"
                )
                _update_pass_status(database, cluster_key, 1, "error", "", message)
                log.warning("Cluster %s %s", cluster_key, message)
                errors += 1
                clusters_deferred_context += 1
                continue

            # Gather records for this cluster using the public dict_cursor
            with database.dict_cursor() as cur:
                records = gather_cluster_records(cur, cluster_names)

            # Build before the reusable-hash skip so a previously accepted
            # projection cannot bypass a newly reviewed context bound.
            prompt = build_entity_cluster_prompt(records)
            if len(prompt) > MAX_DYNAMIC_PROMPT_CHARACTERS:
                message = (
                    "deferred: context exceeds reviewed limits: "
                    f"dynamic_prompt_characters={len(prompt)} "
                    f"limit={MAX_DYNAMIC_PROMPT_CHARACTERS}"
                )
                _update_pass_status(database, cluster_key, 1, "error", "", message)
                log.warning("Cluster %s %s", cluster_key, message)
                errors += 1
                clusters_deferred_context += 1
                continue

            deterministic_resolution = build_deterministic_entity_resolution(
                records,
                cluster_names,
            )
            execution_identity = (
                DETERMINISTIC_VARIANT_VERSION
                if deterministic_resolution is not None
                else (
                    f"{config.model_path}|trials={n_trials}|"
                    f"escalation={escalation_config.model_path if escalation_config else ''}"
                )
            )

            # Prompt/model changes rerun work; contradiction detection compares
            # the evidence-only source hash below.
            source_hash = compute_input_hash(records)
            input_hash = inference_input_hash(
                source_hash,
                requested_model=execution_identity,
                prompt_version=PROMPT_VERSION,
            )

            # Check if we've already processed this exact input
            if prior_hashes.get(cluster_key) == input_hash:
                log.debug("Cluster %s unchanged, skipping", cluster_key)
                skipped += 1
                continue

            if deterministic_resolution is None and not item_budget.claim(
                log, label="changed entity clusters"
            ):
                break

            # Invoke the LLM (N trials; N=1 by default).
            trial_parses: list[dict] = (
                [deterministic_resolution]
                if deterministic_resolution is not None
                else []
            )
            last_error: str | None = None
            decision_result = None
            decision_model = (
                DETERMINISTIC_VARIANT_VERSION
                if deterministic_resolution is not None
                else config.model_path
            )
            if deterministic_resolution is not None:
                deterministic_clusters += 1
                log.info(
                    "Cluster %s resolved by the anchored legal-name variant tier",
                    cluster_key,
                )
            for trial_idx in range(
                0 if deterministic_resolution is not None else n_trials
            ):
                trial_key = (
                    cluster_key if n_trials == 1 else f"{cluster_key}:trial-{trial_idx}"
                )
                trial_calls += 1
                result = invoke_with_retry(
                    config,
                    prompt,
                    retries=1,
                    archive_key=trial_key,
                )
                if not result.success:
                    last_error = result.error
                    log.warning(
                        "LLM failed for cluster %s (trial %d/%d): %s",
                        cluster_names[:2],
                        trial_idx + 1,
                        n_trials,
                        result.error,
                    )
                    continue
                trial_parsed = parse_entity_verification_output(result.parsed or {})
                if "error" in trial_parsed:
                    last_error = trial_parsed["error"]
                    log.warning(
                        "Invalid LLM output for cluster %s (trial %d/%d): %s",
                        cluster_names[:2],
                        trial_idx + 1,
                        n_trials,
                        trial_parsed["error"],
                    )
                    continue
                trial_parses.append(trial_parsed)
                decision_result = result
                remaining_trials = n_trials - (trial_idx + 1)
                if (
                    adaptive_voting
                    and remaining_trials > 0
                    and entity_trial_majority_decided(
                        trial_parses,
                        cluster_names,
                        target_trials=n_trials,
                    )
                ):
                    voting_early_stops += 1
                    voting_calls_saved += remaining_trials
                    log.debug(
                        "Cluster %s reached an irreversible majority after %d/%d trials",
                        cluster_key,
                        trial_idx + 1,
                        n_trials,
                    )
                    break

            if not trial_parses:
                _update_pass_status(
                    database,
                    cluster_key,
                    1,
                    "error",
                    input_hash,
                    last_error or "all trials failed",
                )
                errors += 1
                continue

            # Majority pair-vote across trials; disagreement → abstain.
            parsed = merge_entity_trial_partitions(trial_parses, cluster_names)
            demoted_here = (parsed.get("trial_stats") or {}).get("demoted_entities", 0)
            if demoted_here:
                demotions_total += demoted_here

            # Escalation cascade: abstained clusters go to the stronger
            # model; its (parsed) answer replaces the primary one.
            if escalation_config is not None and parsed.get("abstentions"):
                esc_result = invoke_with_retry(
                    escalation_config,
                    prompt,
                    retries=1,
                    archive_key=f"{cluster_key}:escalation",
                )
                if esc_result.success:
                    esc_parsed = parse_entity_verification_output(
                        esc_result.parsed or {}
                    )
                    if "error" not in esc_parsed:
                        parsed = esc_parsed
                        decision_result = esc_result
                        decision_model = escalation_config.model_path
                        escalations += 1
                        log.info(
                            "Cluster [%s]: escalated to %s",
                            ", ".join(cluster_names[:3]),
                            escalation_config.model_path,
                        )
                    else:
                        log.warning(
                            "Escalation output invalid for %s: %s — keeping primary",
                            cluster_key,
                            esc_parsed["error"],
                        )
                else:
                    log.warning(
                        "Escalation failed for %s: %s — keeping primary",
                        cluster_key,
                        esc_result.error,
                    )

            membership_errors = validate_entity_membership(
                parsed,
                records,
                cluster_names,
            )
            if membership_errors:
                record_validation_rejection(
                    database,
                    subject_key=cluster_key,
                    pass_number=1,
                    output_kind="entity_verification",
                    source_hash=source_hash,
                    input_hash=input_hash,
                    requested_model=execution_identity,
                    prompt_version=PROMPT_VERSION,
                    errors=membership_errors,
                )
                message = "; ".join(membership_errors)
                log.warning(
                    "Cluster %s failed identity membership validation: %s",
                    cluster_key,
                    message,
                )
                _update_pass_status(
                    database,
                    cluster_key,
                    1,
                    "error",
                    input_hash,
                    message,
                )
                errors += 1
                continue

            evidence_refs = sorted(
                {
                    f"{group}:{identifier}"
                    for entity in parsed.get("entities", [])
                    for group, identifiers in (
                        entity.get("linked_records") or {}
                    ).items()
                    for identifier in identifiers or []
                }
                | {f"candidate:{name}" for name in cluster_names}
            )
            if (parsed.get("trial_stats") or {}).get("demoted_entities"):
                evidence_refs.append("trial:voting")
            gate = record_inference_decision(
                database,
                subject_key=cluster_key,
                pass_number=1,
                output_kind="entity_verification",
                decision_key="partition",
                source_hash=source_hash,
                input_hash=input_hash,
                requested_model=decision_model,
                served_model=(
                    decision_result.metadata.get("served_model")
                    if decision_result
                    else None
                ),
                provider=(
                    decision_result.metadata.get("provider")
                    if decision_result
                    else None
                ),
                prompt_version=PROMPT_VERSION,
                payload=parsed,
                semantic_decision=entity_semantic_decision(parsed),
                evidence_refs=evidence_refs,
            )
            if not gate.accepted:
                auto = auto_resolve_contradiction(database, gate.contradiction_id, log)
                if auto.resolved:
                    log.info(
                        "Contradiction %s auto-resolved (%s): %s",
                        gate.contradiction_id,
                        auto.resolution,
                        auto.rationale,
                    )
                    continue
                message = (
                    f"quarantined as contradiction {gate.contradiction_id}: "
                    f"{gate.reason}"
                )
                log.warning("Cluster %s %s", cluster_key, message)
                _update_pass_status(
                    database,
                    cluster_key,
                    1,
                    "error",
                    input_hash,
                    message,
                )
                errors += 1
                continue

            # The accepted partition replaces this cluster atomically. This
            # removes memberships a new evidence version rejects/abstains on;
            # historical assignments remain recoverable in the ledger.
            entities_created += _replace_cluster_entities(
                database,
                parsed.get("entities", []),
                cluster_names,
                inference_id=gate.inference_id,
            )

            abstained_here = len(parsed.get("abstentions", []))
            if abstained_here:
                abstentions_total += abstained_here
                for abstention in parsed["abstentions"]:
                    log.info(
                        "Cluster [%s]: model abstained on %s — %s",
                        ", ".join(cluster_names[:3]),
                        abstention.get("names", [])[:4],
                        (abstention.get("reason") or "")[:160],
                    )

            # Update pass tracking
            _update_pass_status(
                database,
                cluster_key,
                1,
                "complete",
                input_hash,
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

        except PassSpendLimitExceeded as exc:
            spend_limit_reached = True
            log.info(
                "Pass 1 dollar ceiling reached; remaining clusters are deferred: %s",
                exc,
            )
            break
        except Exception as exc:
            log.warning(
                f"Error processing cluster {cluster_names[:2]}: {exc}\n"
                f"{traceback.format_exc()}"
            )
            _update_pass_status(
                database,
                cluster_key,
                1,
                "error",
                input_hash or "",
                str(exc),
            )
            errors += 1

    log.info(
        "Pass 1 complete: %d clusters processed, %d entities created, "
        "%d skipped, %d errors",
        clusters_processed,
        entities_created,
        skipped,
        errors,
    )
    check_error_budget(
        log,
        label="pass1_entity_verification",
        errors=errors,
        total=clusters_processed + errors,
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "model": MetadataValue.text(config.model_path),
            "thinking": MetadataValue.bool(config.thinking),
            "n_trials": MetadataValue.int(n_trials),
            "adaptive_voting": MetadataValue.bool(adaptive_voting),
            "llm_trial_calls": MetadataValue.int(trial_calls),
            "voting_early_stops": MetadataValue.int(voting_early_stops),
            "voting_calls_saved": MetadataValue.int(voting_calls_saved),
            "deterministic_clusters": MetadataValue.int(deterministic_clusters),
            "total_clusters": MetadataValue.int(len(clusters)),
            "person_only_clusters_skipped": MetadataValue.int(person_only_skipped),
            "budget_mode": MetadataValue.text(item_budget.mode),
            "item_limit": (
                MetadataValue.int(item_budget.limit)
                if item_budget.limit is not None
                else MetadataValue.text("cost-only")
            ),
            "items_claimed": MetadataValue.int(item_budget.claimed),
            "spend_limit_reached": MetadataValue.bool(spend_limit_reached),
            "clusters_processed": MetadataValue.int(clusters_processed),
            "clusters_skipped": MetadataValue.int(skipped),
            "entities_created": MetadataValue.int(entities_created),
            "abstentions": MetadataValue.int(abstentions_total),
            "voting_demotions": MetadataValue.int(demotions_total),
            "escalations": MetadataValue.int(escalations),
            "clusters_deferred_context": MetadataValue.int(clusters_deferred_context),
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
        entity.get("member_names", []),
        linked_records.get("corporate_entities", []),
        linked_records.get("proceedings", []),
    )


def _replace_cluster_entities(
    database: DatabaseResource,
    entities: list[dict],
    cluster_names: list[str],
    *,
    inference_id: int,
) -> int:
    """Atomically replace one candidate cluster's active graph projection."""
    with database.transaction() as cur:
        cur.execute(
            """
            DELETE FROM public.entity_graph
            WHERE canonical_name = ANY(%s)
               OR COALESCE(linked_names, ARRAY[]::text[]) && %s::text[]
            """,
            (cluster_names, cluster_names),
        )

        inserted = 0
        for entity in entities:
            linked_records = entity.get("linked_records", {})
            cur.execute(
                """
                INSERT INTO public.entity_graph
                    (canonical_name, entity_type, linked_names, linked_sources,
                     relationships, verification_status,
                     verification_reasoning, verified_at, active_inference_id)
                VALUES
                    (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
                """,
                (
                    entity.get("canonical_name", ""),
                    entity.get("entity_type", "unknown"),
                    _candidate_names(entity) or None,
                    json.dumps(_merge_linked_sources({}, linked_records)),
                    json.dumps(
                        _merge_relationships([], entity.get("relationships", []))
                    ),
                    ("verified" if entity.get("confidence", 0) >= 0.7 else "tentative"),
                    entity.get("reasoning", ""),
                    datetime.now(UTC).isoformat(),
                    inference_id,
                ),
            )
            inserted += 1
    return inserted


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
