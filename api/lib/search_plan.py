"""Compile allowlisted natural-language search plans into parameterized SQL.

The LLM may classify intent and supply values, but it never supplies SQL.
Identifiers and expressions come exclusively from the declarations below;
all user/model values are bound as query parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


class InvalidSearchPlan(ValueError):
    """Raised when a model response falls outside the supported query grammar."""


@dataclass(frozen=True)
class Field:
    expression: str
    kind: str = "text"


@dataclass(frozen=True)
class Table:
    fqn: str
    fields: dict[str, Field]
    row_query_allowed: bool = True
    projection: str = "base.*"


@dataclass(frozen=True)
class CompiledSearch:
    query: str
    params: dict[str, object]
    table: str


TABLES: dict[str, Table] = {
    "parcels": Table(
        "staging.parcels",
        {
            "pidn": Field("base.pidn"),
            "propadr": Field("base.propadr"),
            "municipality": Field("base.municipality"),
            "class": Field("base.class"),
            "acres": Field("base.acres", "number"),
            "aprtotal": Field("base.aprtotal::numeric", "number"),
            "aprland": Field("base.aprland::numeric", "number"),
            "aprbldg": Field("base.aprbldg::numeric", "number"),
            "price": Field("base.price::numeric", "number"),
            "saledt": Field("TO_DATE(base.saledt, 'DD-MON-YYYY')", "date"),
            "school_dis": Field("base.school_dis"),
        },
        projection=(
            "base.pidn, base.propadr, base.municipality, base.class, base.acres, "
            "base.aprtotal, base.aprland, base.aprbldg, base.price, base.saledt, "
            "base.school_dis"
        ),
    ),
    "tax_claims": Table(
        "staging.tax_claims",
        {
            "pidn": Field("base.pidn"),
            "tax_district_name": Field("base.tax_district_name"),
            "tax_year": Field("base.tax_year", "integer"),
            "authority_name": Field("base.authority_name"),
            "total": Field("base.total", "number"),
        },
        row_query_allowed=False,
    ),
    "plcb_licenses": Table(
        "staging.plcb_licenses",
        {
            "premises_name": Field("base.premises_name"),
            "premises_address": Field("base.premises_address"),
            "license_type": Field("base.license_type"),
            "status": Field("base.status"),
            "municipality": Field("base.municipality"),
        },
        projection=(
            "base.premises_name, base.premises_address, base.license_type, "
            "base.status, base.municipality, base.last_issue_date, "
            "base.expiration_date"
        ),
    ),
    "penndot_projects": Table(
        "staging.penndot_projects",
        {
            "project_name": Field("base.project_name"),
            "description": Field("base.description"),
            "status": Field("base.status"),
            "cost": Field("base.cost", "number"),
            "start_date": Field("base.start_date", "date"),
            "end_date": Field("base.end_date", "date"),
        },
    ),
    "penndot_roads": Table(
        "staging.penndot_roads",
        {
            "road_name": Field("base.road_name"),
            "road_class": Field("base.road_class"),
            "speed_limit": Field("base.speed_limit", "number"),
        },
    ),
    "municipalities": Table(
        "staging.municipalities",
        {
            "name": Field("base.name"),
            "muni_type": Field("base.muni_type"),
        },
    ),
    "zipcodes": Table(
        "staging.zipcodes",
        {
            "zipcode": Field("base.zipcode"),
            "po_name": Field("base.po_name"),
        },
    ),
}

_TEXT_OPERATORS = {"eq", "neq", "contains", "starts_with", "in"}
_ORDERED_OPERATORS = {"eq", "neq", "gt", "gte", "lt", "lte", "in"}
_COMPARISONS = {
    "eq": "=",
    "neq": "<>",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


def _table_for(plan: dict[str, Any]) -> tuple[str, Table]:
    table_key = plan.get("table")
    if not isinstance(table_key, str) or table_key not in TABLES:
        raise InvalidSearchPlan("unsupported table")
    return table_key, TABLES[table_key]


def _coerce_value(field: Field, value: object) -> object:
    if field.kind == "number":
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise InvalidSearchPlan("invalid numeric filter") from exc
    if field.kind == "integer":
        if isinstance(value, bool):
            raise InvalidSearchPlan("invalid integer filter")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise InvalidSearchPlan("invalid integer filter") from exc
    if field.kind == "date":
        text = str(value).strip()
        if len(text) != 10 or text[4] != "-" or text[7] != "-":
            raise InvalidSearchPlan("dates must use YYYY-MM-DD")
        return text

    text = str(value).strip()
    if not text or len(text) > 160 or any(ord(char) < 32 for char in text):
        raise InvalidSearchPlan("invalid text filter")
    return text


def _param(params: dict[str, object], value: object) -> str:
    name = f"p{len(params)}"
    params[name] = value
    return f"%({name})s"


def _compile_filters(
    plan: dict[str, Any], table: Table, params: dict[str, object]
) -> list[str]:
    raw_filters = plan.get("filters", [])
    if not isinstance(raw_filters, list) or len(raw_filters) > 12:
        raise InvalidSearchPlan("filters must be a list of at most 12 items")

    clauses: list[str] = []
    for raw_filter in raw_filters:
        if not isinstance(raw_filter, dict):
            raise InvalidSearchPlan("invalid filter")
        field_name = raw_filter.get("field")
        operator = raw_filter.get("op", "eq")
        if not isinstance(field_name, str) or field_name not in table.fields:
            raise InvalidSearchPlan("unsupported filter field")
        field = table.fields[field_name]
        allowed_operators = _TEXT_OPERATORS if field.kind == "text" else _ORDERED_OPERATORS
        if operator not in allowed_operators:
            raise InvalidSearchPlan("unsupported filter operator")
        value = raw_filter.get("value")

        if operator == "in":
            if not isinstance(value, list) or not 1 <= len(value) <= 20:
                raise InvalidSearchPlan("in filters require 1 to 20 values")
            placeholders = [
                _param(params, _coerce_value(field, item)) for item in value
            ]
            clauses.append(f"{field.expression} IN ({', '.join(placeholders)})")
            continue

        bound_value = _coerce_value(field, value)
        if operator == "contains":
            clauses.append(f"{field.expression} ILIKE {_param(params, f'%{bound_value}%')}")
        elif operator == "starts_with":
            clauses.append(f"{field.expression} ILIKE {_param(params, f'{bound_value}%')}")
        else:
            clauses.append(
                f"{field.expression} {_COMPARISONS[operator]} {_param(params, bound_value)}"
            )
    return clauses


def _compile_signals(
    plan: dict[str, Any], table_key: str, params: dict[str, object]
) -> list[str]:
    signals = plan.get("signals", [])
    if not isinstance(signals, list) or len(signals) > 4:
        raise InvalidSearchPlan("signals must be a list of at most four items")

    clauses: list[str] = []
    for signal in signals:
        if table_key != "parcels":
            raise InvalidSearchPlan("signals are only supported for parcels")
        if signal == "vacant":
            clauses.extend(
                [
                    "NOT EXISTS (SELECT 1 FROM staging.structures s "
                    "WHERE s.valid_to IS NULL AND s.geom IS NOT NULL "
                    "AND ST_Intersects(s.geom, base.geom))",
                    "(base.class NOT IN ('R') OR base.aprtotal IS NULL "
                    "OR base.aprtotal::numeric < 50000)",
                    "(base.price IS NULL OR base.price::numeric < 100000)",
                ]
            )
        elif signal == "tax_delinquent":
            clauses.append(
                "EXISTS (SELECT 1 FROM staging.tax_claims tc "
                "WHERE tc.valid_to IS NULL AND tc.total > 0 AND tc.pidn = base.pidn)"
            )
        elif signal == "flood_zone":
            clauses.append(
                "EXISTS (SELECT 1 FROM staging.flood_zones f "
                "WHERE f.valid_to IS NULL AND f.sfha_tf = 'T' "
                "AND ST_Intersects(f.geom, base.geom))"
            )
        elif signal == "recent_sale":
            years = plan.get("recent_sale_years", 1)
            if isinstance(years, bool):
                raise InvalidSearchPlan("invalid recent sale window")
            try:
                years = int(years)
            except (TypeError, ValueError) as exc:
                raise InvalidSearchPlan("invalid recent sale window") from exc
            if not 1 <= years <= 10:
                raise InvalidSearchPlan("recent sale window must be 1 to 10 years")
            placeholder = _param(params, years)
            clauses.append(
                "TO_DATE(base.saledt, 'DD-MON-YYYY') > "
                f"CURRENT_DATE - ({placeholder} * INTERVAL '1 year')"
            )
        else:
            raise InvalidSearchPlan("unsupported signal")
    return clauses


def _compile_location(
    plan: dict[str, Any], table_key: str, params: dict[str, object]
) -> list[str]:
    location = plan.get("location")
    if location is None:
        return []
    if not isinstance(location, dict):
        raise InvalidSearchPlan("invalid location")
    location_type = location.get("type")
    value = str(location.get("value", "")).strip()
    if not value or len(value) > 80:
        raise InvalidSearchPlan("invalid location value")

    if location_type == "zipcode":
        if len(value) != 5 or not value.isdigit():
            raise InvalidSearchPlan("invalid zipcode")
        placeholder = _param(params, value)
        if table_key == "parcels":
            return [
                "EXISTS (SELECT 1 FROM staging.zipcodes z "
                "WHERE z.valid_to IS NULL AND z.zipcode = "
                f"{placeholder} AND ST_Intersects(z.geom, base.geom))"
            ]
        if table_key == "plcb_licenses":
            params_name = _param(params, f"%{value}%")
            return [f"base.premises_address LIKE {params_name}"]
        raise InvalidSearchPlan("zipcode is not supported for this table")

    if location_type == "municipality":
        placeholder = _param(params, f"%{value.upper()}%")
        if table_key == "parcels":
            return [
                "EXISTS (SELECT 1 FROM staging.municipalities m "
                "WHERE m.valid_to IS NULL AND UPPER(m.name) LIKE "
                f"{placeholder} AND ST_Intersects(m.geom, base.geom))"
            ]
        if table_key == "plcb_licenses":
            return [f"UPPER(base.municipality) LIKE {placeholder}"]
        if table_key == "tax_claims":
            return [f"UPPER(base.tax_district_name) LIKE {placeholder}"]
        raise InvalidSearchPlan("municipality is not supported for this table")

    raise InvalidSearchPlan("unsupported location type")


def _compile_where(
    plan: dict[str, Any], table_key: str, table: Table, params: dict[str, object]
) -> str:
    clauses = ["base.valid_to IS NULL"]
    clauses.extend(_compile_filters(plan, table, params))
    clauses.extend(_compile_signals(plan, table_key, params))
    clauses.extend(_compile_location(plan, table_key, params))
    return " AND ".join(f"({clause})" for clause in clauses)


def _compile_order(plan: dict[str, Any], table: Table) -> str:
    raw_sort = plan.get("sort", [])
    if isinstance(raw_sort, dict):
        raw_sort = [raw_sort]
    if not isinstance(raw_sort, list) or len(raw_sort) > 3:
        raise InvalidSearchPlan("sort must contain at most three fields")

    order: list[str] = []
    for item in raw_sort:
        if not isinstance(item, dict):
            raise InvalidSearchPlan("invalid sort")
        field_name = item.get("field")
        direction = str(item.get("direction", "asc")).lower()
        if not isinstance(field_name, str) or field_name not in table.fields:
            raise InvalidSearchPlan("unsupported sort field")
        if direction not in {"asc", "desc"}:
            raise InvalidSearchPlan("unsupported sort direction")
        order.append(f"{table.fields[field_name].expression} {direction.upper()}")
    return ", ".join(order)


def compile_query(plan: dict[str, Any], max_limit: int) -> CompiledSearch:
    """Compile a row-returning search plan."""
    if any(key.startswith("sql_") for key in plan):
        raise InvalidSearchPlan("raw SQL fields are not accepted")
    table_key, table = _table_for(plan)
    if not table.row_query_allowed:
        raise InvalidSearchPlan("row queries are not allowed for this table")
    params: dict[str, object] = {}
    where = _compile_where(plan, table_key, table, params)
    order = _compile_order(plan, table)
    try:
        requested_limit = int(plan.get("limit", max_limit))
    except (TypeError, ValueError) as exc:
        raise InvalidSearchPlan("invalid result limit") from exc
    result_limit = max(1, min(requested_limit, max_limit, 100))

    query = f"SELECT {table.projection} FROM {table.fqn} AS base WHERE {where}"
    if order:
        query += f" ORDER BY {order}"
    query += f" LIMIT {result_limit}"
    return CompiledSearch(query, params, table_key)


def compile_aggregate(plan: dict[str, Any]) -> CompiledSearch:
    """Compile a numeric aggregate search plan."""
    if any(key.startswith("sql_") for key in plan):
        raise InvalidSearchPlan("raw SQL fields are not accepted")
    table_key, table = _table_for(plan)
    aggregate = plan.get("aggregate")
    if not isinstance(aggregate, dict):
        raise InvalidSearchPlan("aggregate definition is required")
    operation = aggregate.get("operation")
    field_name = aggregate.get("field")

    if operation == "count":
        expression = "COUNT(*)"
    elif operation == "count_distinct":
        if not isinstance(field_name, str) or field_name not in table.fields:
            raise InvalidSearchPlan("count_distinct requires an allowlisted field")
        expression = f"COUNT(DISTINCT {table.fields[field_name].expression})"
    elif operation in {"sum", "avg", "min", "max"}:
        if not isinstance(field_name, str) or field_name not in table.fields:
            raise InvalidSearchPlan("aggregate requires an allowlisted field")
        field = table.fields[field_name]
        if field.kind not in {"number", "integer"}:
            raise InvalidSearchPlan("numeric aggregate requires a numeric field")
        expression = f"{operation.upper()}({field.expression})"
    else:
        raise InvalidSearchPlan("unsupported aggregate operation")

    params: dict[str, object] = {}
    where = _compile_where(plan, table_key, table, params)
    query = f"SELECT {expression} AS result FROM {table.fqn} AS base WHERE {where}"
    return CompiledSearch(query, params, table_key)
