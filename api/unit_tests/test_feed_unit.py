"""Database-independent contract tests for the unified feed route."""

from contextlib import contextmanager
from datetime import date, datetime, timezone

from api.routes import feed


class _Cursor:
    def __init__(self, rows: list[dict], owners: list[dict]):
        self.rows = rows
        self.owners = owners
        self.sql = ""
        self.params: dict[str, object] = {}
        self.executions: list[tuple[str, dict[str, object]]] = []

    def execute(self, sql: str, params: dict[str, object]) -> None:
        self.sql = sql
        self.params = params
        self.executions.append((sql, params))

    def fetchall(self) -> list[dict]:
        return self.rows if len(self.executions) == 1 else self.owners


def test_feed_filters_serializes_and_paginates(monkeypatch):
    generated_at = datetime(2026, 8, 27, 12, 30, tzinfo=timezone.utc)
    rows = [
        {
            "event_key": "development:first",
            "category": "development",
            "event_type": "approval",
            "event_tags": ["application", "hearing", "approval", "condition"],
            "title": "Approval: Main Street subdivision",
            "what_happened": "The commission approved the plan with one condition.",
            "why_it_matters": "The approval advances the public review process.",
            "what_happens_next": "The applicant must satisfy the stated condition.",
            "event_date": date(2026, 8, 20),
            "detected_at": generated_at,
            "confidence": 0.91,
            "municipality": "Test Township",
            "project_key": "project:abc",
            "project_name": "Main Street subdivision",
            "related_entities": ["Alpha Holdings LLC"],
            "related_pidns": ["0000000000001"],
            "source_evidence": [
                {
                    "label": "Test Township Planning Commission",
                    "url": "https://example.com/meeting",
                    "document_url": "https://example.com/minutes.pdf",
                    "excerpt": "The commission approved the plan.",
                    "details": {"decision": "approved"},
                }
            ],
            "interpretation_kind": "llm",
            "interpretation_model": "test-model",
            "interpretation_generated_at": generated_at,
            "priority_score": 118,
        },
        {
            "event_key": "development:second",
            "category": "development",
            "event_type": "hearing",
            "event_tags": ["hearing"],
            "title": "Second event proves has_more",
            "what_happened": "A hearing occurred.",
            "why_it_matters": "The matter entered public review.",
            "what_happens_next": "Monitor the decision.",
            "event_date": date(2026, 8, 19),
            "detected_at": generated_at,
            "confidence": 0.8,
            "municipality": "Test Township",
            "project_key": None,
            "project_name": None,
            "related_entities": [],
            "related_pidns": [],
            "source_evidence": [],
            "interpretation_kind": "deterministic",
            "interpretation_model": None,
            "interpretation_generated_at": None,
            "priority_score": 80,
        },
    ]
    cursor = _Cursor(
        rows,
        [
            {
                "owner_id": 7,
                "canonical_name": "Alpha Holdings LLC",
                "aliases": [],
                "verification_status": "verified",
            }
        ],
    )

    @contextmanager
    def fake_get_cursor():
        yield cursor

    monkeypatch.setattr(feed, "get_cursor", fake_get_cursor)
    monkeypatch.setattr(feed, "require_source_use", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(feed, "source_use_allowed", lambda *_args, **_kwargs: True)

    response = feed.intelligence_feed(
        category="development",
        event_type="approval,not-a-real-tag",
        municipality="Test Township",
        since_days=30,
        pidns="0000000000001",
        project_keys="project:abc",
        entity_names=None,
        entity_ids="7,not-an-id",
        sort="priority",
        limit=1,
        offset=2,
    )

    feed_sql, feed_params = cursor.executions[0]
    assert "event_tags && %(event_types)s::text[]" in feed_sql
    assert "related_pidns && %(pidns)s::text[]" in feed_sql
    assert "project_key = ANY(%(project_keys)s::text[])" in feed_sql
    assert "watched_owner.owner_id = ANY(%(entity_ids)s::integer[])" in feed_sql
    assert "priority_score DESC" in feed_sql
    assert feed_params == {
        "fetch_limit": 2,
        "offset": 2,
        "category": "development",
        "event_types": ["approval"],
        "municipality": "Test Township",
        "since_days": 30,
        "pidns": ["0000000000001"],
        "project_keys": ["project:abc"],
        "entity_ids": [7],
    }
    assert response["has_more"] is True
    assert response["limit"] == 1
    assert len(response["events"]) == 1
    event = response["events"][0]
    assert event["event_date"] == "2026-08-20"
    assert event["detected_at"] == "2026-08-27T12:30:00+00:00"
    assert event["project"] == {
        "key": "project:abc",
        "name": "Main Street subdivision",
    }
    assert event["entity_links"] == [
        {
            "owner_id": 7,
            "name": "Alpha Holdings LLC",
            "matched_name": "Alpha Holdings LLC",
            "verification_status": "verified",
        }
    ]
    assert event["importance_score"] == 118
    assert "Decision or deadline" in event["importance_reasons"]
    assert event["interpretation"] == {
        "kind": "llm",
        "model": "test-model",
        "generated_at": "2026-08-27T12:30:00+00:00",
    }
