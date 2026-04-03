"""Pass 4 — County Narratives Dagster Asset.

Detects cross-parcel patterns via 4 scan types (corridor activity, owner
portfolio, municipal trends, distress migration) and synthesizes narratives
using LLM prompts.  Results are inserted to public.county_narratives with a
14-day expiration.  Expired narratives are cleaned up on each run.

The asset is controlled by the COUNTYIQ_TEXT_MODEL environment variable.
If that variable is not set, the asset returns immediately with
status="skipped", allowing it to exist in the Dagster graph without
failing on machines that have no model configured.
"""

import json
import os
from datetime import datetime, timezone

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.pass4_county_narratives import (
    CORRIDOR_SCAN_QUERY,
    PORTFOLIO_SCAN_QUERY,
    MUNICIPAL_SCAN_QUERY,
    DISTRESS_SCAN_QUERY,
    build_corridor_prompt,
    build_portfolio_prompt,
    build_municipal_prompt,
    build_distress_prompt,
    parse_narrative_output,
)
from countyiq.resources.database import DatabaseResource


# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

INSERT_NARRATIVE_QUERY = """
    INSERT INTO public.county_narratives
        (title, body, narrative_type, trajectory,
         affected_pidns, key_entities, citations,
         generated_at, expires_at)
    VALUES
        (%(title)s, %(body)s, %(narrative_type)s, %(trajectory)s,
         %(affected_pidns)s, %(key_entities)s, %(citations)s::jsonb,
         %(generated_at)s, NOW() + INTERVAL '14 days')
"""

CLEANUP_EXPIRED_QUERY = """
    DELETE FROM public.county_narratives
    WHERE expires_at < NOW()
"""

# Gather briefs for a list of PIDNs
BRIEFS_FOR_PIDNS_QUERY = """
    SELECT
        pb.pidn,
        p.propadr AS address,
        pb.assessment,
        LEFT(pb.brief, 300) AS brief_excerpt
    FROM public.parcel_briefs pb
    JOIN staging.parcels p ON p.pidn = pb.pidn AND p.valid_to IS NULL
    WHERE pb.pidn = ANY(%(pidns)s)
"""

# Gather proceedings for a list of PIDNs
PROCEEDINGS_FOR_PIDNS_QUERY = """
    SELECT
        pe.extraction_type AS type,
        pe.applicant_name AS applicant,
        pe.decision,
        pp.meeting_date,
        pp.body_name AS body
    FROM staging.proceeding_extractions pe
    JOIN staging.public_proceedings pp ON pp.id = pe.proceeding_id
    WHERE pe.parcel_reference = ANY(%(pidns)s)
      AND pp.valid_to IS NULL
    ORDER BY pp.meeting_date DESC
    LIMIT 20
"""

# Gather deeds for an entity's linked names
DEEDS_FOR_ENTITY_QUERY = """
    SELECT
        rd.pidn,
        rd.grantor,
        rd.grantee,
        rd.record_date AS date,
        rd.consideration AS price
    FROM staging.recorder_documents rd
    WHERE (rd.grantor = ANY(%(names)s) OR rd.grantee = ANY(%(names)s))
      AND rd.valid_to IS NULL
      AND rd.doc_type IN ('DEED', 'DEED OF TRUST')
    ORDER BY rd.record_date DESC
    LIMIT 20
"""

# ZHB decisions per municipality
ZHB_DECISIONS_QUERY = """
    SELECT
        pe.decision,
        COUNT(*) AS cnt
    FROM staging.proceeding_extractions pe
    JOIN staging.public_proceedings pp ON pp.id = pe.proceeding_id
    JOIN staging.parcels p ON p.pidn = pe.parcel_reference AND p.valid_to IS NULL
    WHERE pp.valid_to IS NULL
      AND p.municipality = %(municipality)s
      AND pe.extraction_type ILIKE '%%zoning%%'
    GROUP BY pe.decision
"""


# ---------------------------------------------------------------------------
# Dagster Asset
# ---------------------------------------------------------------------------

@asset(
    group_name="enrichment",
    description=(
        "Pass 4: detect cross-parcel patterns via corridor, portfolio, "
        "municipal, and distress scans and synthesize county narratives"
    ),
    deps=["brief_generation"],
    kinds={"postgres", "llm"},
)
def county_narratives(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    log = context.log

    # ------------------------------------------------------------------
    # Guard: model must be configured
    # ------------------------------------------------------------------
    model_path = os.environ.get("COUNTYIQ_TEXT_MODEL")
    if not model_path:
        log.info(
            "COUNTYIQ_TEXT_MODEL is not set — skipping Pass 4 county narratives. "
            "Set this env var to the path of a GGUF text model to enable."
        )
        return _skipped_result("COUNTYIQ_TEXT_MODEL not set")

    # ------------------------------------------------------------------
    # Guard: llm_harness must be importable
    # ------------------------------------------------------------------
    try:
        from countyiq.lib.llm_harness import HarnessConfig, invoke_with_retry  # noqa: F401
    except ImportError as exc:
        log.warning("llm_harness import failed (%s) — skipping", exc)
        return _skipped_result("llm_harness import failed")

    from countyiq.lib.llm_harness import HarnessConfig, invoke_with_retry

    config = HarnessConfig(model_path=model_path, max_tokens=2048, temperature=0.3)

    # ------------------------------------------------------------------
    # Cleanup expired narratives
    # ------------------------------------------------------------------
    database.execute(CLEANUP_EXPIRED_QUERY)
    log.info("Cleaned up expired narratives")

    counts = {
        "corridor": 0,
        "portfolio": 0,
        "municipal": 0,
        "distress": 0,
        "errors": 0,
    }

    # ------------------------------------------------------------------
    # Scan A: Corridor Activity
    # ------------------------------------------------------------------
    log.info("Running corridor activity scan")
    try:
        corridor_rows = database.execute(CORRIDOR_SCAN_QUERY) or []
        log.info("Found %d corridor clusters", len(corridor_rows))

        for row in corridor_rows:
            try:
                signal_key = row[0] if isinstance(row, (tuple, list)) else row.get("signal_key")
                cluster_pidns = row[1] if isinstance(row, (tuple, list)) else row.get("cluster_pidns")
                cluster_size = row[2] if isinstance(row, (tuple, list)) else row.get("cluster_size")

                # Gather briefs and proceedings for the cluster
                briefs_rows = database.execute(BRIEFS_FOR_PIDNS_QUERY, {"pidns": cluster_pidns}) or []
                parcels = _rows_to_dicts(briefs_rows, ["pidn", "address", "assessment", "brief_excerpt"])

                proc_rows = database.execute(PROCEEDINGS_FOR_PIDNS_QUERY, {"pidns": cluster_pidns}) or []
                proceedings = _rows_to_dicts(proc_rows, ["type", "applicant", "decision", "meeting_date", "body"])

                cluster_data = {
                    "signal_key": signal_key,
                    "cluster_size": cluster_size,
                    "cluster_pidns": cluster_pidns,
                    "parcels": parcels,
                    "proceedings": proceedings,
                }

                prompt = build_corridor_prompt(cluster_data)
                result = invoke_with_retry(config, prompt, retries=1)

                if not result.success:
                    log.warning("LLM failed for corridor %s: %s", signal_key, result.error)
                    counts["errors"] += 1
                    continue

                parsed = parse_narrative_output(result.parsed or {})
                if "error" in parsed:
                    log.warning("Invalid corridor output for %s: %s", signal_key, parsed["error"])
                    counts["errors"] += 1
                    continue

                _insert_narrative(database, parsed)
                counts["corridor"] += 1
                log.info("Generated corridor narrative: %s", parsed["title"])

            except Exception as exc:
                log.warning("Error in corridor scan for %s: %s", signal_key, exc)
                counts["errors"] += 1

    except Exception as exc:
        log.warning("Corridor scan query failed: %s", exc)
        counts["errors"] += 1

    # ------------------------------------------------------------------
    # Scan B: Owner Portfolio
    # ------------------------------------------------------------------
    log.info("Running owner portfolio scan")
    try:
        portfolio_rows = database.execute(PORTFOLIO_SCAN_QUERY) or []
        log.info("Found %d portfolio entities", len(portfolio_rows))

        for row in portfolio_rows:
            entity_name = ""
            try:
                if isinstance(row, (tuple, list)):
                    entity_id, canonical_name, entity_type = row[0], row[1], row[2]
                    briefed_parcels, municipalities = row[3], row[4]
                    total_acres, pidns = row[5], row[6]
                else:
                    entity_id = row.get("entity_id")
                    canonical_name = row.get("canonical_name")
                    entity_type = row.get("entity_type")
                    briefed_parcels = row.get("briefed_parcels")
                    municipalities = row.get("municipalities")
                    total_acres = row.get("total_acres")
                    pidns = row.get("pidns")

                entity_name = canonical_name

                # Gather briefs
                briefs_rows = database.execute(BRIEFS_FOR_PIDNS_QUERY, {"pidns": pidns}) or []
                briefs = _rows_to_dicts(briefs_rows, ["pidn", "address", "assessment", "brief_excerpt"])

                # Gather deeds
                names = [canonical_name]
                deeds = []
                try:
                    deed_rows = database.execute(
                        DEEDS_FOR_ENTITY_QUERY, {"names": names}
                    ) or []
                    deeds = _rows_to_dicts(deed_rows, ["pidn", "grantor", "grantee", "date", "price"])
                except Exception:
                    pass  # recorder_documents table may not exist yet

                portfolio_data = {
                    "entity_id": entity_id,
                    "canonical_name": canonical_name,
                    "entity_type": entity_type,
                    "briefed_parcels": briefed_parcels,
                    "municipalities": municipalities or [],
                    "total_acres": total_acres or 0,
                    "pidns": pidns,
                    "briefs": briefs,
                    "deeds": deeds,
                }

                prompt = build_portfolio_prompt(portfolio_data)
                result = invoke_with_retry(config, prompt, retries=1)

                if not result.success:
                    log.warning("LLM failed for portfolio %s: %s", canonical_name, result.error)
                    counts["errors"] += 1
                    continue

                parsed = parse_narrative_output(result.parsed or {})
                if "error" in parsed:
                    log.warning("Invalid portfolio output for %s: %s", canonical_name, parsed["error"])
                    counts["errors"] += 1
                    continue

                _insert_narrative(database, parsed)
                counts["portfolio"] += 1
                log.info("Generated portfolio narrative: %s", parsed["title"])

            except Exception as exc:
                log.warning("Error in portfolio scan for %s: %s", entity_name, exc)
                counts["errors"] += 1

    except Exception as exc:
        log.warning("Portfolio scan query failed: %s", exc)
        counts["errors"] += 1

    # ------------------------------------------------------------------
    # Scan C: Municipal Trends
    # ------------------------------------------------------------------
    log.info("Running municipal trends scan")
    try:
        municipal_rows = database.execute(MUNICIPAL_SCAN_QUERY) or []
        log.info("Found %d municipalities with briefs", len(municipal_rows))

        for row in municipal_rows:
            municipality = ""
            try:
                if isinstance(row, (tuple, list)):
                    municipality = row[0]
                    assessment_distribution = {
                        "strong_opportunity": row[1] or 0,
                        "emerging": row[2] or 0,
                        "speculative": row[3] or 0,
                        "constrained": row[4] or 0,
                        "not_actionable": row[5] or 0,
                    }
                    signal_distribution = {
                        "high": row[6] or 0,
                        "medium": row[7] or 0,
                        "low": row[8] or 0,
                    }
                    distress_summary = {
                        "delinquent_parcels": row[9] or 0,
                        "total_owed": row[10] or 0,
                    }
                else:
                    municipality = row.get("municipality")
                    assessment_distribution = {
                        "strong_opportunity": row.get("strong_opportunity_count", 0) or 0,
                        "emerging": row.get("emerging_count", 0) or 0,
                        "speculative": row.get("speculative_count", 0) or 0,
                        "constrained": row.get("constrained_count", 0) or 0,
                        "not_actionable": row.get("not_actionable_count", 0) or 0,
                    }
                    signal_distribution = {
                        "high": row.get("high_signal_count", 0) or 0,
                        "medium": row.get("medium_signal_count", 0) or 0,
                        "low": row.get("low_signal_count", 0) or 0,
                    }
                    distress_summary = {
                        "delinquent_parcels": row.get("delinquent_parcels", 0) or 0,
                        "total_owed": row.get("total_owed", 0) or 0,
                    }

                # Gather ZHB decisions
                zhb_decisions = {}
                try:
                    zhb_rows = database.execute(
                        ZHB_DECISIONS_QUERY, {"municipality": municipality}
                    ) or []
                    for zr in zhb_rows:
                        if isinstance(zr, (tuple, list)):
                            zhb_decisions[zr[0] or "unknown"] = zr[1] or 0
                        else:
                            zhb_decisions[zr.get("decision", "unknown")] = zr.get("cnt", 0)
                except Exception:
                    pass  # proceeding_extractions may be empty

                municipal_data = {
                    "municipality": municipality,
                    "assessment_distribution": assessment_distribution,
                    "signal_distribution": signal_distribution,
                    "zhb_decisions": zhb_decisions,
                    "distress_summary": distress_summary,
                }

                prompt = build_municipal_prompt(municipal_data)
                result = invoke_with_retry(config, prompt, retries=1)

                if not result.success:
                    log.warning("LLM failed for municipal %s: %s", municipality, result.error)
                    counts["errors"] += 1
                    continue

                parsed = parse_narrative_output(result.parsed or {})
                if "error" in parsed:
                    log.warning("Invalid municipal output for %s: %s", municipality, parsed["error"])
                    counts["errors"] += 1
                    continue

                _insert_narrative(database, parsed)
                counts["municipal"] += 1
                log.info("Generated municipal narrative: %s", parsed["title"])

            except Exception as exc:
                log.warning("Error in municipal scan for %s: %s", municipality, exc)
                counts["errors"] += 1

    except Exception as exc:
        log.warning("Municipal scan query failed: %s", exc)
        counts["errors"] += 1

    # ------------------------------------------------------------------
    # Scan D: Distress Migration
    # ------------------------------------------------------------------
    log.info("Running distress migration scan")
    try:
        distress_rows = database.execute(DISTRESS_SCAN_QUERY) or []
        log.info("Found %d municipalities with significant distress changes", len(distress_rows))

        for row in distress_rows:
            municipality = ""
            try:
                if isinstance(row, (tuple, list)):
                    distress_data = {
                        "municipality": row[0] or "",
                        "school_dis": row[1] or "",
                        "current_count": row[2] or 0,
                        "prior_count": row[3] or 0,
                        "current_total_owed": row[4] or 0,
                        "prior_total_owed": row[5] or 0,
                        "count_delta": row[6] or 0,
                        "total_delta": row[7] or 0,
                    }
                else:
                    distress_data = {
                        "municipality": row.get("municipality", ""),
                        "school_dis": row.get("school_dis", ""),
                        "current_count": row.get("current_count", 0) or 0,
                        "prior_count": row.get("prior_count", 0) or 0,
                        "current_total_owed": row.get("current_total_owed", 0) or 0,
                        "prior_total_owed": row.get("prior_total_owed", 0) or 0,
                        "count_delta": row.get("count_delta", 0) or 0,
                        "total_delta": row.get("total_delta", 0) or 0,
                    }

                municipality = distress_data["municipality"]

                prompt = build_distress_prompt(distress_data)
                result = invoke_with_retry(config, prompt, retries=1)

                if not result.success:
                    log.warning("LLM failed for distress %s: %s", municipality, result.error)
                    counts["errors"] += 1
                    continue

                parsed = parse_narrative_output(result.parsed or {})
                if "error" in parsed:
                    log.warning("Invalid distress output for %s: %s", municipality, parsed["error"])
                    counts["errors"] += 1
                    continue

                _insert_narrative(database, parsed)
                counts["distress"] += 1
                log.info("Generated distress narrative: %s", parsed["title"])

            except Exception as exc:
                log.warning("Error in distress scan for %s: %s", municipality, exc)
                counts["errors"] += 1

    except Exception as exc:
        log.warning("Distress scan query failed: %s", exc)
        counts["errors"] += 1

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total = counts["corridor"] + counts["portfolio"] + counts["municipal"] + counts["distress"]
    log.info(
        "Pass 4 complete: %d narratives (%d corridor, %d portfolio, %d municipal, %d distress), %d errors",
        total, counts["corridor"], counts["portfolio"],
        counts["municipal"], counts["distress"], counts["errors"],
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "corridor_narratives": MetadataValue.int(counts["corridor"]),
            "portfolio_narratives": MetadataValue.int(counts["portfolio"]),
            "municipal_narratives": MetadataValue.int(counts["municipal"]),
            "distress_narratives": MetadataValue.int(counts["distress"]),
            "total_narratives": MetadataValue.int(total),
            "errors": MetadataValue.int(counts["errors"]),
        }
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rows_to_dicts(rows: list, keys: list[str]) -> list[dict]:
    """Convert tuple rows to dicts using the given key names."""
    result = []
    for row in rows:
        if isinstance(row, dict):
            result.append(row)
        elif isinstance(row, (tuple, list)):
            d = {}
            for i, key in enumerate(keys):
                d[key] = row[i] if i < len(row) else None
            result.append(d)
        else:
            result.append(row)
    return result


def _insert_narrative(database: DatabaseResource, parsed: dict) -> None:
    """Insert a parsed narrative into public.county_narratives."""
    now = datetime.now(timezone.utc).isoformat()
    database.execute(
        INSERT_NARRATIVE_QUERY,
        {
            "title": parsed["title"],
            "body": parsed["narrative"],
            "narrative_type": parsed["narrative_type"],
            "trajectory": parsed["trajectory"],
            "affected_pidns": parsed.get("affected_pidns", []),
            "key_entities": parsed.get("key_entities", []),
            "citations": json.dumps(parsed.get("citations", [])),
            "generated_at": now,
        },
    )


def _skipped_result(reason: str) -> MaterializeResult:
    """Return a MaterializeResult indicating the asset was skipped."""
    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("skipped"),
            "reason": MetadataValue.text(reason),
            "corridor_narratives": MetadataValue.int(0),
            "portfolio_narratives": MetadataValue.int(0),
            "municipal_narratives": MetadataValue.int(0),
            "distress_narratives": MetadataValue.int(0),
            "total_narratives": MetadataValue.int(0),
            "errors": MetadataValue.int(0),
        }
    )
