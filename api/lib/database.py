"""Database helpers for the FastAPI API service.

Connections come from a process-wide ThreadedConnectionPool instead of a
fresh psycopg2.connect() per request: with 2 uvicorn workers and FastAPI's
~40-thread pool for sync endpoints, per-request connects could stack up to
~80 simultaneous handshakes against Postgres's default max_connections=100,
with setup latency on every request.

Pool sizing: each uvicorn worker process gets its own pool of up to
DATABASE_POOL_MAX (default 8) connections — 2 workers x 8 = 16 peak, well
inside the connection budget documented in docs/api/api.md.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import PoolError, ThreadedConnectionPool


class DatabasePoolExhausted(RuntimeError):
    """Raised when no database connection becomes available before timeout."""


def _connection_kwargs() -> dict[str, str | int]:
    return {
        "host": os.environ.get("DATABASE_HOST", "localhost"),
        "port": int(os.environ.get("DATABASE_PORT", "5432")),
        "dbname": os.environ.get("DATABASE_NAME", "countyiq"),
        "user": os.environ.get("DATABASE_USER", "dagster_admin"),
        "password": os.environ.get("DATABASE_PASSWORD", "localtest"),
        "connect_timeout": 5,
    }


_pool: ThreadedConnectionPool | None = None
_pool_gate: threading.BoundedSemaphore | None = None
_pool_lock = threading.Lock()


def _get_pool_resources() -> tuple[ThreadedConnectionPool, threading.BoundedSemaphore]:
    global _pool, _pool_gate
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                max_connections = int(os.environ.get("DATABASE_POOL_MAX", "8"))
                pool = ThreadedConnectionPool(
                    minconn=int(os.environ.get("DATABASE_POOL_MIN", "1")),
                    maxconn=max_connections,
                    **_connection_kwargs(),
                )
                _pool = pool
                _pool_gate = threading.BoundedSemaphore(max_connections)
    if _pool_gate is None:  # pragma: no cover - defensive invariant
        raise RuntimeError("database connection gate is not initialized")
    return _pool, _pool_gate


def close_pool() -> None:
    """Close all pooled connections (app shutdown / test teardown)."""
    global _pool, _pool_gate
    with _pool_lock:
        if _pool is not None:
            _pool.closeall()
            _pool = None
            _pool_gate = None


@contextmanager
def get_cursor() -> Iterator[RealDictCursor]:
    """Yield a RealDictCursor backed by a pooled connection."""
    pool, gate = _get_pool_resources()
    wait_seconds = max(
        0.0,
        float(os.environ.get("DATABASE_POOL_WAIT_SECONDS", "5")),
    )
    if not gate.acquire(timeout=wait_seconds):
        raise DatabasePoolExhausted("database connection pool is busy")

    conn = None
    broken = False
    try:
        try:
            conn = pool.getconn()
        except PoolError as exc:
            raise DatabasePoolExhausted(
                "database connection pool is busy"
            ) from exc
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
    except psycopg2.OperationalError:
        # Connection likely died (server restart, network); drop it from the
        # pool instead of recycling a broken socket.
        broken = True
        raise
    finally:
        if conn is not None:
            pool.putconn(conn, close=broken or conn.closed)
        gate.release()
