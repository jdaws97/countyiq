"""Inbox pagination remains navigable when source policy suppresses a page."""
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import watchspaces


def test_hidden_page_retains_cursor_and_does_not_acknowledge(monkeypatch):
    executions = []
    pages = [
        [{"notification_id": i, "event_key": f"event-{i}"} for i in range(201, 100, -1)],
        [{"notification_id": 101, "event_key": "event-101"}],
    ]

    class Cursor:
        def execute(self, sql, params):
            executions.append((sql, params))

        def fetchall(self):
            return pages.pop(0)

    @contextmanager
    def cursor():
        yield Cursor()

    monkeypatch.setattr(watchspaces, "get_cursor", cursor)
    monkeypatch.setattr(watchspaces, "account_workspace", lambda *a, **kw: {"workspace_id": "own-workspace"})
    monkeypatch.setattr(watchspaces, "limited", lambda request: None)
    lookups = []

    def governed_feed(**kwargs):
        lookups.append(kwargs)
        return {"events": [{"event_key": "event-101"}] if kwargs["event_keys"] == ["event-101"] else []}

    monkeypatch.setattr(watchspaces, "fetch_feed", governed_feed)
    first = watchspaces.notifications(None, before_id=None)
    assert first["notifications"] == []
    assert first["has_more"] is True
    assert first["next_before_id"] == 102
    # Lookahead must not be consumed on the first page.
    assert len(lookups[0]["event_keys"]) == 100
    assert "event-101" not in lookups[0]["event_keys"]
    second = watchspaces.notifications(None, before_id=first["next_before_id"])
    assert second["notifications"] == [{"id": 101, "event": {"event_key": "event-101"}}]
    assert second["has_more"] is False
    assert second["next_before_id"] is None
    assert executions[1][1] == ("own-workspace", 102, 102)
    assert all(sql.lstrip().startswith("SELECT") for sql, _ in executions)


def test_exact_full_page_has_no_false_next_page(monkeypatch):
    class Cursor:
        def execute(self, *args):
            pass

        def fetchall(self):
            return [{"notification_id": i, "event_key": str(i)} for i in range(100, 0, -1)]

    @contextmanager
    def cursor():
        yield Cursor()

    monkeypatch.setattr(watchspaces, "get_cursor", cursor)
    monkeypatch.setattr(watchspaces, "account_workspace", lambda *a, **kw: {"workspace_id": "own-workspace"})
    monkeypatch.setattr(watchspaces, "limited", lambda request: None)
    monkeypatch.setattr(watchspaces, "fetch_feed", lambda **kw: {"events": []})
    result = watchspaces.notifications(None, before_id=None)
    assert result["has_more"] is False
    assert result["next_before_id"] is None


@pytest.mark.parametrize("identifier", [0, -1, 9223372036854775808])
def test_out_of_range_ids_fail_validation_before_database(identifier):
    app = FastAPI()
    app.include_router(watchspaces.router, prefix="/watchspaces")
    with TestClient(app) as client:
        assert client.get("/watchspaces/notifications", params={"before_id": identifier}).status_code == 422
        assert client.post("/watchspaces/notifications/read", json={"notification_ids": [identifier]}).status_code == 422
