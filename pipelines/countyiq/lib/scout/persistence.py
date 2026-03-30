"""Database persistence helpers for County Scout."""

from __future__ import annotations

from psycopg2.extras import Json, execute_batch

from countyiq.lib.scout.models import CandidateRecord, ObservationRecord, RegistryMonitorRecord
from countyiq.resources.database import DatabaseResource


def upsert_source_candidates(
    database: DatabaseResource,
    candidates: list[CandidateRecord],
) -> None:
    """Upsert current candidate classifications into meta.source_candidates."""
    if not candidates:
        return

    sql = """
        INSERT INTO meta.source_candidates (
            source_key,
            county_key,
            seed_slug,
            source_name,
            source_url,
            normalized_url,
            parent_url,
            discovery_method,
            source_type,
            platform,
            extraction_method,
            categories,
            audiences,
            value_score,
            risk_level,
            risk_memo,
            alert_examples,
            product_examples,
            monitor_interval_hours,
            classification_confidence,
            metadata,
            monitored,
            first_discovered_at,
            last_seen_at,
            updated_at
        )
        VALUES (
            %(source_key)s,
            %(county_key)s,
            %(seed_slug)s,
            %(source_name)s,
            %(source_url)s,
            %(normalized_url)s,
            %(parent_url)s,
            %(discovery_method)s,
            %(source_type)s,
            %(platform)s,
            %(extraction_method)s,
            %(categories)s,
            %(audiences)s,
            %(value_score)s,
            %(risk_level)s,
            %(risk_memo)s,
            %(alert_examples)s,
            %(product_examples)s,
            %(monitor_interval_hours)s,
            %(classification_confidence)s,
            %(metadata)s,
            FALSE,
            NOW(),
            NOW(),
            NOW()
        )
        ON CONFLICT (source_key) DO UPDATE SET
            county_key = EXCLUDED.county_key,
            seed_slug = EXCLUDED.seed_slug,
            source_name = EXCLUDED.source_name,
            source_url = EXCLUDED.source_url,
            normalized_url = EXCLUDED.normalized_url,
            parent_url = EXCLUDED.parent_url,
            discovery_method = EXCLUDED.discovery_method,
            source_type = EXCLUDED.source_type,
            platform = EXCLUDED.platform,
            extraction_method = EXCLUDED.extraction_method,
            categories = EXCLUDED.categories,
            audiences = EXCLUDED.audiences,
            value_score = EXCLUDED.value_score,
            risk_level = EXCLUDED.risk_level,
            risk_memo = EXCLUDED.risk_memo,
            alert_examples = EXCLUDED.alert_examples,
            product_examples = EXCLUDED.product_examples,
            monitor_interval_hours = EXCLUDED.monitor_interval_hours,
            classification_confidence = EXCLUDED.classification_confidence,
            metadata = EXCLUDED.metadata,
            last_seen_at = NOW(),
            updated_at = NOW()
    """
    cur = database.cursor()
    try:
        execute_batch(cur, sql, [_candidate_params(candidate) for candidate in candidates], page_size=100)
    finally:
        cur.close()


def insert_source_observations(
    database: DatabaseResource,
    observations: list[ObservationRecord],
) -> None:
    """Insert append-only observations into meta.source_observations."""
    if not observations:
        return

    sql = """
        INSERT INTO meta.source_observations (
            source_key,
            county_key,
            source_url,
            probe_status,
            status_code,
            final_url,
            content_type,
            extraction_method,
            response_ms,
            content_hash,
            etag,
            last_modified,
            notes,
            metadata,
            checked_at
        )
        VALUES (
            %(source_key)s,
            %(county_key)s,
            %(source_url)s,
            %(probe_status)s,
            %(status_code)s,
            %(final_url)s,
            %(content_type)s,
            %(extraction_method)s,
            %(response_ms)s,
            %(content_hash)s,
            %(etag)s,
            %(last_modified)s,
            %(notes)s,
            %(metadata)s,
            NOW()
        )
    """
    cur = database.cursor()
    try:
        execute_batch(cur, sql, [_observation_params(observation) for observation in observations], page_size=200)
    finally:
        cur.close()


def promote_source_registry(
    database: DatabaseResource,
    promoted: list[CandidateRecord],
) -> None:
    """Upsert high-value candidates into meta.source_registry."""
    if not promoted:
        return

    sql = """
        INSERT INTO meta.source_registry (
            source_key,
            county_key,
            source_name,
            source_url,
            source_type,
            platform,
            extraction_method,
            categories,
            audiences,
            value_score,
            risk_level,
            risk_memo,
            alert_examples,
            product_examples,
            notes,
            health_status,
            last_status_code,
            last_probe_status,
            last_content_hash,
            promoted_at,
            last_checked_at,
            last_changed_at,
            active,
            monitor_interval_hours,
            metadata
        )
        VALUES (
            %(source_key)s,
            %(county_key)s,
            %(source_name)s,
            %(source_url)s,
            %(source_type)s,
            %(platform)s,
            %(extraction_method)s,
            %(categories)s,
            %(audiences)s,
            %(value_score)s,
            %(risk_level)s,
            %(risk_memo)s,
            %(alert_examples)s,
            %(product_examples)s,
            %(notes)s,
            %(health_status)s,
            %(last_status_code)s,
            %(last_probe_status)s,
            %(last_content_hash)s,
            NOW(),
            NOW(),
            %(last_changed_at)s,
            TRUE,
            %(monitor_interval_hours)s,
            %(metadata)s
        )
        ON CONFLICT (source_key) DO UPDATE SET
            county_key = EXCLUDED.county_key,
            source_name = EXCLUDED.source_name,
            source_url = EXCLUDED.source_url,
            source_type = EXCLUDED.source_type,
            platform = EXCLUDED.platform,
            extraction_method = EXCLUDED.extraction_method,
            categories = EXCLUDED.categories,
            audiences = EXCLUDED.audiences,
            value_score = EXCLUDED.value_score,
            risk_level = EXCLUDED.risk_level,
            risk_memo = EXCLUDED.risk_memo,
            alert_examples = EXCLUDED.alert_examples,
            product_examples = EXCLUDED.product_examples,
            notes = EXCLUDED.notes,
            health_status = CASE
                WHEN meta.source_registry.last_content_hash IS NOT NULL
                 AND meta.source_registry.last_content_hash IS DISTINCT FROM EXCLUDED.last_content_hash
                THEN 'changed'
                ELSE EXCLUDED.health_status
            END,
            last_status_code = EXCLUDED.last_status_code,
            last_probe_status = EXCLUDED.last_probe_status,
            last_content_hash = EXCLUDED.last_content_hash,
            last_checked_at = NOW(),
            last_changed_at = CASE
                WHEN meta.source_registry.last_content_hash IS NOT NULL
                 AND meta.source_registry.last_content_hash IS DISTINCT FROM EXCLUDED.last_content_hash
                THEN NOW()
                ELSE meta.source_registry.last_changed_at
            END,
            active = TRUE,
            monitor_interval_hours = EXCLUDED.monitor_interval_hours,
            metadata = EXCLUDED.metadata
    """

    rows = []
    for candidate in promoted:
        rows.append(
            {
                "source_key": candidate.source_key,
                "county_key": candidate.county_key,
                "source_name": candidate.source_name,
                "source_url": candidate.source_url,
                "source_type": candidate.source_type,
                "platform": candidate.platform,
                "extraction_method": candidate.extraction_method,
                "categories": Json(candidate.categories),
                "audiences": Json(candidate.audiences),
                "value_score": candidate.value_score,
                "risk_level": candidate.risk_level,
                "risk_memo": candidate.risk_memo,
                "alert_examples": Json(candidate.alert_examples),
                "product_examples": Json(candidate.product_examples),
                "notes": f"Promoted by County Scout from seed '{candidate.seed_slug}'",
                "health_status": _health_from_metadata(candidate.metadata),
                "last_status_code": candidate.metadata.get("status_code"),
                "last_probe_status": candidate.metadata.get("probe_status"),
                "last_content_hash": candidate.metadata.get("content_hash"),
                "last_changed_at": None,
                "monitor_interval_hours": candidate.monitor_interval_hours,
                "metadata": Json(candidate.metadata),
            }
        )

    cur = database.cursor()
    try:
        execute_batch(cur, sql, rows, page_size=100)
        database.execute(
            "UPDATE meta.source_candidates SET monitored = TRUE, updated_at = NOW() WHERE source_key = ANY(%s)",
            ([candidate.source_key for candidate in promoted],),
        )
    finally:
        cur.close()


def fetch_registry_sources(database: DatabaseResource, county_key: str) -> list[dict]:
    """Fetch active registry sources for monitoring."""
    rows = database.execute(
        """
        SELECT
            source_key,
            county_key,
            source_url,
            extraction_method,
            last_content_hash
        FROM meta.source_registry
        WHERE county_key = %s AND active = TRUE
        ORDER BY value_score DESC, source_name
        """,
        (county_key,),
    )
    return [
        {
            "source_key": row[0],
            "county_key": row[1],
            "source_url": row[2],
            "extraction_method": row[3],
            "last_content_hash": row[4],
        }
        for row in rows or []
    ]


def apply_registry_monitor_updates(
    database: DatabaseResource,
    updates: list[RegistryMonitorRecord],
) -> None:
    """Persist monitoring updates into meta.source_registry."""
    if not updates:
        return

    sql = """
        UPDATE meta.source_registry
        SET
            health_status = %(health_status)s,
            last_status_code = %(status_code)s,
            last_probe_status = %(probe_status)s,
            last_content_hash = %(content_hash)s,
            last_checked_at = NOW(),
            last_changed_at = CASE WHEN %(last_changed)s THEN NOW() ELSE last_changed_at END,
            notes = COALESCE(%(notes)s, notes),
            metadata = COALESCE(metadata, '{}'::jsonb) || %(metadata)s::jsonb
        WHERE source_key = %(source_key)s
    """
    cur = database.cursor()
    try:
        execute_batch(
            cur,
            sql,
            [
                {
                    "source_key": update.source_key,
                    "health_status": update.health_status,
                    "status_code": update.status_code,
                    "probe_status": update.probe_status,
                    "content_hash": update.content_hash,
                    "last_changed": update.last_changed,
                    "notes": update.notes,
                    "metadata": Json(update.metadata),
                }
                for update in updates
            ],
            page_size=100,
        )
    finally:
        cur.close()


def candidate_count_summary(database: DatabaseResource, county_key: str) -> tuple[int, int]:
    """Return candidate and registry counts for a county."""
    rows = database.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM meta.source_candidates WHERE county_key = %s),
            (SELECT COUNT(*) FROM meta.source_registry WHERE county_key = %s AND active = TRUE)
        """,
        (county_key, county_key),
    )
    if not rows:
        return 0, 0
    return int(rows[0][0]), int(rows[0][1])


def _candidate_params(candidate: CandidateRecord) -> dict:
    return {
        "source_key": candidate.source_key,
        "county_key": candidate.county_key,
        "seed_slug": candidate.seed_slug,
        "source_name": candidate.source_name,
        "source_url": candidate.source_url,
        "normalized_url": candidate.normalized_url,
        "parent_url": candidate.parent_url,
        "discovery_method": candidate.discovery_method,
        "source_type": candidate.source_type,
        "platform": candidate.platform,
        "extraction_method": candidate.extraction_method,
        "categories": Json(candidate.categories),
        "audiences": Json(candidate.audiences),
        "value_score": candidate.value_score,
        "risk_level": candidate.risk_level,
        "risk_memo": candidate.risk_memo,
        "alert_examples": Json(candidate.alert_examples),
        "product_examples": Json(candidate.product_examples),
        "monitor_interval_hours": candidate.monitor_interval_hours,
        "classification_confidence": candidate.classification_confidence,
        "metadata": Json(candidate.metadata),
    }


def _observation_params(observation: ObservationRecord) -> dict:
    return {
        "source_key": observation.source_key,
        "county_key": observation.county_key,
        "source_url": observation.source_url,
        "probe_status": observation.probe_status,
        "status_code": observation.status_code,
        "final_url": observation.final_url,
        "content_type": observation.content_type,
        "extraction_method": observation.extraction_method,
        "response_ms": observation.response_ms,
        "content_hash": observation.content_hash,
        "etag": observation.etag,
        "last_modified": observation.last_modified,
        "notes": observation.notes,
        "metadata": Json(observation.metadata),
    }


def _health_from_metadata(metadata: dict) -> str:
    probe_status = metadata.get("probe_status")
    if probe_status == "blocked":
        return "blocked"
    if probe_status == "error":
        return "error"
    if metadata.get("status_code") == 200:
        return "healthy"
    return "degraded"
