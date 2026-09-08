"""Account-owned watches and saved investigations.

Verified external identity resolves CountyIQ workspace membership.
Inbox content is resolved through current feed policy rather than storing copies
of source data that might later be retracted.
"""

import os
import re
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator

from api.lib.accounts import account_workspace
from api.lib.auth import require_identity, require_workspace_write
from api.lib.database import get_cursor
from api.lib.rate_limit import PerClientRateLimiter, client_ip
from api.routes.feed import fetch_feed

router = APIRouter()
request_limiter = PerClientRateLimiter(rate_per_minute=60, burst=20)


def enabled():
    return os.environ.get("COUNTYIQ_WATCH_SYNC_ENABLED", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def require_enabled():
    if not enabled():
        raise HTTPException(503, "Server watches are not enabled on this deployment")


class WatchItem(BaseModel):
    kind: Literal["parcel", "project", "entity", "municipality"]
    subject_key: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid_key(self):
        if self.subject_key != self.subject_key.strip() or any(
            ord(c) < 32 for c in self.subject_key
        ):
            raise ValueError("Invalid subject key")
        if self.kind == "entity" and (
            not self.subject_key.isdigit() or int(self.subject_key) <= 0
        ):
            raise ValueError("Entity ID must be positive")
        return self


class SavedSearch(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["feed", "radar"]
    path: str = Field(max_length=2000)
    createdAt: datetime

    @model_validator(mode="after")
    def local_destination(self):
        url = urlsplit(self.path)
        if (
            url.scheme
            or url.netloc
            or url.fragment
            or url.path != "/" + self.kind
            or "\\" in self.path
        ):
            raise ValueError("Saved search must point to a local search page")
        return self


class RecentInvestigation(BaseModel):
    path: str = Field(max_length=500)
    label: str = Field(min_length=1, max_length=200)
    visitedAt: datetime

    @model_validator(mode="after")
    def local_destination(self):
        if not re.fullmatch(
            r"/(?:property|project|entity|owner|municipalities)/[A-Za-z0-9%:_.-]+",
            self.path,
        ):
            raise ValueError("Invalid investigation destination")
        return self


class WatchSnapshot(BaseModel):
    version: int = Field(ge=0)
    items: list[WatchItem] = Field(max_length=200)
    saved_searches: list[SavedSearch] = Field(default_factory=list, max_length=20)
    comparison: list[str] = Field(default_factory=list, max_length=4)
    recent_investigations: list[RecentInvestigation] = Field(
        default_factory=list, max_length=20
    )

    @model_validator(mode="after")
    def unique_bounded_items(self):
        if any(
            not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", key) for key in self.comparison
        ):
            raise ValueError("Invalid comparison parcel")
        keys = [(item.kind, item.subject_key) for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate watch")
        if any(
            sum(item.kind == kind for item in self.items) > 50
            for kind in ("parcel", "project", "entity", "municipality")
        ):
            raise ValueError("At most 50 watches of each kind")
        return self


class Acknowledge(BaseModel):
    notification_ids: list[Annotated[int, Field(gt=0, le=9223372036854775807)]] = Field(
        min_length=1, max_length=100
    )


def limited(request):
    require_enabled()
    require_identity(request)
    if request.method not in {"GET", "HEAD"}:
        require_workspace_write(request)
    if not request_limiter.allow(client_ip(request)):
        raise HTTPException(429, "Too many workspace requests")


@router.get("/status")
def status():
    return {"enabled": enabled()}


@router.post("")
def create(request: Request):
    require_identity(request)
    raise HTTPException(
        410, "Workspaces now belong to signed-in accounts. Initialize /api/session."
    )


@router.get("/current")
def current(request: Request):
    limited(request)
    with get_cursor() as cur:
        row = account_workspace(cur, request)
        cur.execute(
            "SELECT kind,subject_key,label FROM public.watch_items WHERE workspace_id=%s ORDER BY kind,subject_key",
            (row["workspace_id"],),
        )
        return {
            "version": row["version"],
            "items": [dict(item) for item in cur.fetchall()],
            "saved_searches": row["saved_searches"],
            "comparison": row["comparison"],
            "recent_investigations": row["recent_investigations"],
        }


@router.put("/current")
def save(snapshot: WatchSnapshot, request: Request):
    limited(request)
    with get_cursor(write=True) as cur:
        row = account_workspace(cur, request, lock=True)
        if row["version"] != snapshot.version:
            raise HTTPException(
                409, "Watches changed on another device. Reload before saving."
            )
        # Upsert retains added_at; replacing the snapshot must not reset the notification baseline.
        keys = [f"{item.kind}:{item.subject_key}" for item in snapshot.items]
        cur.execute(
            "DELETE FROM public.watch_items WHERE workspace_id=%s AND NOT (kind || ':' || subject_key = ANY(%s::text[]))",
            (row["workspace_id"], keys),
        )
        for item in snapshot.items:
            cur.execute(
                """INSERT INTO public.watch_items(workspace_id,kind,subject_key,label) VALUES (%s,%s,%s,%s)
                ON CONFLICT(workspace_id,kind,subject_key) DO UPDATE SET label=EXCLUDED.label""",
                (row["workspace_id"], item.kind, item.subject_key, item.label),
            )
        from psycopg2.extras import Json

        cur.execute(
            """UPDATE public.watchspaces SET version=version+1,updated_at=NOW(),
            saved_searches=%s,comparison=%s,recent_investigations=%s WHERE workspace_id=%s""",
            (
                Json(
                    [item.model_dump(mode="json") for item in snapshot.saved_searches]
                ),
                snapshot.comparison,
                Json(
                    [
                        item.model_dump(mode="json")
                        for item in snapshot.recent_investigations
                    ]
                ),
                row["workspace_id"],
            ),
        )
    return {**snapshot.model_dump(mode="json"), "version": snapshot.version + 1}


@router.delete("/current", status_code=204)
def delete(request: Request):
    limited(request)
    with get_cursor(write=True) as cur:
        row = account_workspace(cur, request, lock=True)
        cur.execute(
            "DELETE FROM public.watch_items WHERE workspace_id=%s",
            (row["workspace_id"],),
        )
        cur.execute(
            "DELETE FROM public.watch_notifications WHERE workspace_id=%s",
            (row["workspace_id"],),
        )
        cur.execute(
            """UPDATE public.watchspaces SET version=version+1,saved_searches='[]',comparison='{}',
            recent_investigations='[]',updated_at=NOW() WHERE workspace_id=%s""",
            (row["workspace_id"],),
        )


@router.get("/notifications")
def notifications(
    request: Request,
    before_id: int | None = Query(default=None, gt=0, le=9223372036854775807),
):
    limited(request)
    with get_cursor() as cur:
        row = account_workspace(cur, request)
        cur.execute(
            """SELECT n.notification_id,n.event_key,n.read_at
          FROM public.watch_notifications n JOIN public.current_intelligence_events e USING(event_key)
          WHERE workspace_id=%s AND n.read_at IS NULL AND (%s::bigint IS NULL OR n.notification_id<%s)
            AND (e.source_kind <> 'municipal_evidence' OR EXISTS (
              SELECT 1 FROM public.watch_items w
              WHERE w.workspace_id=n.workspace_id AND e.detected_at > w.added_at
                AND (
                  (w.kind='parcel' AND w.subject_key=ANY(e.related_pidns))
                  OR (w.kind='project' AND w.subject_key=e.project_key)
                  OR (w.kind='municipality' AND lower(replace(w.subject_key,'_',' '))=lower(replace(e.municipality,'_',' ')))
                  OR (w.kind='entity' AND EXISTS (
                    SELECT 1 FROM public.owners o
                    WHERE o.owner_id::text=w.subject_key AND EXISTS (
                      SELECT 1 FROM unnest(e.related_entities) name
                      WHERE lower(name)=lower(o.canonical_name)
                        OR lower(name)=ANY(ARRAY(SELECT lower(alias) FROM unnest(o.aliases) alias))
                    )
                  ))
                )
            ))
          ORDER BY n.notification_id DESC LIMIT 101""",
            (row["workspace_id"], before_id, before_id),
        )
        notices = [dict(item) for item in cur.fetchall()]
    has_more = len(notices) > 100
    notices = notices[:100]
    # A shared feed lookup enforces source governance and retractions.
    feed = (
        fetch_feed(
            event_keys=[item["event_key"] for item in notices],
            include_distress=True,
            since_days=None,
            limit=100,
        )
        if notices
        else {"events": []}
    )
    by_key = {event["event_key"]: event for event in feed["events"]}
    visible = [
        {"id": item["notification_id"], "event": by_key[item["event_key"]]}
        for item in notices
        if item["event_key"] in by_key
    ]
    return {
        "notifications": visible,
        "has_more": has_more,
        "next_before_id": notices[-1]["notification_id"] if has_more else None,
        "summary": f"{len(visible)} unread source-backed changes on your watches.",
    }


@router.post("/notifications/read")
def acknowledge(payload: Acknowledge, request: Request):
    limited(request)
    with get_cursor(write=True) as cur:
        row = account_workspace(cur, request)
        cur.execute(
            "UPDATE public.watch_notifications SET read_at=NOW() WHERE workspace_id=%s AND notification_id=ANY(%s::bigint[]) AND read_at IS NULL",
            (row["workspace_id"], payload.notification_ids),
        )
    return {"ok": True}
