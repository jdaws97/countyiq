"""Shared HTTP retry helper — transient statuses + network errors."""

from unittest import mock

import pytest
import requests

from countyiq.lib import http_retry
from countyiq.lib.http_retry import get_with_retry


def _resp(status, content=b"ok"):
    r = mock.Mock()
    r.status_code = status
    r.content = content
    r.headers = {}
    r.raise_for_status.side_effect = (
        requests.exceptions.HTTPError(f"{status}") if status >= 400 else None
    )
    return r


def test_transient_404_then_success():
    calls = [_resp(404), _resp(200, b"pdf")]
    with (
        mock.patch.object(http_retry.requests, "get", side_effect=calls),
        mock.patch.object(http_retry.time, "sleep"),
    ):
        resp = get_with_retry("http://x", retries=3)
    assert resp.content == b"pdf"


def test_non_transient_403_raises_immediately():
    get = mock.Mock(return_value=_resp(403))
    with (
        mock.patch.object(http_retry.requests, "get", get),
        mock.patch.object(http_retry.time, "sleep"),
    ):
        with pytest.raises(requests.exceptions.HTTPError):
            get_with_retry("http://x", retries=4)
    assert get.call_count == 1


def test_network_error_retried_then_raises():
    get = mock.Mock(side_effect=requests.exceptions.ConnectionError())
    with (
        mock.patch.object(http_retry.requests, "get", get),
        mock.patch.object(http_retry.time, "sleep"),
    ):
        with pytest.raises(requests.exceptions.ConnectionError):
            get_with_retry("http://x", retries=3)
    assert get.call_count == 3


def test_retry_after_header_honored():
    calls = [_resp(429), _resp(200)]
    calls[0].headers = {"Retry-After": "7"}
    slept = []
    with (
        mock.patch.object(http_retry.requests, "get", side_effect=calls),
        mock.patch.object(
            http_retry.time, "sleep", side_effect=lambda s: slept.append(s)
        ),
    ):
        get_with_retry("http://x", retries=3)
    assert slept == [7.0]
