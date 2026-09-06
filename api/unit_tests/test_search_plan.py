"""Tests for the allowlisted natural-language search compiler."""

import pytest

from api.lib.search_plan import InvalidSearchPlan, compile_aggregate, compile_query


def test_query_compiles_identifiers_but_binds_model_values():
    compiled = compile_query(
        {
            "table": "parcels",
            "filters": [
                {"field": "class", "op": "eq", "value": "C"},
                {"field": "acres", "op": "gte", "value": 2},
            ],
            "signals": ["vacant", "tax_delinquent"],
            "location": {"type": "municipality", "value": "Spring Garden"},
            "sort": [{"field": "acres", "direction": "desc"}],
            "limit": 250,
        },
        max_limit=80,
    )

    assert compiled.table == "parcels"
    assert "staging.parcels AS base" in compiled.query
    assert "ST_Intersects" in compiled.query
    assert "base.acres DESC" in compiled.query
    assert compiled.query.endswith("LIMIT 80")
    assert "Spring Garden" not in compiled.query
    assert "owner_full" not in compiled.query
    assert set(compiled.params.values()) == {"C", 2, "%SPRING GARDEN%"}


def test_aggregate_compiles_allowlisted_metric_and_filters():
    compiled = compile_aggregate(
        {
            "table": "tax_claims",
            "aggregate": {"operation": "sum", "field": "total"},
            "filters": [{"field": "total", "op": "gt", "value": 0}],
            "location": {"type": "municipality", "value": "Dover Township"},
        }
    )

    assert "SELECT SUM(base.total) AS result" in compiled.query
    assert "UPPER(base.tax_district_name) LIKE" in compiled.query
    assert set(compiled.params.values()) == {0, "%DOVER TOWNSHIP%"}


def test_tax_claim_rows_are_not_queryable_but_aggregates_remain_available():
    with pytest.raises(InvalidSearchPlan, match="row queries are not allowed"):
        compile_query({"table": "tax_claims", "limit": 10}, max_limit=10)

    with pytest.raises(InvalidSearchPlan, match="unsupported filter field"):
        compile_aggregate(
            {
                "table": "tax_claims",
                "aggregate": {"operation": "sum", "field": "total"},
                "filters": [{"field": "owner_name", "op": "eq", "value": "A PERSON"}],
            }
        )


@pytest.mark.parametrize(
    "plan",
    [
        {"table": "parcels", "sql_where": "TRUE"},
        {
            "table": "parcels",
            "filters": [{"field": "owner_full; DROP TABLE x", "value": "x"}],
        },
        {
            "table": "parcels",
            "filters": [{"field": "owner_full", "op": "contains", "value": "\n"}],
        },
        {"table": "unknown"},
    ],
)
def test_query_rejects_raw_sql_and_values_outside_the_grammar(plan):
    with pytest.raises(InvalidSearchPlan):
        compile_query(plan, max_limit=20)


def test_aggregate_rejects_non_numeric_sum():
    with pytest.raises(InvalidSearchPlan):
        compile_aggregate(
            {
                "table": "parcels",
                "aggregate": {"operation": "sum", "field": "owner_full"},
            }
        )


def test_license_rows_exclude_licensee_identity():
    compiled = compile_query(
        {
            "table": "plcb_licenses",
            "filters": [{"field": "status", "op": "eq", "value": "Active"}],
        },
        max_limit=20,
    )

    assert "premises_name" in compiled.query
    assert "licensee" not in compiled.query
