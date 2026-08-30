from __future__ import annotations

from datetime import date

from api.routes.ops import _get_municipality_source_status, _get_source_policy_status


class _Cursor:
    def __init__(self, row: dict):
        self.row = row
        self.query = ""

    def execute(self, query: str, _params=None) -> None:
        self.query = query

    def fetchone(self) -> dict:
        return self.row


def test_source_policy_health_exposes_review_deadlines():
    cursor = _Cursor(
        {
            "configured_count": 11,
            "active_count": 8,
            "conditional_count": 4,
            "paused_count": 3,
            "overdue_count": 0,
            "due_soon_count": 2,
            "next_review_on": date(2026, 11, 27),
        }
    )

    status = _get_source_policy_status(cursor)

    assert status == {
        "status": "green",
        "record_count": 8,
        "configured_count": 11,
        "active_count": 8,
        "healthy_count": 8,
        "blocked_count": 3,
        "unchecked_count": 0,
        "conditional_count": 4,
        "paused_count": 3,
        "overdue_count": 0,
        "due_soon_count": 2,
        "next_review_on": date(2026, 11, 27),
    }
    assert "CURRENT_DATE + 30" in cursor.query


def test_municipality_health_excludes_paused_document_counts():
    cursor = _Cursor(
        {
            "configured_count": 122,
            "active_count": 110,
            "healthy_count": 96,
            "blocked_count": 26,
            "unchecked_count": 0,
            "document_count": 7152,
        }
    )

    status = _get_municipality_source_status(cursor)

    assert status == {
        "status": "red",
        "record_count": 7152,
        "configured_count": 122,
        "active_count": 110,
        "healthy_count": 96,
        "blocked_count": 26,
        "unchecked_count": 0,
    }
    assert "SUM(h.document_count) FILTER (WHERE r.acquisition_allowed)" in cursor.query
    assert "policy_skipped" in cursor.query
    assert "policy_no_documents" in cursor.query
