"""Explicit-scope draft generation; publication is a separate recorded review."""

from dagster import AssetExecutionContext, Field, MaterializeResult, asset

from countyiq.lib.emerging_intelligence import (
    ANALYSIS_SCHEMA,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    generate_analysis,
)
from countyiq.lib.emerging_packets import build_packet, fetch_scope
from countyiq.lib.emerging_store import retain_analysis
from countyiq.lib.intelligence_integrity import content_hash
from countyiq.lib.pass_llm_config import PassItemBudget, resolve_pass_harness
from countyiq.lib.pass_subscription import (
    start_subscription_item,
    subscription_provenance,
)
from countyiq.resources.database import DatabaseResource


@asset(
    group_name="emerging_intelligence",
    kinds={"postgres", "llm"},
    config_schema={
        "bundle_keys": Field(
            [str],
            default_value=[],
            description="Explicit candidate scope keys; at most ten per manual run.",
        ),
    },
)
def emerging_intelligence_drafts(
    context: AssetExecutionContext, database: DatabaseResource
) -> MaterializeResult:
    keys = list(dict.fromkeys(context.op_config["bundle_keys"]))
    if not keys:
        return MaterializeResult(
            metadata={
                "status": "skipped",
                "reason": "No explicit evidence scopes selected",
            }
        )
    if len(keys) > 10:
        raise ValueError("Select at most ten emerging-intelligence scopes per run")
    packets = []
    unchanged = 0
    with database.read_snapshot() as cur:
        for key in keys:
            packet = build_packet(fetch_scope(cur, key))
            cur.execute(
                """SELECT payload->'packet'->'source' AS source, prompt_version
                FROM meta.intelligence_inference_history
                WHERE output_kind='emerging_analysis' AND subject_key=%s AND disposition='accepted'
                ORDER BY inference_id DESC LIMIT 1""",
                (key,),
            )
            previous = cur.fetchone()
            if (
                previous
                and previous["source"] == packet["source"]
                and previous["prompt_version"] == PROMPT_VERSION
            ):
                unchanged += 1
            else:
                packets.append(packet)
    if not packets:
        return MaterializeResult(metadata={"unchanged": unchanged, "drafts": 0})
    config, invoke = resolve_pass_harness(
        context.log,
        pass_number=4,
        archive_label="emerging_intelligence",
        default_max_tokens=12000,
        json_schema=ANALYSIS_SCHEMA,
        schema_name="emerging_analysis",
        system_prompt=SYSTEM_PROMPT,
    )
    budget = PassItemBudget(4)
    drafts = 0
    quarantined = 0
    for packet in packets:
        if not budget.claim(context.log, label="emerging intelligence"):
            break
        start_subscription_item(invoke)
        analysis, _ = generate_analysis(packet, config, invoke)
        result = retain_analysis(
            database,
            packet,
            analysis,
            author=config.model_path,
            provenance=subscription_provenance(invoke),
        )
        drafts += int(result.accepted)
        quarantined += int(not result.accepted)
    return MaterializeResult(
        metadata={
            "drafts": drafts,
            "quarantined": quarantined,
            "unchanged": unchanged,
            "remaining": len(packets) - drafts - quarantined,
            "scope_hash": content_hash(keys),
            "publication": "Requires a separate source-and-claim review",
        }
    )
