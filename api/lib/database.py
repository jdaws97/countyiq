"""Database helpers for the FastAPI Lambda API."""

from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor


def _connection_kwargs() -> dict:
    return {
        "host": os.environ.get("DATABASE_HOST", "localhost"),
        "port": int(os.environ.get("DATABASE_PORT", "5432")),
        "dbname": os.environ.get("DATABASE_NAME", "countyiq"),
        "user": os.environ.get("DATABASE_USER", "dagster_admin"),
        "password": os.environ.get("DATABASE_PASSWORD", "localtest"),
        "connect_timeout": 5,
    }


@contextmanager
def get_cursor():
    """Yield a RealDictCursor for one request."""
    conn = psycopg2.connect(**_connection_kwargs())
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
    finally:
        conn.close()
