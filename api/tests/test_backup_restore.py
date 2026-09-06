"""Real PostgreSQL recovery of synthetic fixtures; no remote storage or live data."""

from __future__ import annotations

import subprocess
import uuid

import psycopg2
from psycopg2 import sql

from api.tests.conftest import API_DB_USER, DB_ENV, PIPELINES_DIR


def _database_inventory(database: str) -> dict:
    with psycopg2.connect(
        host=DB_ENV["DATABASE_HOST"],
        port=DB_ENV["DATABASE_PORT"],
        dbname=database,
        user=DB_ENV["DATABASE_USER"],
        password=DB_ENV["DATABASE_PASSWORD"],
    ) as connection:
        connection.set_session(readonly=True)
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT schemaname, tablename FROM pg_tables
                WHERE schemaname IN ('public', 'staging', 'meta')
                ORDER BY schemaname, tablename
            """)
            tables = cursor.fetchall()
            result = {}
            for schema, table in tables:
                cursor.execute(
                    sql.SQL("""
                    SELECT count(*), md5(COALESCE(string_agg(
                        to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text
                    ), '')) FROM {}.{} t
                """).format(sql.Identifier(schema), sql.Identifier(table))
                )
                result[f"{schema}.{table}"] = cursor.fetchone()
            cursor.execute(
                "SELECT extname, extversion FROM pg_extension ORDER BY extname"
            )
            result["extensions"] = cursor.fetchall()
            cursor.execute("SELECT count(*) FROM public.properties")
            result["properties_view"] = cursor.fetchone()
            cursor.execute(
                """
                SELECT has_table_privilege(%s, 'public.properties', 'SELECT'),
                       has_table_privilege(%s, 'staging.parcels', 'DELETE')
            """,
                (API_DB_USER, API_DB_USER),
            )
            result["api_permissions"] = cursor.fetchone()
            return result


def test_actual_dump_restores_schema_records_and_api_grants(
    prepared_database, tmp_path
):
    # The autouse fixture creates and seeds only this dedicated database.
    assert DB_ENV["DATABASE_NAME"] == "countyiq_test"
    source = DB_ENV["DATABASE_NAME"]
    target = "countyiq_test_restore_" + uuid.uuid4().hex
    dump = tmp_path / "synthetic.dump"
    created = False
    docker = ["docker", "compose", "exec", "-T", "postgres-test"]

    def command(*args, **kwargs):
        return subprocess.run(
            [*docker, *args],
            cwd=PIPELINES_DIR,
            check=True,
            timeout=90,
            stderr=subprocess.PIPE,
            **kwargs,
        )

    before = _database_inventory(source)
    try:
        with dump.open("wb") as stream:
            command(
                "pg_dump",
                "-U",
                DB_ENV["DATABASE_USER"],
                "--format=custom",
                source,
                stdout=stream,
            )
        command("createdb", "-U", DB_ENV["DATABASE_USER"], target)
        created = True
        with dump.open("rb") as stream:
            command(
                "pg_restore",
                "-U",
                DB_ENV["DATABASE_USER"],
                "--exit-on-error",
                "--no-owner",
                "-d",
                target,
                stdin=stream,
            )
        restored = _database_inventory(target)
        assert restored == before
        assert restored["api_permissions"] == (True, False)
        assert _database_inventory(source) == before
    finally:
        # Never reset an occupied name or drop a database we did not create.
        if created:
            command("dropdb", "-U", DB_ENV["DATABASE_USER"], target)
