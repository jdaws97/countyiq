"""Radar movers endpoint, compact list payloads, and the new signal labels."""

from contextlib import contextmanager

from api.lib.development_radar import (
    build_reason_signals,
    compact_signals_for_list,
    format_signal_label,
)
from api.routes import radar


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.executions = []

    def execute(self, sql, params=None):
        self.executions.append((sql, params))

    def fetchall(self):
        return self.rows if len(self.executions) == 1 else []

    def fetchone(self):
        return {"previous_computed_at": None}


def _cursor_context(cursor):
    @contextmanager
    def _ctx():
        yield cursor

    return _ctx


def test_new_signal_labels_say_where_the_plan_is():
    on_parcel = {"distance_m": 0, "evidence": {"plan_title": "Ridge Estates", "plan_location": "point_on_parcel"}}
    nearby = {"distance_m": 142.4, "evidence": {"plan_title": "Ridge Estates"}}
    assert format_signal_label("active_subdivision", on_parcel) == "Plan point mapped on parcel: Ridge Estates"
    assert format_signal_label("nearby_subdivision", nearby) == "Plan 142 m away: Ridge Estates"
    assert format_signal_label(
        "municipal_action",
        {"evidence": {"extraction_type": "rezoning_application", "decision": "approved"}},
    ) == "Municipal rezoning application linked by record (approved)"
    assert format_signal_label(
        "entity_assemblage", {"evidence": {"contiguous_same_owner_parcels": 3}}
    ) == "Same recorded owner holds 3 touching parcels after a recent acquisition"


def test_reason_signals_rank_municipal_action_above_context():
    signals = {
        "growth_area": {"weight": 0.02, "evidence": {"ga_type": "PGA"}},
        "municipal_action": {"weight": 0.14, "evidence": {"extraction_type": "variance_request"}},
        "flood_zone": {"weight": -0.1, "evidence": {"fld_zone": "AE"}},
    }
    reasons = build_reason_signals(signals, limit=4)
    assert [r["key"] for r in reasons] == ["municipal_action", "growth_area", "flood_zone"]
    assert reasons[0]["is_direct"] is True
    assert reasons[2]["is_risk"] is True


def test_compact_signals_drop_prose_but_keep_evidence():
    signals = {
        "vacancy": {
            "weight": 0.12,
            "evidence": {"structure_count": 0},
            "validation_reasoning": "long prose",
            "cross_references": ["signal:vacancy"],
            "claim": "vacancy classified confirmed",
            "internal_url": "/property/1",
            "validation_status": "confirmed",
        }
    }
    compact = compact_signals_for_list(signals)
    assert compact == {
        "vacancy": {
            "weight": 0.12,
            "evidence": {"structure_count": 0},
            "validation_status": "confirmed",
        }
    }


def test_movers_orders_by_delta_and_exposes_previous_snapshot(monkeypatch):
    rows = [
        {
            "pidn": "1",
            "score": 40,
            "opportunity_score": 55,
            "site_readiness_score": 60,
            "top_signal": "No mapped building footprint; low-value screen",
            "signal_count": 2,
            "signals": {"vacancy": {"weight": 0.12, "evidence": {}}},
            "eligible": True,
            "has_active_plan": False,
            "score_version": 7,
            "computed_at": None,
            "previous_score": 40,
            "previous_opportunity_score": 30,
            "score_delta": 0,
            "opportunity_delta": 25,
            "previous_computed_at": None,
            "is_new": False,
            "owner_full": None,
            "propadr": "1 MAIN ST",
            "municipality": "TEST TWP",
            "acres": 2.5,
            "aprtotal": 10000,
            "class": "R",
        }
    ]
    cursor = _Cursor(rows)
    monkeypatch.setattr(radar, "get_cursor", _cursor_context(cursor))
    monkeypatch.setattr(radar, "_require_radar_sources", lambda _cur, **_kw: None)
    monkeypatch.setattr(radar, "source_use_allowed", lambda *_args, **_kw: False)

    response = radar.radar_movers(
        view="opportunity",
        direction="up",
        municipality="TEST TWP",
        min_delta=5,
        min_score=0,
        limit=10,
        offset=0,
    )

    sql, params = cursor.executions[0]
    assert "dm.opportunity_delta >= %(min_delta)s" in sql
    assert "ORDER BY dm.opportunity_delta DESC" in sql
    assert "dm.has_active_plan = FALSE" in sql
    assert params["municipality"] == "TEST TWP"
    assert response["direction"] == "up"
    parcel = response["parcels"][0]
    assert parcel["score"] == 55  # opportunity view reports the opportunity score
    assert parcel["opportunity_delta"] == 25
    assert parcel["is_new"] is False
    assert parcel["reason_signals"][0]["key"] == "vacancy"


def test_list_views_accept_acreage_and_class_filters(monkeypatch):
    cursor = _Cursor([])
    monkeypatch.setattr(radar, "get_cursor", _cursor_context(cursor))
    monkeypatch.setattr(radar, "_require_radar_sources", lambda _cur, **_kw: None)
    monkeypatch.setattr(radar, "source_use_allowed", lambda *_args, **_kw: False)

    radar.opportunity_scores(
        min_score=30,
        municipality=None,
        min_acres=5,
        max_acres=None,
        parcel_class="r, i, bogus",
        limit=10,
        offset=0,
    )
    sql, params = cursor.executions[0]
    assert "p.acres >= %(min_acres)s" in sql
    assert "UPPER(p.class) = ANY(%(parcel_classes)s)" in sql
    assert params["parcel_classes"] == ["R", "I"]
    assert "dm.opportunity_score >= %(min_score)s" in sql
