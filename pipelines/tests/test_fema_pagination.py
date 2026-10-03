"""FEMA pagination termination tests."""

from unittest.mock import Mock

import pytest
import requests

from countyiq.assets.bulk import fema_flood


def feature(identifier, dfirm_id="42133C"):
    return {"attributes": {"FLD_AR_ID": identifier, "DFIRM_ID": dfirm_id}}


def test_verified_count_terminates_even_when_server_retains_transfer_flag(monkeypatch):
    monkeypatch.setattr(fema_flood, "_get_feature_count", Mock(return_value=1))
    fetch_page = Mock(
        side_effect=[
            {
                "features": [feature("one")],
                "exceededTransferLimit": True,
            },
            {"features": [], "exceededTransferLimit": True},
        ]
    )
    monkeypatch.setattr(fema_flood, "_fetch_page", fetch_page)
    context = Mock()

    result = fema_flood._fetch_all_pages("https://example.test", 28, "42133C", context)

    assert len(result["features"]) == 1
    assert fetch_page.call_count == 1


def test_final_nonempty_page_terminates_when_transfer_flag_clears(monkeypatch):
    monkeypatch.setattr(fema_flood, "_get_feature_count", Mock(return_value=1))
    fetch_page = Mock(
        return_value={
            "features": [feature("one")],
            "exceededTransferLimit": False,
        }
    )
    monkeypatch.setattr(fema_flood, "_fetch_page", fetch_page)

    result = fema_flood._fetch_all_pages("https://example.test", 28, "42133C", Mock())

    assert len(result["features"]) == 1
    assert fetch_page.call_count == 1


def test_page_fetch_retries_connection_reset_then_succeeds(monkeypatch):
    response = Mock()
    response.json.return_value = {"features": []}
    get = Mock(
        side_effect=[
            requests.exceptions.ConnectionError("connection reset"),
            response,
        ]
    )
    sleep = Mock()
    monkeypatch.setattr(fema_flood.requests, "get", get)
    monkeypatch.setattr(fema_flood.time, "sleep", sleep)

    assert fema_flood._fetch_page("https://example.test") == {"features": []}
    assert get.call_count == 2
    sleep.assert_called_once_with(fema_flood.RETRY_BACKOFF)


def test_page_fetch_does_not_retry_non_retryable_4xx(monkeypatch):
    response = Mock(status_code=404)
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        "not found", response=response
    )
    get = Mock(return_value=response)
    sleep = Mock()
    monkeypatch.setattr(fema_flood.requests, "get", get)
    monkeypatch.setattr(fema_flood.time, "sleep", sleep)

    with pytest.raises(requests.exceptions.HTTPError):
        fema_flood._fetch_page("https://example.test")
    assert get.call_count == 1
    sleep.assert_not_called()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (None, "invalid page response"),
        ([], "invalid page response"),
        ({"error": {"code": 500, "message": "query failed"}}, "ArcGIS service error"),
        ({}, "missing its feature list"),
        ({"features": None}, "missing its feature list"),
        ({"features": {}}, "missing its feature list"),
    ],
)
def test_http_success_cannot_hide_service_errors_or_invalid_pages(
    monkeypatch, payload, message
):
    response = Mock()
    response.json.return_value = payload
    get = Mock(return_value=response)
    monkeypatch.setattr(fema_flood.requests, "get", get)

    with pytest.raises(RuntimeError, match=message):
        fema_flood._fetch_page("https://example.test")
    get.assert_called_once()


def test_empty_county_response_cannot_be_reported_as_a_successful_refresh(monkeypatch):
    monkeypatch.setattr(fema_flood, "_get_feature_count", Mock(return_value=0))
    fetch_page = Mock(return_value={"features": [], "exceededTransferLimit": False})
    monkeypatch.setattr(fema_flood, "_fetch_page", fetch_page)

    with pytest.raises(RuntimeError, match="no flood hazard features"):
        fema_flood._fetch_all_pages("https://example.test", 28, "42133C", Mock())
    fetch_page.assert_not_called()


def test_error_on_a_later_page_does_not_publish_a_partial_county(monkeypatch):
    monkeypatch.setattr(fema_flood, "_get_feature_count", Mock(return_value=2))
    monkeypatch.setattr(fema_flood, "PAGE_SIZE", 1)
    first = Mock()
    first.json.return_value = {
        "features": [feature("one")],
        "exceededTransferLimit": True,
    }
    failed = Mock()
    failed.json.return_value = {"error": {"code": 500, "message": "query failed"}}
    get = Mock(side_effect=[first, failed])
    monkeypatch.setattr(fema_flood.requests, "get", get)

    with pytest.raises(RuntimeError, match="ArcGIS service error"):
        fema_flood._fetch_all_pages("https://example.test", 28, "42133C", Mock())
    assert get.call_count == 2


def test_server_query_failure_retries_the_same_offset_with_a_smaller_page(monkeypatch):
    monkeypatch.setattr(fema_flood, "_get_feature_count", Mock(return_value=2))
    monkeypatch.setattr(fema_flood, "PAGE_SIZE", 2)
    fetch_page = Mock(
        side_effect=[
            fema_flood.FemaQueryError("query too large"),
            {"features": [feature("one")]},
            {"features": [feature("two")]},
        ]
    )
    monkeypatch.setattr(fema_flood, "_fetch_page", fetch_page)
    result = fema_flood._fetch_all_pages("https://example.test", 28, "42133C", Mock())
    assert len(result["features"]) == 2
    urls = [call.args[0] for call in fetch_page.call_args_list]
    assert "resultOffset=0" in urls[0] and "resultRecordCount=2" in urls[0]
    assert "resultOffset=0" in urls[1] and "resultRecordCount=1" in urls[1]
    assert "resultOffset=1" in urls[2]


def test_repeated_small_pages_cannot_exceed_request_budget(monkeypatch):
    monkeypatch.setattr(fema_flood, "_get_feature_count", Mock(return_value=10))
    monkeypatch.setattr(fema_flood, "MAX_PAGE_REQUESTS", 2)
    fetch_page = Mock(return_value={"features": [feature("one")]})
    monkeypatch.setattr(fema_flood, "_fetch_page", fetch_page)
    with pytest.raises(RuntimeError, match="bounded pagination request limit"):
        fema_flood._fetch_all_pages("https://example.test", 28, "42133C", Mock())
    assert fetch_page.call_count == 2


def test_premature_transfer_flag_does_not_truncate_the_snapshot(monkeypatch):
    monkeypatch.setattr(fema_flood, "_get_feature_count", Mock(return_value=2))
    fetch_page = Mock(
        side_effect=[
            {"features": [feature("one")]},
            {"features": [feature("two")]},
        ]
    )
    monkeypatch.setattr(fema_flood, "_fetch_page", fetch_page)
    result = fema_flood._fetch_all_pages("https://example.test", 28, "42133C", Mock())
    assert len(result["features"]) == 2
    assert "resultOffset=1" in fetch_page.call_args.args[0]


def test_empty_page_before_verified_count_rejects_partial_snapshot(monkeypatch):
    monkeypatch.setattr(fema_flood, "_get_feature_count", Mock(return_value=2))
    monkeypatch.setattr(
        fema_flood,
        "_fetch_page",
        Mock(
            side_effect=[
                {"features": [feature("one")]},
                {"features": [], "exceededTransferLimit": False},
            ]
        ),
    )
    with pytest.raises(RuntimeError, match="1 of 2 expected"):
        fema_flood._fetch_all_pages("https://example.test", 28, "42133C", Mock())


@pytest.mark.parametrize("identifiers", [["one", "one"], ["one", None]])
def test_matching_count_cannot_hide_duplicate_or_missing_identifiers(
    monkeypatch, identifiers
):
    monkeypatch.setattr(fema_flood, "_get_feature_count", Mock(return_value=2))
    monkeypatch.setattr(
        fema_flood,
        "_fetch_page",
        Mock(return_value={"features": [feature(value) for value in identifiers]}),
    )
    with pytest.raises(RuntimeError, match="missing or"):
        fema_flood._fetch_all_pages("https://example.test", 28, "42133C", Mock())


@pytest.mark.parametrize(
    "features",
    [
        [feature("one"), feature("two"), feature("three")],
        [feature("one", "99999C"), feature("two")],
        [feature("one"), feature(" ")],
        [feature("one"), {"attributes": None}],
    ],
)
def test_count_growth_wrong_county_or_malformed_features_cannot_publish(
    monkeypatch, features
):
    monkeypatch.setattr(fema_flood, "_get_feature_count", Mock(return_value=2))
    monkeypatch.setattr(
        fema_flood, "_fetch_page", Mock(return_value={"features": features})
    )
    with pytest.raises(RuntimeError):
        fema_flood._fetch_all_pages("https://example.test", 28, "42133C", Mock())


@pytest.mark.parametrize("failure", ["later_page_error", "missing_geometry"])
def test_incomplete_snapshot_never_reaches_the_staging_upsert(monkeypatch, failure):
    monkeypatch.setattr(fema_flood, "authorize_source", Mock())
    monkeypatch.setattr(fema_flood, "require_source_use", Mock())
    fetch = (
        Mock(side_effect=RuntimeError("later page failed"))
        if failure == "later_page_error"
        else Mock(return_value={"features": [feature("one")]})
    )
    monkeypatch.setattr(fema_flood, "_fetch_all_pages", fetch)
    upsert = Mock()
    monkeypatch.setattr(fema_flood, "scd2_upsert_geom", upsert)
    database = Mock()
    storage = Mock()
    execute = fema_flood.fema_flood_zones.op.compute_fn.decorated_fn

    with pytest.raises(RuntimeError):
        execute(Mock(), database, storage)

    upsert.assert_not_called()
    database.cursor.assert_not_called()
