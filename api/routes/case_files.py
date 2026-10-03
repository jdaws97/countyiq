"""Project investigation views over the same governed events as the feed."""

from fastapi import APIRouter, Path

from api.lib.project_status import summarize_project
from api.routes.feed import fetch_feed

router = APIRouter()


@router.get("/{project_key}")
def project_case(
    project_key: str = Path(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9:_-]+$"),
) -> dict:
    feed = fetch_feed(
        category="development",
        project_keys=project_key,
        since_days=None,
        sort="latest",
        limit=500,
    )
    # A municipal matter has one current account, in either Activity or
    # Research. Its direct case link must remain usable from either surface.
    if project_key.startswith("matter:") and not feed["events"]:
        feed = fetch_feed(
            category="development",
            project_keys=project_key,
            since_days=None,
            sort="latest",
            view="research",
            limit=500,
        )
    return {
        **feed,
        "summary": summarize_project(feed["events"], incomplete=feed["has_more"]),
    }
