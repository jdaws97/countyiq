"""FEMA pagination termination tests."""

from unittest.mock import Mock

import pytest
import requests

from countyiq.assets.bulk import fema_flood


def test_empty_page_terminates_even_when_server_retains_transfer_flag(monkeypatch):
    fetch_page = Mock(
        side_effect=[
            {
                "features": [{"attributes": {"FLD_AR_ID": "one"}}],
                "exceededTransferLimit": True,
            },
            {"features": [], "exceededTransferLimit": True},
        ]
    )
    monkeypatch.setattr(fema_flood, "_fetch_page", fetch_page)
    context = Mock()

    result = fema_flood._fetch_all_pages("https://example.test", 28, "42133C", context)

    assert len(result["features"]) == 1
    assert fetch_page.call_count == 2


def test_final_nonempty_page_terminates_when_transfer_flag_clears(monkeypatch):
    fetch_page = Mock(
        return_value={
            "features": [{"attributes": {"FLD_AR_ID": "one"}}],
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
