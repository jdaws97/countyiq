"""Real Dagster event contracts for source freshness in partially failed jobs."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from dagster import DagsterInstance, MaterializeResult, asset, materialize

from countyiq.lib.asset_refresh_status import collect_asset_refresh_outcomes
from countyiq.sensors.alerting import _record_outcome


def test_successful_source_does_not_inherit_sibling_failure():
    @asset
    def plcb_licenses():
        return MaterializeResult(metadata={"record_count": 1369})

    @asset
    def tax_claims():
        raise RuntimeError("Source download unavailable")

    @asset
    def unrelated_analysis():
        return MaterializeResult(metadata={"record_count": 10})

    with DagsterInstance.ephemeral() as instance:
        result = materialize(
            [plcb_licenses, tax_claims, unrelated_analysis],
            instance=instance,
            raise_on_error=False,
        )
        assert result.success is False
        run = instance.get_run_by_id(result.run_id)
        outcomes = collect_asset_refresh_outcomes(instance, run)
        database = Mock()
        _record_outcome(
            SimpleNamespace(instance=instance, dagster_run=run), database, "failure"
        )

    writes = [call.args[1] for call in database.execute.call_args_list]
    assert writes[0]["status"] == "failure"
    assert {item["asset_key"]: item["status"] for item in writes[1:]} == {
        "plcb_licenses": "success",
        "tax_claims": "failure",
    }

    by_asset = {outcome.asset_key: outcome for outcome in outcomes}
    assert by_asset["plcb_licenses"].status == "success"
    assert by_asset["plcb_licenses"].record_count == 1369
    assert by_asset["tax_claims"].status == "failure"
    assert by_asset["tax_claims"].failure_reason == "step_failed"
    assert by_asset["tax_claims"].record_count is None
    assert set(by_asset) == {"plcb_licenses", "tax_claims"}


@pytest.mark.parametrize(
    ("metadata", "reason"),
    [
        ({"record_count": 0}, "empty_result"),
        ({}, "unverified_result"),
        ({"record_count": -1}, "unverified_result"),
        ({"record_count": "4000"}, "unverified_result"),
    ],
)
def test_materialization_without_verified_rows_cannot_refresh_freshness(
    metadata, reason
):
    @asset
    def fema_flood_zones():
        return MaterializeResult(metadata=metadata)

    with DagsterInstance.ephemeral() as instance:
        result = materialize([fema_flood_zones], instance=instance)
        run = instance.get_run_by_id(result.run_id)
        outcomes = collect_asset_refresh_outcomes(instance, run)

    assert result.success is True
    assert len(outcomes) == 1
    assert outcomes[0].status == "failure"
    assert outcomes[0].failure_reason == reason
    assert outcomes[0].finished_at <= datetime.now(UTC)


def test_environmental_snapshot_requires_both_component_counts():
    @asset
    def pa_dep_environmental_diligence():
        return MaterializeResult(
            metadata={"storage_tank_count": 100, "cleanup_site_count": 12}
        )

    with DagsterInstance.ephemeral() as instance:
        result = materialize([pa_dep_environmental_diligence], instance=instance)
        run = instance.get_run_by_id(result.run_id)
        outcomes = collect_asset_refresh_outcomes(instance, run)

    assert len(outcomes) == 1
    assert outcomes[0].status == "success"
    assert outcomes[0].record_count == 112
