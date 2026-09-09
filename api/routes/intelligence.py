"""Paged source-current case summaries and evidence on demand; never inference."""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from api.lib.database import get_cursor
from api.lib.emerging_pages import filter_fingerprint, load_case, load_page
from api.lib.feed_cache import FeedPageCache, read_feed_revision

router = APIRouter()
_pages = FeedPageCache(capacity=32)


def _cached_read(cur, key: str, load):
    revision, checked_at = read_feed_revision(cur)
    cached = _pages.get(key, revision, checked_at)
    if cached is not None:
        return cached
    result = load()
    if result is not None:
        _pages.put(key, revision, checked_at + timedelta(minutes=5), result)
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
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=1024),
    offset: int | None = Query(default=None, ge=0, le=10000),
    opportunities_only: bool = False,
):
    if offset:
        raise HTTPException(422, "Use the next_cursor returned by the previous page.")
    filters = {
        "family": sorted(set(family or [])),
        "municipality": sorted({value.lower() for value in municipality or []}),
        "service": sorted(set(service or [])) if audience != "investor" else [],
        "case_key": sorted(set(case_key or [])),
        "exclude_case_key": sorted(set(exclude_case_key or [])),
        "project_type": sorted(set(project_type or [])),
        "readiness": sorted(set(readiness or [])),
        "audience": audience,
        "q": q.lower() if q else None,
        "pidn": pidn,
        "opportunities_only": opportunities_only,
    }
    key = f"page:{filter_fingerprint(filters)}:{limit}:{cursor or ''}"
    try:
        with get_cursor(snapshot=True) as cur:
            return _cached_read(
                cur, key, lambda: load_page(cur, filters, limit, cursor)
            )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/{case_key}")
def case(case_key: str):
    with get_cursor(snapshot=True) as cur:
        result = _cached_read(cur, "case:" + case_key, lambda: load_case(cur, case_key))
    if result is None:
        raise HTTPException(
            404,
            "This case is unavailable or needs reassessment after its evidence changed.",
        )
    return result
