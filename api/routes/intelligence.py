"""Read-only, source-current emerging cases; requests never invoke inference."""

from datetime import timedelta
from hashlib import sha256
from threading import Lock
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from api.lib.database import get_cursor
from api.lib.emerging_intelligence import present_cases
from api.lib.feed_cache import FeedPageCache, read_feed_revision

router = APIRouter()
_snapshots = FeedPageCache(capacity=2)
_snapshot_lock = Lock()


def _current_snapshot(cur) -> dict:
    """Reuse one complete currentness check while all dependency revisions match.

    Filters run on the server against this bounded-cache snapshot before slicing.
    Publication actions, every context layer, source changes and policy dates all
    invalidate the snapshot transactionally; time alone never keeps revoked data.
    """
    revision, checked_at = read_feed_revision(cur)
    with _snapshot_lock:
        cached = _snapshots.get("cases", revision, checked_at)
        if cached is not None:
            return cached
        cur.execute("SELECT * FROM public.current_emerging_analyses")
        analyses = list(cur.fetchall())
        rows = []
        for analysis in analyses:
            payload = analysis["payload"]
            for hypothesis in payload["analysis"]["hypotheses"]:
                identity = analysis["subject_key"] + "|" + hypothesis["family"]
                rows.append(
                    {
                        "case_key": "emerging-" + sha256(identity.encode()).hexdigest(),
                        "inference_id": analysis["inference_id"],
                        "created_at": analysis["created_at"],
                        "packet": payload["packet"],
                        "analysis": payload["analysis"],
                        "hypothesis": hypothesis,
                    }
                )
        rows.sort(key=lambda row: row["case_key"])
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        current_ids = [row["inference_id"] for row in analyses]
        cur.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (subject_key) inference_id
                FROM meta.intelligence_inference_history
                WHERE output_kind='emerging_analysis' AND disposition='accepted'
                ORDER BY subject_key, inference_id DESC
            )
            SELECT (SELECT count(*) FROM public.current_municipal_matter_inputs) AS available_records,
                count(*) AS assessed_scopes,
                count(*) FILTER (WHERE (
                    SELECT action FROM meta.emerging_intelligence_publications review
                    WHERE review.inference_id=latest.inference_id
                    ORDER BY publication_id DESC LIMIT 1
                )='publish' AND NOT (inference_id=ANY(%s::bigint[]))) AS awaiting_refresh
            FROM latest
        """,
            (current_ids,),
        )
        coverage = {
            **dict(cur.fetchone()),
            "current_cases": len(rows),
            "note": "Reviewed cases cover selected evidence scopes. Unassessed places may still contain opportunities; an empty result does not establish inactivity.",
            "missing_source_families": [
                "Project-specific utility capacity and service commitments",
                "Complete permit and construction-start histories",
                "Current procurement, financing and contractor commitments",
            ],
        }
        result = {"cases": present_cases(cur, rows), "coverage": coverage}
        _snapshots.put("cases", revision, checked_at + timedelta(minutes=5), result)
        return result


@router.get("")
def cases(
    family: Annotated[list[str] | None, Query(max_length=6)] = None,
    municipality: Annotated[list[str] | None, Query(max_length=80)] = None,
    service: Annotated[list[str] | None, Query(max_length=20)] = None,
    case_key: Annotated[list[str] | None, Query(max_length=100)] = None,
    exclude_case_key: Annotated[list[str] | None, Query(max_length=100)] = None,
    project_type: Annotated[list[str] | None, Query(max_length=6)] = None,
    readiness: Annotated[list[str] | None, Query(max_length=5)] = None,
    audience: str | None = Query(default=None, pattern="^(investor|service_business)$"),
    q: str | None = Query(default=None, max_length=200),
    pidn: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    opportunities_only: bool = False,
):
    if audience == "investor":
        service = None
    with get_cursor(snapshot=True) as cur:
        snapshot = _current_snapshot(cur)
    filtered = []
    for item in snapshot["cases"]:
        if family and item["family"] not in family:
            continue
        if case_key and item["case_key"] not in case_key:
            continue
        if exclude_case_key and item["case_key"] in exclude_case_key:
            continue
        if project_type and not set(project_type).intersection(item["project_types"]):
            continue
        if municipality and not {
            value.casefold() for value in municipality
        }.intersection(value.casefold() for value in item["municipalities"]):
            continue
        if pidn and not any(prop["pidn"] == pidn for prop in item["properties"]):
            continue
        if (
            q
            and q.casefold()
            not in (item["title"] + " " + item["hypothesis"]).casefold()
        ):
            continue
        opportunities = (
            item["opportunities"]
            if opportunities_only
            else item["opportunities"] + item["implications"]
        )
        if opportunities_only and not opportunities:
            continue
        if (audience or service or readiness) and not any(
            (not audience or opportunity["audience"] == audience)
            and (not service or set(service).intersection(opportunity["services"]))
            and (not readiness or opportunity["readiness"] in readiness)
            for opportunity in opportunities
        ):
            continue
        filtered.append(item)
    return {
        "cases": filtered[offset : offset + limit],
        "total": len(filtered),
        "coverage": snapshot["coverage"],
    }


@router.get("/{case_key}")
def case(case_key: str):
    with get_cursor(snapshot=True) as cur:
        snapshot = _current_snapshot(cur)
    for item in snapshot["cases"]:
        if item["case_key"] == case_key:
            return item
    raise HTTPException(
        404,
        "This case is unavailable or needs reassessment after its evidence changed.",
    )
