from datetime import UTC, datetime, timedelta

from api.lib.source_refresh import source_refresh_run
from api.routes.ops import _apply_run_health


def refresh(status="success", *, days_ago=0, success_days_ago=0):
    now = datetime(2026, 10, 3, 12, tzinfo=UTC)
    return {
        "job_name": "radar_refresh",
        "status": status,
        "started_at": None,
        "finished_at": now - timedelta(days=days_ago),
        "last_success_at": now - timedelta(days=success_days_ago),
    }


def test_composite_source_freshness_uses_oldest_contributor():
    runs = {
        "business_parks_arcgis": refresh(),
        "industrial_parks_arcgis": refresh(days_ago=10, success_days_ago=10),
    }
    combined = source_refresh_run("economic_development_parks", runs)
    source = _apply_run_health(
        {"status": "green", "record_count": 504},
        job_name="radar_refresh",
        max_age_hours=192,
        run=combined,
        now=datetime(2026, 10, 3, 12, tzinfo=UTC),
    )
    assert source["status_reason"] == "stale"
    assert (
        source["last_success_at"] == runs["industrial_parks_arcgis"]["last_success_at"]
    )


def test_missing_contributor_does_not_establish_composite_success():
    assert (
        source_refresh_run(
            "economic_development_parks", {"business_parks_arcgis": refresh()}
        )
        is None
    )


def test_failure_is_not_hidden_by_later_success_of_another_contributor():
    runs = {
        "business_parks_arcgis": refresh(),
        "industrial_parks_arcgis": refresh("failure", days_ago=1, success_days_ago=7),
    }
    assert source_refresh_run("economic_development_parks", runs)["status"] == "failure"


def test_unrelated_failed_asset_does_not_change_successful_source():
    runs = {
        "plcb_licenses": refresh(),
        "tax_claims": refresh("failure", success_days_ago=30),
    }
    assert source_refresh_run("plcb_licenses", runs)["status"] == "success"
