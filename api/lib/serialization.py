"""Helpers for serializing DB-native types into API wire shapes."""

from __future__ import annotations

from datetime import date, datetime


def isoformat_or_none(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def serialize_temporal_fields(record: dict, *keys: str) -> dict:
    for key in keys:
        record[key] = isoformat_or_none(record.get(key))
    return record
