"""Pass 3b — owner-rollup briefs (portfolio-level intelligence).

For every resolved owner in ``public.owners`` with ≥3 parcels carrying
medium-or-high-significance Pass 2 evidence, generate a single
portfolio-level brief via ``public.owner_briefs``. Experiment E showed
these score 4.75 vs 1.00 on portfolio-pattern insight compared to
reading N parcel briefs independently.
"""

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.error_budget import check_error_budget
from countyiq.lib.pass_llm_config import (
    PassItemBudget,
    PassHarnessUnavailable,
    resolve_pass_harness,
)
from countyiq.lib.pass_schemas import PASS3B_OWNER_BRIEF_SCHEMA
from countyiq.lib.pass3_owner_briefs import (
    OWNER_PORTFOLIO_QUERY,
    OWNER_ROLLUP_SYSTEM_PROMPT,
    OWNERS_NEEDING_BRIEFS_QUERY,
    PORTFOLIO_EVIDENCE_QUERY,
    PROMPT_VERSION,
    UPSERT_OWNER_BRIEF,
    build_owner_rollup_prompt,
    parse_owner_brief_output,
)
from countyiq.resources.database import DatabaseResource


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
        return MaterializeResult(metadata={
            "status": MetadataValue.text(f"skipped ({exc.reason})"),
            "briefs_created": MetadataValue.int(0),
        })
    item_budget = PassItemBudget(3)
    # Keep Pass 3 temperature low — narratives should be consistent with
    # the committed structured fields, per experiment C.
    config = replace(config, temperature=min(config.temperature, 0.3))

    owner_rows = database.execute(OWNERS_NEEDING_BRIEFS_QUERY)
    owners_needing = [
        (r["owner_id"], r["canonical_name"]) if isinstance(r, dict) else (r[0], r[1])
        for r in (owner_rows or [])
    ]
    if not owners_needing:
        log.info("No owners eligible for rollup briefs.")
        return MaterializeResult(metadata={
            "status": MetadataValue.text("complete"),
            "owners_eligible": MetadataValue.int(0),
            "briefs_created":  MetadataValue.int(0),
        })

    log.info(f"{len(owners_needing)} owners eligible for rollup briefs")
    briefs_created = 0
    skipped_unchanged = 0
    errors = 0

    for i, (owner_id, canonical_name) in enumerate(owners_needing, 1):
        try:
            with database.dict_cursor() as cur:
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

            prompt = build_owner_rollup_prompt(owner, evidence_rows)

            # Skip unchanged work. Pass 2 rewrites validated_at on every upsert,
            # so the eligibility query re-selects owners whose briefs would come
            # out byte-identical. Hashing the RENDERED prompt (+ model + prompt
            # version) skips those without a false-invalidation from volatile
            # timestamp fields — and re-runs when the template itself changes.
            subject_key = "owner_brief:" + hashlib.sha256(
                canonical_name.encode("utf-8")
            ).hexdigest()[:20]
            input_hash = hashlib.sha256(
                f"{config.model_path}\x1f{PROMPT_VERSION}\x1f{prompt}".encode("utf-8")
            ).hexdigest()
            existing = database.execute(
                """
                SELECT input_hash FROM meta.intelligence_passes
                WHERE pidn = %(key)s AND pass_number = 3 AND status = 'complete'
                """,
                {"key": subject_key},
            )
            prior_hash = None
            if existing:
                row0 = existing[0]
                prior_hash = row0.get("input_hash") if isinstance(row0, dict) else row0[0]
            if prior_hash == input_hash:
                skipped_unchanged += 1
                continue

            if not item_budget.claim(log, label="changed owner briefs"):
                break

            result = invoke_with_retry(
                config, prompt, archive_key=f"owner-{owner_id}", retries=1,
            )
            if not result.success:
                log.warning(f"owner {owner_id}: LLM failed — {result.error}")
                errors += 1
                continue

            parsed = parse_owner_brief_output(result.parsed or {})
            if "error" in parsed:
                log.warning(f"owner {owner_id}: parse error — {parsed['error']}")
                errors += 1
                continue

            now = datetime.now(timezone.utc).isoformat()
            pass_metadata = {
                "model":       config.model_path,
                "pass":        "3b-owner-rollup",
                "temperature": config.temperature,
                "thinking":    config.thinking,
            }

            database.execute(
                UPSERT_OWNER_BRIEF,
                {
                    "canonical_name":       canonical_name,
                    "owner_id":             owner_id,
                    "brief_text":           parsed["brief_text"],
                    "portfolio_strategy":   parsed["portfolio_strategy"],
                    "concentration_notes":  parsed["concentration_notes"],
                    "key_pattern":          parsed["key_pattern"],
                    "recommendation":       parsed["recommendation"],
                    "urgency":              parsed["urgency"],
                    "top_risk":             parsed["top_risk"],
                    "evidence_strength":    parsed["evidence_strength"],
                    "citations":            json.dumps(parsed["citations"]),
                    "parcel_citations":     json.dumps(parsed["parcel_citations"]),
                    "n_parcels":            len(set(r["pidn"] for r in evidence_rows)),
                    "model_version":        config.model_path,
                    "prompt_version":       PROMPT_VERSION,
                    # A single unvoted sample has no agreement measurement;
                    # writing 1.0 here would read as "3/3 unanimous" in any UI.
                    "n_trials":             1,
                    "trial_agreement":      None,
                    "confidence":           parsed["confidence"],
                    "pass_metadata":        json.dumps(pass_metadata),
                    "generated_at":         now,
                },
            )
            database.execute(
                """
                INSERT INTO meta.intelligence_passes
                    (pidn, pass_number, status, last_run_at, input_hash)
                VALUES (%(key)s, 3, 'complete', NOW(), %(hash)s)
                ON CONFLICT (pidn, pass_number)
                DO UPDATE SET
                    status = 'complete',
                    last_run_at = NOW(),
                    input_hash = EXCLUDED.input_hash,
                    error_message = NULL
                """,
                {"key": subject_key, "hash": input_hash},
            )
            briefs_created += 1
            if i % 25 == 0:
                log.info(f"  progress: {i}/{len(owners_needing)} owners, {briefs_created} briefs")

        except Exception as exc:
            log.warning(f"owner {owner_id}: exception — {exc}")
            errors += 1
            continue

    check_error_budget(
        log, label="pass3b_owner_briefs",
        errors=errors, total=briefs_created + errors,
    )

    return MaterializeResult(metadata={
        "status":           MetadataValue.text("complete"),
        "skipped_unchanged": MetadataValue.int(skipped_unchanged),
        "owners_eligible":  MetadataValue.int(len(owners_needing)),
        "briefs_created":   MetadataValue.int(briefs_created),
        "item_limit":       MetadataValue.int(item_budget.limit),
        "items_claimed":    MetadataValue.int(item_budget.claimed),
        "errors":           MetadataValue.int(errors),
        "model":            MetadataValue.text(config.model_path),
        "prompt_version":   MetadataValue.text(PROMPT_VERSION),
    })
