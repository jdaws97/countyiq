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
from psycopg2.pool import ThreadedConnectionPool


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
_pool_lock = threading.Lock()


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadedConnectionPool(
                    minconn=int(os.environ.get("DATABASE_POOL_MIN", "1")),
                    maxconn=int(os.environ.get("DATABASE_POOL_MAX", "8")),
                    **_connection_kwargs(),
                )
    return _pool


def close_pool() -> None:
    """Close all pooled connections (app shutdown / test teardown)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.closeall()
            _pool = None


@contextmanager
def get_cursor() -> Iterator[RealDictCursor]:
    """Yield a RealDictCursor backed by a pooled connection."""
    pool = _get_pool()
    conn = pool.getconn()
    broken = False
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
    except psycopg2.OperationalError:
        # Connection likely died (server restart, network); drop it from the
        # pool instead of recycling a broken socket.
        broken = True
        raise
    finally:
        pool.putconn(conn, close=broken or conn.closed)
