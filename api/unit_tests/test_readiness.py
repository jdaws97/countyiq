"""Readiness must fail closed without exposing database error details."""

from contextlib import contextmanager

from fastapi.testclient import TestClient
from psycopg2 import OperationalError

import api.main as api_main


def test_readiness_returns_generic_503_when_database_is_unavailable(monkeypatch):
    @contextmanager
    def unavailable_cursor():
        raise OperationalError("host=secret.internal password=do-not-leak")
        yield  # pragma: no cover - makes this a context manager generator

    monkeypatch.setattr(api_main, "get_cursor", unavailable_cursor)

    with TestClient(api_main.app) as client:
        response = client.get("/api/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
    assert "secret.internal" not in response.text
