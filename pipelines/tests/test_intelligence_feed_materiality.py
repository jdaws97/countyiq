"""Regression coverage for public-feed delinquency materiality."""

from countyiq.assets.enrichment.intelligence_events import _DELINQUENCY_EVENTS_SQL


def test_delinquency_event_sql_excludes_routine_interest_accrual():
    assert "t.old_total = 0" in _DELINQUENCY_EVENTS_SQL
    assert "t.new_total = 0" in _DELINQUENCY_EVENTS_SQL
    assert "GREATEST(100::numeric, ABS(t.old_total) * 0.10)" in _DELINQUENCY_EVENTS_SQL
