"""The API's explicit watch writes must not unlock source-data mutations."""

import psycopg2
import pytest
from psycopg2 import sql

from api.lib.database import get_cursor


@pytest.mark.parametrize(
    "schema,table",
    [
        ("public", "intelligence_events"),
        ("public", "owners"),
        ("staging", "parcels"),
        ("meta", "intelligence_passes"),
    ],
)
def test_writable_transaction_cannot_modify_source_tables(client, schema, table):
    relation = f"{schema}.{table}"
    with get_cursor(write=True) as cur:
        cur.execute(
            "SELECT has_table_privilege(current_user,%s,'INSERT,UPDATE,DELETE,TRUNCATE') AS writable",
            (relation,),
        )
        assert cur.fetchone()["writable"] is False
    # Exercise the privilege boundary even when the transaction allows writes.
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        with get_cursor(write=True) as cur:
            cur.execute(
                sql.SQL("DELETE FROM {}.{} WHERE FALSE").format(
                    sql.Identifier(schema), sql.Identifier(table)
                )
            )
    with get_cursor() as cur:
        cur.execute("SHOW transaction_read_only")
        assert cur.fetchone()["transaction_read_only"] == "on"
