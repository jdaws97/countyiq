"""Pass 3b — owner-rollup briefs (portfolio-level intelligence).

For every resolved owner in ``public.owners`` with ≥3 parcels carrying
medium-or-high-significance Pass 2 evidence, generate a single
portfolio-level brief via ``public.owner_briefs``. Experiment E showed
these score 4.75 vs 1.00 on portfolio-pattern insight compared to
reading N parcel briefs independently.
"""

import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, datetime

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.error_budget import check_error_budget
from countyiq.lib.intelligence_common import (
    fetch_prior_pass_attempts,
    pass_attempt_priority,
    strip_volatile_evidence,
)
from countyiq.lib.intelligence_autoresolve import auto_resolve_contradiction
from countyiq.lib.intelligence_integrity import (
    content_hash,
    inference_input_hash,
    owner_brief_semantic_decision,
    record_inference_decision,
    signal_version_refs,
    record_validation_rejection,
    validate_owner_brief_citations,
)
from countyiq.lib.pass3_owner_briefs import (
    OWNER_PORTFOLIO_QUERY,
    OWNER_ROLLUP_SYSTEM_PROMPT,
    OWNERS_NEEDING_BRIEFS_QUERY,
    PORTFOLIO_EVIDENCE_QUERY,
    PROMPT_VERSION,
    UPSERT_OWNER_BRIEF,
    build_owner_rollup_prompt,
    owner_brief_context,
    parse_owner_brief_output,
)
from countyiq.lib.pass_llm_config import (
    PassHarnessUnavailable,
    PassItemBudget,
    PassSpendLimitExceeded,
    resolve_pass_harness,
)
from countyiq.lib.pass_schemas import PASS3B_OWNER_BRIEF_SCHEMA
from countyiq.lib.signal_policy import INTERPRETIVE_SIGNAL_KEYS_SQL
from countyiq.resources.database import DatabaseResource


def _owner_subject_key(canonical_name: str) -> str:
    return (
        "owner_brief:" + hashlib.sha256(canonical_name.encode("utf-8")).hexdigest()[:20]
    )


@asset(
    group_name="enrichment",
    description=(
        "Pass 3b (owner rollup): one portfolio-level brief per owner with "
        "≥3 parcels carrying validated signals. Surfaces strategy, "
        "concentration, and actionable recommendation."
    ),
    # owner_resolution upserts public.owners in one transaction; briefs read
    # the resolved owner set, so keep the ordering dependency.
    deps=["signal_validation_batched", "owner_resolution"],
    kinds={"postgres", "llm"},
)
def owner_briefs(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    log = context.log
    if os.environ.get("COUNTYIQ_PASS3_MODE", "legacy").strip().lower() == "records":
        return MaterializeResult(
            metadata={
                "status": "skipped",
                "reason": "Record explanation mode is enabled",
            }
        )

    # Projection cleanup is deterministic and must still run when Pass 3 is
    # disabled or unavailable.
    database.execute(
        f"""
        DELETE FROM public.owner_briefs ob
        WHERE NOT EXISTS (
            SELECT 1
            FROM public.owners o
            JOIN public.owner_source_links osl
              ON osl.owner_id = o.owner_id AND osl.source_type = 'parcel'
            JOIN public.evidence e ON e.pidn = osl.source_id
            WHERE o.canonical_name = ob.canonical_name
              AND e.signal_key IN ({INTERPRETIVE_SIGNAL_KEYS_SQL})
              AND e.validation_status IN ('confirmed', 'upgraded', 'downgraded')
              AND e.adjusted_significance IN ('high', 'medium')
            GROUP BY o.owner_id
            HAVING COUNT(DISTINCT osl.source_id) >= 3
        )
        """
    )

    try:
        config, invoke_with_retry = resolve_pass_harness(
            log,
            pass_number=3,
            archive_label="pass3_owner_briefs",
            default_max_tokens=2048,
            json_schema=PASS3B_OWNER_BRIEF_SCHEMA,
            schema_name="pass3b_owner_brief",
            # Static block goes out as a byte-identical system message so
            # providers with implicit prompt caching can reuse it per owner.
            system_prompt=OWNER_ROLLUP_SYSTEM_PROMPT,
        )
    except PassHarnessUnavailable as exc:
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text(f"skipped ({exc.reason})"),
                "briefs_created": MetadataValue.int(0),
            }
        )
    item_budget = PassItemBudget(3)
    # Keep Pass 3 temperature low — narratives should be consistent with
    # the committed structured fields, per experiment C.
    config = replace(config, temperature=min(config.temperature, 0.3))

    owner_rows = database.execute(OWNERS_NEEDING_BRIEFS_QUERY)
    owners_needing = [
        (r["owner_id"], r["canonical_name"]) if isinstance(r, dict) else (r[0], r[1])
        for r in (owner_rows or [])
    ]
    prior_attempts = fetch_prior_pass_attempts(database, pass_number=3)
    owners_needing.sort(
        key=lambda owner: pass_attempt_priority(
            _owner_subject_key(owner[1]), prior_attempts
        )
    )
    if not owners_needing:
        log.info("No owners eligible for rollup briefs.")
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("complete"),
                "owners_eligible": MetadataValue.int(0),
                "briefs_created": MetadataValue.int(0),
            }
        )

    log.info(f"{len(owners_needing)} owners eligible for rollup briefs")
    briefs_created = 0
    skipped_unchanged = 0
    errors = 0
    spend_limit_reached = False

    for i, (owner_id, canonical_name) in enumerate(owners_needing, 1):
        subject_key = _owner_subject_key(canonical_name)
        input_hash: str | None = None
        try:
            with database.read_snapshot() as cur:
                cur.execute(OWNER_PORTFOLIO_QUERY, {"owner_id": owner_id})
                owner = cur.fetchone()
                if not owner:
                    continue
                owner = dict(owner)
                pidns = owner["pidns"] or []
                if not pidns:
                    continue
                cur.execute(PORTFOLIO_EVIDENCE_QUERY, {"pidns": pidns})
                evidence_rows = [dict(r) for r in cur.fetchall()]

            if not evidence_rows:
                continue

            signal_dependencies = signal_version_refs(evidence_rows)
            owner_context = owner_brief_context(owner, evidence_rows)
            prompt = build_owner_rollup_prompt(owner, evidence_rows)

            # Hash stable evidence and its inference identity. Revalidation can
            # replace a source version without changing rendered prose; that
            # replacement must regenerate the dependency receipt too.
            source_hash = content_hash(
                {
                    "owner": owner_context,
                    "evidence": [
                        {
                            key: (
                                strip_volatile_evidence(row.get(key))
                                if key == "evidence_data"
                                else row.get(key)
                            )
                            for key in (
                                "pidn",
                                "signal_key",
                                "active_inference_id",
                                "validation_status",
                                "adjusted_significance",
                                "validation_reasoning",
                                "evidence_data",
                                "confidence",
                                "municipality",
                            )
                        }
                        for row in evidence_rows
                    ],
                }
            )
            input_hash = inference_input_hash(
                source_hash,
                requested_model=config.model_path,
                prompt_version=PROMPT_VERSION,
            )
            existing = database.execute(
                """
                SELECT ip.input_hash
                FROM meta.intelligence_passes ip
                JOIN public.owner_briefs ob
                  ON ob.canonical_name = %(canonical_name)s
                WHERE ip.pidn = %(key)s
                  AND ip.pass_number = 3
                  AND ip.status = 'complete'
                """,
                {"key": subject_key, "canonical_name": canonical_name},
            )
            prior_hash = None
            if existing:
                row0 = existing[0]
                prior_hash = (
                    row0.get("input_hash") if isinstance(row0, dict) else row0[0]
                )
            if prior_hash == input_hash:
                skipped_unchanged += 1
                continue

            if not item_budget.claim(log, label="changed owner briefs"):
                break

            result = invoke_with_retry(
                config,
                prompt,
                archive_key=f"owner-{owner_id}",
                retries=1,
            )
            if not result.success:
                _update_owner_pass_status(
                    database, subject_key, "error", input_hash, result.error
                )
                log.warning(f"owner {owner_id}: LLM failed — {result.error}")
                errors += 1
                continue

            parsed = parse_owner_brief_output(result.parsed or {})
            if "error" in parsed:
                _update_owner_pass_status(
                    database, subject_key, "error", input_hash, parsed["error"]
                )
                log.warning(f"owner {owner_id}: parse error — {parsed['error']}")
                errors += 1
                continue

            allowed_signal_keys = {
                row["signal_key"] for row in evidence_rows if row.get("signal_key")
            }
            allowed_pidns = {row["pidn"] for row in evidence_rows if row.get("pidn")}
            citation_errors = validate_owner_brief_citations(
                parsed,
                allowed_signal_keys,
                allowed_pidns,
            )
            if citation_errors:
                _update_owner_pass_status(
                    database,
                    subject_key,
                    "error",
                    input_hash,
                    "; ".join(citation_errors),
                )
                record_validation_rejection(
                    database,
                    subject_key=subject_key,
                    pass_number=3,
                    output_kind="owner_brief",
                    source_hash=source_hash,
                    input_hash=input_hash,
                    requested_model=config.model_path,
                    prompt_version=PROMPT_VERSION,
                    errors=citation_errors,
                )
                log.warning(
                    "owner %s: citation validation failed — %s",
                    owner_id,
                    "; ".join(citation_errors),
                )
                errors += 1
                continue

            gate = record_inference_decision(
                database,
                subject_key=subject_key,
                pass_number=3,
                output_kind="owner_brief",
                decision_key="brief",
                source_hash=source_hash,
                input_hash=input_hash,
                requested_model=config.model_path,
                served_model=result.metadata.get("served_model"),
                provider=result.metadata.get("provider"),
                prompt_version=PROMPT_VERSION,
                payload=parsed,
                semantic_decision=owner_brief_semantic_decision(parsed),
                citations=parsed["citations"],
                evidence_refs=(
                    [f"signal:{key}" for key in parsed["citations"]]
                    + [f"parcel:{pidn}" for pidn in parsed["parcel_citations"]]
                    + signal_dependencies
                    + ["owner-context:v2:" + content_hash(owner_context)]
                ),
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
                _update_owner_pass_status(
                    database,
                    subject_key,
                    "error",
                    input_hash,
                    f"quarantined contradiction {gate.contradiction_id}: {gate.reason}",
                )
                log.warning(
                    "owner %s: quarantined as contradiction %s — %s",
                    owner_id,
                    gate.contradiction_id,
                    gate.reason,
                )
                errors += 1
                continue

            now = datetime.now(UTC).isoformat()
            pass_metadata = {
                "model": config.model_path,
                "pass": "3b-owner-rollup",
                "temperature": config.temperature,
                "thinking": config.thinking,
            }

            database.execute(
                UPSERT_OWNER_BRIEF,
                {
                    "canonical_name": canonical_name,
                    "owner_id": owner_id,
                    "brief_text": parsed["brief_text"],
                    "portfolio_strategy": parsed["portfolio_strategy"],
                    "concentration_notes": parsed["concentration_notes"],
                    "key_pattern": parsed["key_pattern"],
                    "recommendation": parsed["recommendation"],
                    "urgency": parsed["urgency"],
                    "top_risk": parsed["top_risk"],
                    "evidence_strength": parsed["evidence_strength"],
                    "citations": json.dumps(parsed["citations"]),
                    "parcel_citations": json.dumps(parsed["parcel_citations"]),
                    "n_parcels": len({r["pidn"] for r in evidence_rows}),
                    "model_version": config.model_path,
                    "prompt_version": PROMPT_VERSION,
                    # A single unvoted sample has no agreement measurement;
                    # writing 1.0 here would read as "3/3 unanimous" in any UI.
                    "n_trials": 1,
                    "trial_agreement": None,
                    "confidence": parsed["confidence"],
                    "pass_metadata": json.dumps(pass_metadata),
                    "generated_at": now,
                    "active_inference_id": gate.inference_id,
                },
            )
            _update_owner_pass_status(database, subject_key, "complete", input_hash)
            briefs_created += 1
            if i % 25 == 0:
                log.info(
                    f"  progress: {i}/{len(owners_needing)} owners, {briefs_created} briefs"
                )

        except PassSpendLimitExceeded as exc:
            spend_limit_reached = True
            log.info(
                "Pass 3b dollar ceiling reached; remaining owner briefs are deferred: %s",
                exc,
            )
            break
        except Exception as exc:
            _update_owner_pass_status(
                database, subject_key, "error", input_hash or "", str(exc)
            )
            log.warning(f"owner {owner_id}: exception — {exc}")
            errors += 1
            continue

    check_error_budget(
        log,
        label="pass3b_owner_briefs",
        errors=errors,
        total=briefs_created + errors,
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "skipped_unchanged": MetadataValue.int(skipped_unchanged),
            "owners_eligible": MetadataValue.int(len(owners_needing)),
            "briefs_created": MetadataValue.int(briefs_created),
            "budget_mode": MetadataValue.text(item_budget.mode),
            "item_limit": (
                MetadataValue.int(item_budget.limit)
                if item_budget.limit is not None
                else MetadataValue.text("cost-only")
            ),
            "items_claimed": MetadataValue.int(item_budget.claimed),
            "spend_limit_reached": MetadataValue.bool(spend_limit_reached),
            "errors": MetadataValue.int(errors),
            "model": MetadataValue.text(config.model_path),
            "prompt_version": MetadataValue.text(PROMPT_VERSION),
        }
    )


def _update_owner_pass_status(
    database: DatabaseResource,
    subject_key: str,
    status: str,
    input_hash: str,
    error_message: str | None = None,
) -> None:
    database.execute(
        """
        INSERT INTO meta.intelligence_passes
            (pidn, pass_number, status, last_run_at, input_hash, error_message)
        VALUES (%(key)s, 3, %(status)s, NOW(), %(hash)s, %(error)s)
        ON CONFLICT (pidn, pass_number)
        DO UPDATE SET
            status = EXCLUDED.status,
            last_run_at = EXCLUDED.last_run_at,
            input_hash = EXCLUDED.input_hash,
            error_message = EXCLUDED.error_message
        """,
        {
            "key": subject_key,
            "status": status,
            "hash": input_hash,
            "error": error_message,
        },
    )
