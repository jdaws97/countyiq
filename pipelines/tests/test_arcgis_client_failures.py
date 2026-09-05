"""Failure-path tests for the parallel ArcGIS client.

A partial fetch must never be returned: downstream SCD2 loaders treat
missing rows as deletions and expire them, so a 60% fetch silently wipes
40% of the county. These tests pin the raise-on-partial behavior and the
per-page retry logic.
"""

from unittest import mock

import pytest
import requests

from countyiq.lib import arcgis_client


def _resp(json_data, status=200):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = json_data
    if status >= 400:
        err = requests.exceptions.HTTPError(response=r)
        r.raise_for_status.side_effect = err
    else:
        r.raise_for_status.return_value = None
    return r


def test_bounded_parallel_iterator_limits_submitted_page_window():
    with mock.patch.object(arcgis_client, "_get_feature_count", return_value=5), \
         mock.patch.object(arcgis_client, "_fetch_page") as fetch_page:
        fetch_page.side_effect = lambda u, w, f, s, b, offset, g: [
            {"attributes": {"offset": offset}}
        ]
        pages = arcgis_client.iterate_feature_pages_parallel(
            "http://x/FeatureServer/0", batch_size=1, max_workers=2,
        )

        first_page = next(pages)
        assert fetch_page.call_count <= 2
        remaining_pages = list(pages)

    returned_offsets = {
        feature["attributes"]["offset"]
        for page in [first_page, *remaining_pages]
        for feature in page
    }
    assert returned_offsets == {0, 1, 2, 3, 4}


def test_bounded_parallel_iterator_raises_on_partial_fetch():
    with mock.patch.object(arcgis_client, "_get_feature_count", return_value=2), \
         mock.patch.object(arcgis_client, "_fetch_page") as fetch_page:
        def side_effect(url, where, out_fields, out_sr, batch_size, offset, return_geometry):
            if offset == 1:
                raise RuntimeError("boom")
            return [{"attributes": {"offset": offset}}]

        fetch_page.side_effect = side_effect
        pages = arcgis_client.iterate_feature_pages_parallel(
            "http://x/FeatureServer/0", batch_size=1, max_workers=2,
        )
        with pytest.raises(RuntimeError, match="Refusing to yield a successful partial result"):
            list(pages)


def test_fetch_page_retries_transient_then_succeeds():
    good = _resp({"features": [{"attributes": {}}]})
    with mock.patch.object(arcgis_client.requests, "get",
                           side_effect=[requests.exceptions.Timeout(), good]), \
         mock.patch.object(arcgis_client.time, "sleep"):
        features = arcgis_client._fetch_page("http://x", "1=1", "*", 4326, 1000, 0, True)
    assert len(features) == 1


def test_fetch_page_gives_up_after_retries():
    with mock.patch.object(arcgis_client.requests, "get",
                           side_effect=requests.exceptions.ConnectionError()), \
         mock.patch.object(arcgis_client.time, "sleep"):
        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            arcgis_client._fetch_page("http://x", "1=1", "*", 4326, 1000, 0, True)


def test_fetch_page_4xx_raises_immediately():
    with mock.patch.object(arcgis_client.requests, "get", return_value=_resp({}, status=404)) as get:
        with pytest.raises(requests.exceptions.HTTPError):
            arcgis_client._fetch_page("http://x", "1=1", "*", 4326, 1000, 0, True)
    assert get.call_count == 1
