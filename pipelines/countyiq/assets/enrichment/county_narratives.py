"""Generate county-level narratives from cross-parcel signal patterns."""

import hashlib
import json
import re
from datetime import datetime, timezone

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.intelligence_common import compute_input_hash
from countyiq.lib.pass_llm_config import PassHarnessUnavailable, resolve_pass_harness
from countyiq.lib.pass4_county_narratives import (
    CORRIDOR_SCAN_QUERY,
    DISTRESS_SCAN_QUERY,
    MUNICIPAL_SCAN_QUERY,
    PORTFOLIO_SCAN_QUERY,
    build_corridor_prompt,
    build_distress_prompt,
    build_municipal_prompt,
    build_portfolio_prompt,
    parse_narrative_output,
)
from countyiq.resources.database import DatabaseResource

PASS_NUMBER = 4
PASS_VERSION = "4.1"

UPSERT_NARRATIVE_QUERY = """
    INSERT INTO public.county_narratives
        (narrative_key, title, body, narrative_type, trajectory,
         affected_pidns, key_entities, citations, generated_at, expires_at)
    VALUES
        (%(narrative_key)s, %(title)s, %(body)s, %(narrative_type)s, %(trajectory)s,
         %(affected_pidns)s, %(key_entities)s, %(citations)s::jsonb,
         %(generated_at)s, NOW() + INTERVAL '14 days')
    ON CONFLICT (narrative_key)
    DO UPDATE SET
        title = EXCLUDED.title,
        body = EXCLUDED.body,
        narrative_type = EXCLUDED.narrative_type,
        trajectory = EXCLUDED.trajectory,
        affected_pidns = EXCLUDED.affected_pidns,
        key_entities = EXCLUDED.key_entities,
        citations = EXCLUDED.citations,
        generated_at = EXCLUDED.generated_at,
        expires_at = EXCLUDED.expires_at
"""

CLEANUP_EXPIRED_QUERY = """
    DELETE FROM public.county_narratives
    WHERE expires_at < NOW()
"""

TOUCH_NARRATIVE_QUERY = """
    UPDATE public.county_narratives
    SET expires_at = NOW() + INTERVAL '14 days'
    WHERE narrative_key = %(narrative_key)s
"""

DELETE_STALE_NARRATIVES_QUERY = """
    DELETE FROM public.county_narratives
    WHERE narrative_type = %(narrative_type)s
      AND NOT (narrative_key = ANY(%(keep_keys)s::text[]))
"""

BRIEFS_FOR_PIDNS_QUERY = """
    SELECT
        pb.pidn,
        p.propadr AS address,
        pb.assessment,
        LEFT(pb.brief_text, 300) AS brief_excerpt
    FROM public.parcel_briefs pb
    JOIN staging.parcels p ON p.pidn = pb.pidn AND p.valid_to IS NULL
    WHERE pb.pidn = ANY(%(pidns)s)
"""

PROCEEDINGS_FOR_PIDNS_QUERY = """
    SELECT
        pe.extraction_type AS type,
        pe.applicant_name AS applicant,
        pe.decision,
        pp.meeting_date,
        pp.body_name AS body
    FROM staging.proceeding_extractions pe
    JOIN staging.public_proceedings pp ON pp.id = pe.proceeding_id
    WHERE pp.valid_to IS NULL
      AND pe.extraction_type NOT IN ('_complete', '_no_extractions')
      AND (
          pe.parcel_reference = ANY(%(pidns)s)
          OR pe.parcel_reference IN (
              SELECT propadr FROM staging.parcels
              WHERE pidn = ANY(%(pidns)s) AND valid_to IS NULL AND propadr IS NOT NULL
          )
      )
    ORDER BY pp.meeting_date DESC
    LIMIT 20
"""

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

ZHB_DECISIONS_QUERY = """
    SELECT
        pe.decision,
        COUNT(*) AS cnt
    FROM staging.proceeding_extractions pe
    JOIN staging.public_proceedings pp ON pp.id = pe.proceeding_id
    WHERE pp.valid_to IS NULL
      AND pe.extraction_type NOT IN ('_complete', '_no_extractions')
      AND pe.extraction_type ILIKE '%%zoning%%'
      AND EXISTS (
          SELECT 1 FROM staging.parcels p
          WHERE p.valid_to IS NULL
            AND p.municipality = %(municipality)s
            AND (
                p.pidn = pe.parcel_reference
                OR (p.propadr IS NOT NULL AND p.propadr = pe.parcel_reference)
            )
      )
    GROUP BY pe.decision
"""


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

    try:
        config, invoke_with_retry = resolve_pass_harness(
            log,
            pass_number=PASS_NUMBER,
            archive_label="pass4_narratives",
            default_max_tokens=2048,
        )
    except PassHarnessUnavailable as exc:
        return _skipped_result(exc.reason)

    database.execute(CLEANUP_EXPIRED_QUERY)
    log.info("Cleaned up expired narratives")

    counts = {
        "corridor_generated": 0,
        "corridor_skipped": 0,
        "portfolio_generated": 0,
        "portfolio_skipped": 0,
        "municipal_generated": 0,
        "municipal_skipped": 0,
        "distress_generated": 0,
        "distress_skipped": 0,
        "errors": 0,
    }

    corridor_generated, corridor_skipped, corridor_errors = _run_corridor_scan(
        database, log, config, invoke_with_retry
    )
    counts["corridor_generated"] = corridor_generated
    counts["corridor_skipped"] = corridor_skipped
    counts["errors"] += corridor_errors

    portfolio_generated, portfolio_skipped, portfolio_errors = _run_portfolio_scan(
        database, log, config, invoke_with_retry
    )
    counts["portfolio_generated"] = portfolio_generated
    counts["portfolio_skipped"] = portfolio_skipped
    counts["errors"] += portfolio_errors

    municipal_generated, municipal_skipped, municipal_errors = _run_municipal_scan(
        database, log, config, invoke_with_retry
    )
    counts["municipal_generated"] = municipal_generated
    counts["municipal_skipped"] = municipal_skipped
    counts["errors"] += municipal_errors

    distress_generated, distress_skipped, distress_errors = _run_distress_scan(
        database, log, config, invoke_with_retry
    )
    counts["distress_generated"] = distress_generated
    counts["distress_skipped"] = distress_skipped
    counts["errors"] += distress_errors

    total_generated = (
        counts["corridor_generated"]
        + counts["portfolio_generated"]
        + counts["municipal_generated"]
        + counts["distress_generated"]
    )
    total_skipped = (
        counts["corridor_skipped"]
        + counts["portfolio_skipped"]
        + counts["municipal_skipped"]
        + counts["distress_skipped"]
    )

    log.info(
        "Pass 4 complete: %d generated, %d unchanged, %d errors",
        total_generated,
        total_skipped,
        counts["errors"],
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "model": MetadataValue.text(config.model_path),
            "thinking": MetadataValue.bool(config.thinking),
            "corridor_narratives": MetadataValue.int(counts["corridor_generated"]),
            "corridor_skipped": MetadataValue.int(counts["corridor_skipped"]),
            "portfolio_narratives": MetadataValue.int(counts["portfolio_generated"]),
            "portfolio_skipped": MetadataValue.int(counts["portfolio_skipped"]),
            "municipal_narratives": MetadataValue.int(counts["municipal_generated"]),
            "municipal_skipped": MetadataValue.int(counts["municipal_skipped"]),
            "distress_narratives": MetadataValue.int(counts["distress_generated"]),
            "distress_skipped": MetadataValue.int(counts["distress_skipped"]),
            "total_narratives": MetadataValue.int(total_generated),
            "total_skipped": MetadataValue.int(total_skipped),
            "errors": MetadataValue.int(counts["errors"]),
        }
    )


def _run_corridor_scan(database, log, config, invoke_with_retry):
    generated = 0
    skipped = 0
    errors = 0
    seen_keys: list[str] = []

    log.info("Running corridor activity scan")
    try:
        rows = database.execute(CORRIDOR_SCAN_QUERY) or []
        log.info("Found %d corridor clusters", len(rows))

        for row in rows:
            signal_key = ""
            try:
                if isinstance(row, (tuple, list)):
                    signal_key = row[0]
                    municipality = row[1]
                    cluster_pidns = row[2]
                    cluster_size = row[3]
                else:
                    signal_key = row.get("signal_key")
                    municipality = row.get("municipality")
                    cluster_pidns = row.get("cluster_pidns")
                    cluster_size = row.get("cluster_size")

                briefs_rows = database.execute(
                    BRIEFS_FOR_PIDNS_QUERY,
                    {"pidns": cluster_pidns or []},
                ) or []
                parcels = _rows_to_dicts(briefs_rows, ["pidn", "address", "assessment", "brief_excerpt"])

                proc_rows = database.execute(
                    PROCEEDINGS_FOR_PIDNS_QUERY,
                    {"pidns": cluster_pidns or []},
                ) or []
                proceedings = _rows_to_dicts(proc_rows, ["type", "applicant", "decision", "meeting_date", "body"])

                narrative_data = {
                    "signal_key": signal_key,
                    "municipality": municipality,
                    "cluster_size": cluster_size,
                    "cluster_pidns": cluster_pidns or [],
                    "parcels": parcels,
                    "proceedings": proceedings,
                }
                narrative_key = _build_narrative_key(
                    "corridor",
                    municipality,
                    signal_key,
                    ",".join(sorted(cluster_pidns or [])),
                )
                seen_keys.append(narrative_key)

                status = _generate_or_refresh_narrative(
                    database=database,
                    log=log,
                    config=config,
                    invoke_with_retry=invoke_with_retry,
                    narrative_key=narrative_key,
                    narrative_type="corridor",
                    prompt=build_corridor_prompt(narrative_data),
                    narrative_data=narrative_data,
                    archive_key=_narrative_archive_key(
                        "corridor",
                        municipality,
                        signal_key,
                        cluster_size,
                    ),
                )
                if status == "generated":
                    generated += 1
                elif status == "skipped":
                    skipped += 1
                else:
                    errors += 1

            except Exception as exc:
                log.warning("Error in corridor scan for %s: %s", signal_key, exc)
                errors += 1

    except Exception as exc:
        log.warning("Corridor scan query failed: %s", exc)
        return 0, 0, errors + 1

    _delete_stale_narratives(database, "corridor", seen_keys)
    return generated, skipped, errors


def _run_portfolio_scan(database, log, config, invoke_with_retry):
    generated = 0
    skipped = 0
    errors = 0
    seen_keys: list[str] = []

    log.info("Running owner portfolio scan")
    try:
        rows = database.execute(PORTFOLIO_SCAN_QUERY) or []
        log.info("Found %d portfolio entities", len(rows))

        for row in rows:
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

                entity_name = canonical_name or ""
                names = [canonical_name] if canonical_name else []

                briefs_rows = database.execute(
                    BRIEFS_FOR_PIDNS_QUERY,
                    {"pidns": pidns or []},
                ) or []
                briefs = _rows_to_dicts(briefs_rows, ["pidn", "address", "assessment", "brief_excerpt"])

                deeds = []
                if names:
                    try:
                        deed_rows = database.execute(DEEDS_FOR_ENTITY_QUERY, {"names": names}) or []
                        deeds = _rows_to_dicts(deed_rows, ["pidn", "grantor", "grantee", "date", "price"])
                    except Exception:
                        deeds = []

                narrative_data = {
                    "entity_id": entity_id,
                    "canonical_name": canonical_name,
                    "entity_type": entity_type,
                    "briefed_parcels": briefed_parcels,
                    "municipalities": municipalities or [],
                    "total_acres": total_acres or 0,
                    "pidns": pidns or [],
                    "briefs": briefs,
                    "deeds": deeds,
                }
                narrative_key = _build_narrative_key(
                    "owner_portfolio",
                    entity_id if entity_id is not None else canonical_name,
                )
                seen_keys.append(narrative_key)

                status = _generate_or_refresh_narrative(
                    database=database,
                    log=log,
                    config=config,
                    invoke_with_retry=invoke_with_retry,
                    narrative_key=narrative_key,
                    narrative_type="owner_portfolio",
                    prompt=build_portfolio_prompt(narrative_data),
                    narrative_data=narrative_data,
                    archive_key=_narrative_archive_key(
                        "portfolio",
                        entity_id if entity_id is not None else canonical_name,
                    ),
                )
                if status == "generated":
                    generated += 1
                elif status == "skipped":
                    skipped += 1
                else:
                    errors += 1

            except Exception as exc:
                log.warning("Error in portfolio scan for %s: %s", entity_name, exc)
                errors += 1

    except Exception as exc:
        log.warning("Portfolio scan query failed: %s", exc)
        return 0, 0, errors + 1

    _delete_stale_narratives(database, "owner_portfolio", seen_keys)
    return generated, skipped, errors


def _run_municipal_scan(database, log, config, invoke_with_retry):
    generated = 0
    skipped = 0
    errors = 0
    seen_keys: list[str] = []

    log.info("Running municipal trends scan")
    try:
        rows = database.execute(MUNICIPAL_SCAN_QUERY) or []
        log.info("Found %d municipalities with briefs", len(rows))

        for row in rows:
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

                zhb_decisions = {}
                try:
                    zhb_rows = database.execute(ZHB_DECISIONS_QUERY, {"municipality": municipality}) or []
                    for zhb_row in zhb_rows:
                        if isinstance(zhb_row, (tuple, list)):
                            zhb_decisions[zhb_row[0] or "unknown"] = zhb_row[1] or 0
                        else:
                            zhb_decisions[zhb_row.get("decision", "unknown")] = zhb_row.get("cnt", 0)
                except Exception:
                    zhb_decisions = {}

                narrative_data = {
                    "municipality": municipality,
                    "assessment_distribution": assessment_distribution,
                    "signal_distribution": signal_distribution,
                    "zhb_decisions": zhb_decisions,
                    "distress_summary": distress_summary,
                }
                narrative_key = _build_narrative_key("municipality", municipality)
                seen_keys.append(narrative_key)

                status = _generate_or_refresh_narrative(
                    database=database,
                    log=log,
                    config=config,
                    invoke_with_retry=invoke_with_retry,
                    narrative_key=narrative_key,
                    narrative_type="municipality",
                    prompt=build_municipal_prompt(narrative_data),
                    narrative_data=narrative_data,
                    archive_key=_narrative_archive_key("municipality", municipality),
                )
                if status == "generated":
                    generated += 1
                elif status == "skipped":
                    skipped += 1
                else:
                    errors += 1

            except Exception as exc:
                log.warning("Error in municipal scan for %s: %s", municipality, exc)
                errors += 1

    except Exception as exc:
        log.warning("Municipal scan query failed: %s", exc)
        return 0, 0, errors + 1

    _delete_stale_narratives(database, "municipality", seen_keys)
    return generated, skipped, errors


def _run_distress_scan(database, log, config, invoke_with_retry):
    generated = 0
    skipped = 0
    errors = 0
    seen_keys: list[str] = []

    log.info("Running distress migration scan")
    try:
        rows = database.execute(DISTRESS_SCAN_QUERY) or []
        log.info("Found %d municipalities with significant distress changes", len(rows))

        for row in rows:
            municipality = ""
            school_dis = ""
            try:
                if isinstance(row, (tuple, list)):
                    narrative_data = {
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
                    narrative_data = {
                        "municipality": row.get("municipality", ""),
                        "school_dis": row.get("school_dis", ""),
                        "current_count": row.get("current_count", 0) or 0,
                        "prior_count": row.get("prior_count", 0) or 0,
                        "current_total_owed": row.get("current_total_owed", 0) or 0,
                        "prior_total_owed": row.get("prior_total_owed", 0) or 0,
                        "count_delta": row.get("count_delta", 0) or 0,
                        "total_delta": row.get("total_delta", 0) or 0,
                    }

                municipality = narrative_data["municipality"]
                school_dis = narrative_data["school_dis"]
                narrative_key = _build_narrative_key("market_segment", municipality, school_dis)
                seen_keys.append(narrative_key)

                status = _generate_or_refresh_narrative(
                    database=database,
                    log=log,
                    config=config,
                    invoke_with_retry=invoke_with_retry,
                    narrative_key=narrative_key,
                    narrative_type="market_segment",
                    prompt=build_distress_prompt(narrative_data),
                    narrative_data=narrative_data,
                    archive_key=_narrative_archive_key("distress", municipality, school_dis),
                )
                if status == "generated":
                    generated += 1
                elif status == "skipped":
                    skipped += 1
                else:
                    errors += 1

            except Exception as exc:
                log.warning("Error in distress scan for %s / %s: %s", municipality, school_dis, exc)
                errors += 1

    except Exception as exc:
        log.warning("Distress scan query failed: %s", exc)
        return 0, 0, errors + 1

    _delete_stale_narratives(database, "market_segment", seen_keys)
    return generated, skipped, errors


def _generate_or_refresh_narrative(
    *,
    database: DatabaseResource,
    log,
    config,
    invoke_with_retry,
    narrative_key: str,
    narrative_type: str,
    prompt: str,
    narrative_data: dict,
    archive_key: str,
) -> str:
    input_hash = compute_input_hash(
        {
            "pass_version": PASS_VERSION,
            "narrative_type": narrative_type,
            "data": narrative_data,
        }
    )

    prior_hash = _get_prior_hash(database, narrative_key)
    if prior_hash == input_hash:
        _touch_narrative(database, narrative_key)
        _update_pass_status(database, narrative_key, "complete", input_hash)
        return "skipped"

    result = invoke_with_retry(
        config,
        prompt,
        retries=1,
        archive_key=archive_key,
    )
    if not result.success:
        log.warning("LLM failed for %s: %s", narrative_key, result.error)
        _update_pass_status(database, narrative_key, "error", input_hash, result.error)
        return "error"

    parsed = parse_narrative_output(result.parsed or {})
    if "error" in parsed:
        log.warning("Invalid narrative output for %s: %s", narrative_key, parsed["error"])
        _update_pass_status(database, narrative_key, "error", input_hash, parsed["error"])
        return "error"

    parsed["narrative_type"] = narrative_type
    _upsert_narrative(database, narrative_key, parsed)
    _update_pass_status(database, narrative_key, "complete", input_hash)
    return "generated"


def _rows_to_dicts(rows: list, keys: list[str]) -> list[dict]:
    result = []
    for row in rows:
        if isinstance(row, dict):
            result.append(row)
        elif isinstance(row, (tuple, list)):
            result.append({key: row[i] if i < len(row) else None for i, key in enumerate(keys)})
        else:
            result.append(row)
    return result


def _normalize_key_part(part: object) -> str:
    text = str(part or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:48] or "blank"


def _build_narrative_key(kind: str, *parts: object) -> str:
    normalized = [_normalize_key_part(part) for part in parts if part not in (None, "", [], ())]
    digest_source = "|".join([kind, *normalized]).encode("utf-8")
    digest = hashlib.sha256(digest_source).hexdigest()[:16]
    prefix = ":".join([kind, *normalized[:2]])
    return f"{prefix}:{digest}" if prefix else f"{kind}:{digest}"


def _narrative_archive_key(kind: str, *parts) -> str:
    cleaned_parts = [str(part).strip() for part in parts if part not in (None, "")]
    return ":".join([kind, *cleaned_parts]) if cleaned_parts else kind


def _get_prior_hash(database: DatabaseResource, narrative_key: str) -> str | None:
    rows = database.execute(
        """
        SELECT input_hash
        FROM meta.intelligence_passes
        WHERE pidn = %(pidn)s
          AND pass_number = %(pass_number)s
          AND status = 'complete'
        """,
        {"pidn": narrative_key, "pass_number": PASS_NUMBER},
    ) or []
    if not rows:
        return None
    row = rows[0]
    if isinstance(row, dict):
        return row.get("input_hash")
    return row[0] if row else None


def _touch_narrative(database: DatabaseResource, narrative_key: str) -> None:
    database.execute(TOUCH_NARRATIVE_QUERY, {"narrative_key": narrative_key})


def _delete_stale_narratives(
    database: DatabaseResource,
    narrative_type: str,
    keep_keys: list[str],
) -> None:
    database.execute(
        DELETE_STALE_NARRATIVES_QUERY,
        {
            "narrative_type": narrative_type,
            "keep_keys": keep_keys,
        },
    )


def _upsert_narrative(
    database: DatabaseResource,
    narrative_key: str,
    parsed: dict,
) -> None:
    database.execute(
        UPSERT_NARRATIVE_QUERY,
        {
            "narrative_key": narrative_key,
            "title": parsed["title"],
            "body": parsed["narrative"],
            "narrative_type": parsed["narrative_type"],
            "trajectory": parsed["trajectory"],
            "affected_pidns": parsed.get("affected_pidns", []),
            "key_entities": parsed.get("key_entities", []),
            "citations": json.dumps(parsed.get("citations", [])),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _update_pass_status(
    database: DatabaseResource,
    narrative_key: str,
    status: str,
    input_hash: str,
    error_message: str | None = None,
) -> None:
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
            "pidn": narrative_key,
            "pass_number": PASS_NUMBER,
            "status": status,
            "input_hash": input_hash,
            "error_message": error_message,
        },
    )


def _skipped_result(reason: str) -> MaterializeResult:
    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("skipped"),
            "reason": MetadataValue.text(reason),
            "corridor_narratives": MetadataValue.int(0),
            "corridor_skipped": MetadataValue.int(0),
            "portfolio_narratives": MetadataValue.int(0),
            "portfolio_skipped": MetadataValue.int(0),
            "municipal_narratives": MetadataValue.int(0),
            "municipal_skipped": MetadataValue.int(0),
            "distress_narratives": MetadataValue.int(0),
            "distress_skipped": MetadataValue.int(0),
            "total_narratives": MetadataValue.int(0),
            "total_skipped": MetadataValue.int(0),
            "errors": MetadataValue.int(0),
        }
    )
