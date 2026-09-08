"""Explain current records once, with the ordinary Pass 3 spend and release gates."""

import os

from dagster import AssetExecutionContext, Field, MaterializeResult, Noneable, asset
from jsonschema import ValidationError

from countyiq.lib.county_config import county_open_data_source_key, get_county_config
from countyiq.lib.error_budget import check_error_budget
from countyiq.lib.intelligence_integrity import content_hash, record_inference_decision
from countyiq.lib.pass_llm_config import (
    PassHarnessUnavailable,
    PassItemBudget,
    PassSpendLimitExceeded,
    resolve_pass_harness,
)
from countyiq.lib.pass_subscription import (
    start_subscription_item,
    subscription_provenance,
)
from countyiq.lib.record_explanations import (
    EXPLANATION_SCHEMA,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    configure_explanation_harness,
    generate_explanation,
    prepare_explanation,
    validate_explanation,
)
from countyiq.resources.database import DatabaseResource

PROPERTY_CANDIDATES_QUERY = """
    WITH ranked AS (
        SELECT pidn FROM public.current_development_momentum
        WHERE eligible ORDER BY score DESC, pidn LIMIT %(rank_limit)s
    ), linked AS (
        SELECT pidn, max(evidence.meeting_date) AS latest_meeting
        FROM public.current_municipal_evidence evidence,
            LATERAL unnest(evidence.related_pidns) AS pidn
        GROUP BY pidn
        ORDER BY latest_meeting DESC, pidn LIMIT %(municipal_limit)s
    )
    SELECT pidn FROM ranked
    UNION SELECT pidn FROM linked
    ORDER BY pidn
"""


def property_candidate_limits() -> dict[str, int]:
    from countyiq.assets.enrichment.brief_generation import resolve_brief_rank_limit

    try:
        municipal_limit = max(
            1, int(os.environ.get("COUNTYIQ_PASS3_MUNICIPAL_PROPERTY_LIMIT", "1000"))
        )
    except ValueError:
        municipal_limit = 1000
    return {
        "rank_limit": resolve_brief_rank_limit(),
        "municipal_limit": municipal_limit,
    }


def explanation_identity(source: dict, config) -> str:
    return content_hash(
        {"source": source, "prompt_version": PROMPT_VERSION, "config": config.__dict__}
    )


def persist_explanation(
    database,
    source: dict,
    explanation: dict,
    config,
    *,
    attempts: int = 1,
    provenance=None,
):
    prepared, preparation_notes = prepare_explanation(explanation, source)
    validated = validate_explanation(prepared, source)
    return record_inference_decision(
        database,
        subject_key=source["subject_key"],
        pass_number=3,
        output_kind="record_explanation",
        decision_key="record_explanation",
        source_hash=content_hash(source),
        input_hash=explanation_identity(source, config),
        requested_model=config.model_path,
        prompt_version=PROMPT_VERSION,
        payload={
            "version": 1,
            "source": source,
            "explanation": validated,
            "preparation_notes": preparation_notes,
            "validation_attempts": attempts,
            **({"provenance": provenance} if provenance is not None else {}),
        },
        # Changed municipal stages or property interpretations on the same
        # evidence require review through the existing contradiction queue.
        semantic_decision=validated["record"] or validated["summary"],
        citations=validated["citations"],
        evidence_refs=[item["url"] for item in source["sources"] if item.get("url")],
        provider=provenance.get("provider") if provenance else None,
    )


def _source_bundles(
    database,
    kind: str,
    *,
    subject_keys: list[str] | None = None,
    pidns: list[str] | None = None,
):
    """Return the scope size and lazily prepared bundles, including unavailable ones."""
    county = get_county_config()
    with database.dict_cursor() as cur:
        if kind == "municipal":
            cur.execute(
                """
                SELECT explanation_source AS source
                FROM public.current_municipal_intelligence
                WHERE (%(subject_keys)s::text[] IS NULL
                    OR explanation_source->>'subject_key' = ANY(%(subject_keys)s::text[]))
                ORDER BY meeting_date DESC, proceeding_id DESC, card_position
            """,
                {"subject_keys": subject_keys or None},
            )
            sources = [row["source"] for row in cur.fetchall()]
            missing = set(subject_keys or []) - {
                source["subject_key"] for source in sources
            }
            if missing:
                raise ValueError(
                    f"Requested municipal records are not current: {sorted(missing)}"
                )
            return len(sources), sources
        if pidns is None:
            cur.execute(PROPERTY_CANDIDATES_QUERY, property_candidate_limits())
            selected_pidns = [row["pidn"] for row in cur.fetchall()]
        else:
            cur.execute(
                "SELECT pidn FROM public.properties WHERE pidn = ANY(%s::text[]) ORDER BY pidn",
                (pidns,),
            )
            selected_pidns = [row["pidn"] for row in cur.fetchall()]
            missing = set(pidns) - set(selected_pidns)
            if missing:
                raise ValueError(
                    f"Requested properties are not current: {sorted(missing)}"
                )

    # Generate expensive spatial contexts lazily, after the paid gate opens.
    def properties():
        for pidn in selected_pidns:
            with database.dict_cursor() as cur:
                cur.execute(
                    "SELECT public.property_explanation_source(%s, %s, %s, %s) AS source",
                    (
                        pidn,
                        county_open_data_source_key(county),
                        county.signal_subdivision_radius_m,
                        county.signal_environmental_radius_m,
                    ),
                )
                source = cur.fetchone()["source"]
            yield source

    return len(selected_pidns), properties()


def run_explanations(context, database, kind: str) -> MaterializeResult:
    if os.environ.get("COUNTYIQ_PASS3_MODE", "legacy").strip().lower() != "records":
        return MaterializeResult(
            metadata={
                "status": "skipped",
                "reason": "Record explanation mode is disabled",
            }
        )
    try:
        config, invoke = resolve_pass_harness(
            context.log,
            pass_number=3,
            archive_label=f"{kind}_record_explanations",
            default_max_tokens=2048,
            json_schema=EXPLANATION_SCHEMA,
            schema_name="record_explanation",
            system_prompt=SYSTEM_PROMPT,
        )
    except PassHarnessUnavailable as error:
        return MaterializeResult(metadata={"status": "skipped", "reason": error.reason})
    config = configure_explanation_harness(config, kind)
    budget = PassItemBudget(3)
    counts = {
        "accepted": 0,
        "unchanged": 0,
        "quarantined": 0,
        "errors": 0,
        "corrected": 0,
        "unavailable": 0,
    }
    with database.dict_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (subject_key)
                subject_key, input_hash, provider, prompt_version, source_hash
            FROM meta.intelligence_inference_history
            WHERE output_kind = 'record_explanation' AND disposition = 'accepted'
            ORDER BY subject_key, inference_id DESC
        """)
        previous = {row["subject_key"]: row for row in cur.fetchall()}
    subject_keys = (
        context.op_config.get("subject_keys", []) if kind == "municipal" else None
    )
    pidns = context.op_config.get("pidns") if kind == "property" else None
    eligible_in_scope, sources = _source_bundles(
        database, kind, subject_keys=subject_keys, pidns=pidns
    )
    stop_reason = "scope_exhausted"
    for source in sources:
        if source is None:
            counts["unavailable"] += 1
            continue
        prior = previous.get(source["subject_key"], {})
        subscription_current = (
            prior.get("provider") == "codex_subscription"
            and prior.get("prompt_version") == PROMPT_VERSION
            and prior.get("source_hash") == content_hash(source)
        )
        if (
            prior.get("input_hash") == explanation_identity(source, config)
            or subscription_current
        ):
            counts["unchanged"] += 1
            continue
        if not budget.claim(context.log, label="record explanations"):
            stop_reason = "item_limit"
            break
        try:
            start_subscription_item(invoke)
            explanation, attempts = generate_explanation(source, config, invoke)
            counts["corrected"] += int(attempts == 2)
            result = persist_explanation(
                database,
                source,
                explanation,
                config,
                attempts=attempts,
                provenance=subscription_provenance(invoke),
            )
            counts["accepted" if result.accepted else "quarantined"] += 1
        except PassSpendLimitExceeded as error:
            context.log.warning("Record explanation execution stopped: %s", error)
            stop_reason = getattr(error, "stop_reason", "spend_limit")
            break
        except (ValueError, ValidationError) as error:
            counts["errors"] += 1
            context.log.warning(
                "Explanation %s failed: %s", source["subject_key"], error
            )
    check_error_budget(
        context.log,
        label="Record explanations",
        errors=counts["errors"],
        total=counts["accepted"] + counts["quarantined"] + counts["errors"],
    )
    remaining = eligible_in_scope - counts["accepted"] - counts["unchanged"]
    return MaterializeResult(
        metadata={
            "status": "partial" if remaining else "complete",
            "stop_reason": stop_reason,
            "eligible_in_scope": eligible_in_scope,
            "remaining": remaining,
            **counts,
        }
    )


@asset(
    group_name="enrichment",
    deps=["municipal_evidence_linking"],
    kinds={"postgres", "llm"},
    config_schema={
        "subject_keys": Field(
            [str],
            default_value=[],
            description="Optional fixed record scope for an explanation canary.",
        ),
    },
)
def municipal_record_explanations(
    context: AssetExecutionContext, database: DatabaseResource
) -> MaterializeResult:
    return run_explanations(context, database, "municipal")


@asset(
    group_name="enrichment",
    deps=["development_momentum", "municipal_record_explanations"],
    kinds={"postgres", "llm"},
    config_schema={
        "pidns": Field(
            Noneable([str]),
            default_value=None,
            description="Optional fixed property scope; an empty list selects no properties.",
        ),
    },
)
def property_record_explanations(
    context: AssetExecutionContext, database: DatabaseResource
) -> MaterializeResult:
    return run_explanations(context, database, "property")
