"""County Scout API routes."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException, Query

from api.lib.database import get_cursor

router = APIRouter(tags=["scout"])


@router.get("/summary")
def scout_summary(
    county: str = Query(default="york", description="County key, starting with york"),
) -> dict:
    """Summarize County Scout discovery depth and registry composition."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM meta.source_candidates WHERE county_key = %s) AS candidate_count,
                (SELECT COUNT(*) FROM meta.source_registry WHERE county_key = %s AND active = TRUE) AS monitored_count
            """,
            (county, county),
        )
        counts = cur.fetchone()

        cur.execute(
            """
            SELECT
                source_key,
                source_name,
                categories,
                extraction_method,
                platform,
                risk_level,
                health_status,
                value_score
            FROM meta.source_registry
            WHERE county_key = %s AND active = TRUE
            ORDER BY value_score DESC, source_name
            """,
            (county,),
        )
        rows = cur.fetchall()

    category_counts = Counter()
    extraction_counts = Counter()
    platform_counts = Counter()
    risk_counts = Counter()
    health_counts = Counter()
    high_value = 0

    for row in rows:
        for category in row["categories"] or []:
            category_counts[category] += 1
        extraction_counts[row["extraction_method"]] += 1
        platform_counts[row["platform"]] += 1
        risk_counts[row["risk_level"]] += 1
        health_counts[row["health_status"]] += 1
        if row["value_score"] >= 85:
            high_value += 1

    return {
        "county": county,
        "candidate_count": counts["candidate_count"] if counts else 0,
        "monitored_count": counts["monitored_count"] if counts else 0,
        "high_value_monitored_count": high_value,
        "by_category": dict(sorted(category_counts.items())),
        "by_extraction_method": dict(sorted(extraction_counts.items())),
        "by_platform": dict(sorted(platform_counts.items())),
        "by_risk_level": dict(sorted(risk_counts.items())),
        "by_health_status": dict(sorted(health_counts.items())),
    }


@router.get("/registry")
def scout_registry(
    county: str = Query(default="york"),
    category: str | None = Query(default=None),
    min_score: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """List promoted sources in the monitored source registry."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                r.source_key,
                r.county_key,
                r.source_name,
                r.source_url,
                r.source_type,
                r.platform,
                r.extraction_method,
                r.categories,
                r.audiences,
                r.value_score,
                r.risk_level,
                r.risk_memo,
                r.alert_examples,
                r.product_examples,
                r.health_status,
                r.last_status_code,
                r.last_probe_status,
                r.last_checked_at,
                r.last_changed_at,
                latest.checked_at AS last_observed_at
            FROM meta.source_registry r
            LEFT JOIN LATERAL (
                SELECT checked_at
                FROM meta.source_observations o
                WHERE o.source_key = r.source_key
                ORDER BY checked_at DESC
                LIMIT 1
            ) latest ON TRUE
            WHERE r.county_key = %s
              AND r.active = TRUE
              AND r.value_score >= %s
            ORDER BY r.value_score DESC, r.source_name
            LIMIT %s
            """,
            (county, min_score, limit),
        )
        rows = cur.fetchall()

    filtered = [
        row
        for row in rows
        if category is None or category in (row["categories"] or [])
    ]
    return {"county": county, "count": len(filtered), "items": filtered}


@router.get("/candidates")
def scout_candidates(
    county: str = Query(default="york"),
    category: str | None = Query(default=None),
    monitored_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """List current source candidates, whether promoted or not."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                source_key,
                county_key,
                seed_slug,
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
                monitored,
                classification_confidence,
                last_seen_at,
                updated_at
            FROM meta.source_candidates
            WHERE county_key = %s
              AND (%s = FALSE OR monitored = TRUE)
            ORDER BY value_score DESC, source_name
            LIMIT %s
            """,
            (county, monitored_only, limit),
        )
        rows = cur.fetchall()

    filtered = [
        row
        for row in rows
        if category is None or category in (row["categories"] or [])
    ]
    return {"county": county, "count": len(filtered), "items": filtered}


@router.get("/sources/{source_key}")
def scout_source_detail(source_key: str) -> dict:
    """Return current source details with recent observations."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                c.*,
                r.health_status,
                r.last_status_code,
                r.last_probe_status,
                r.last_checked_at,
                r.last_changed_at,
                r.active AS registry_active
            FROM meta.source_candidates c
            LEFT JOIN meta.source_registry r
                ON r.source_key = c.source_key
            WHERE c.source_key = %s
            """,
            (source_key,),
        )
        source = cur.fetchone()
        if source is None:
            raise HTTPException(status_code=404, detail="Source not found")

        cur.execute(
            """
            SELECT
                checked_at,
                probe_status,
                status_code,
                final_url,
                content_type,
                extraction_method,
                response_ms,
                content_hash,
                notes
            FROM meta.source_observations
            WHERE source_key = %s
            ORDER BY checked_at DESC
            LIMIT 20
            """,
            (source_key,),
        )
        observations = cur.fetchall()

    return {"source": source, "observations": observations}
