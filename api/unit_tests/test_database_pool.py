"""Connection-pool saturation must apply bounded backpressure."""

import threading
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from api.lib import database
from api.routes import parcels


class _UnusedPool:
    def __init__(self):
        self.getconn_calls = 0

    def getconn(self):
        self.getconn_calls += 1
        raise AssertionError("pool.getconn must not run without a permit")


def test_pool_saturation_times_out_before_getconn(monkeypatch):
    pool = _UnusedPool()
    gate = threading.BoundedSemaphore(0)
    monkeypatch.setenv("DATABASE_POOL_WAIT_SECONDS", "0")
    monkeypatch.setattr(database, "_get_pool_resources", lambda: (pool, gate))

    with pytest.raises(database.DatabasePoolExhausted):
        with database.get_cursor():
            pass

    assert pool.getconn_calls == 0


def test_pool_saturation_is_a_generic_http_503(monkeypatch):
    @contextmanager
    def exhausted_cursor():
        raise database.DatabasePoolExhausted("internal pool detail")
        yield  # pragma: no cover - context-manager generator marker

    monkeypatch.setattr(parcels, "get_cursor", exhausted_cursor)

    with TestClient(api_main.app) as client:
        response = client.get(
            "/api/parcels/bbox",
            params={
                "west": -76.9,
                "south": 39.9,
                "east": -76.8,
                "north": 40.0,
            },
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
    assert "internal pool detail" not in response.text


def test_pool_return_failure_does_not_leak_capacity(monkeypatch):
    class Connection:
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @contextmanager
        def cursor(self, **_kwargs):
            yield object()

    class Pool:
        def getconn(self):
            return Connection()

        def putconn(self, *_args, **_kwargs):
            raise RuntimeError("pool closed during cleanup")

    gate = threading.BoundedSemaphore(1)
    monkeypatch.setattr(database, "_get_pool_resources", lambda: (Pool(), gate))
    with pytest.raises(RuntimeError, match="pool closed"):
        with database.get_cursor():
            pass
    assert gate.acquire(blocking=False), "cleanup leaked the only pool permit"
