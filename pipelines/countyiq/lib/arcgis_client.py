"""ArcGIS REST API client with automatic pagination.

Handles FeatureServer and MapServer endpoints. Paginates using
resultRecordCount + resultOffset until all records are fetched.

Supports both sequential (iterate_feature_pages) and parallel
(fetch_all_features_parallel) fetching. The parallel fetcher uses
ThreadPoolExecutor for ~5-8x speedup on large layers.
"""

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dagster import get_dagster_logger

DEFAULT_BATCH_SIZE = 2000
REQUEST_TIMEOUT = 60


def iterate_feature_pages(
    url: str,
    where: str = "1=1",
    out_fields: str = "*",
    out_sr: int = 4326,
    batch_size: int = DEFAULT_BATCH_SIZE,
    return_geometry: bool = True,
    delay: float = 0.5,
) -> Iterator[list[dict]]:
    """Yield ArcGIS feature pages one request at a time.

    This lets large layers be streamed into downstream loaders without
    materializing every feature in memory first.
    """
    log = get_dagster_logger()
    offset = 0
    total = 0

    while True:
        params = {
            "where": where,
            "outFields": out_fields,
            "outSR": out_sr,
            "f": "json",
            "resultRecordCount": batch_size,
            "resultOffset": offset,
            "returnGeometry": str(return_geometry).lower(),
        }

        resp = requests.get(f"{url}/query", params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"ArcGIS API error: {data['error']}")

        features = data.get("features", [])
        total += len(features)
        log.info(f"Fetched {len(features)} features (offset={offset}, total={total})")
        yield features

        # ArcGIS sets exceededTransferLimit when there are more records
        if not data.get("exceededTransferLimit", False) or len(features) == 0:
            break

        offset += len(features)
        time.sleep(delay)

    log.info(f"Finished: {total} total features from {url}")


def query_all_features(
    url: str,
    where: str = "1=1",
    out_fields: str = "*",
    out_sr: int = 4326,
    batch_size: int = DEFAULT_BATCH_SIZE,
    return_geometry: bool = True,
    delay: float = 0.5,
) -> list[dict]:
    """Fetch all features from an ArcGIS REST API endpoint with pagination.

    Args:
        url: FeatureServer or MapServer layer URL (e.g. .../FeatureServer/0)
        where: SQL WHERE clause (default "1=1" for all records)
        out_fields: Fields to return (default "*" for all)
        out_sr: Output spatial reference (default 4326/WGS84)
        batch_size: Records per request (ArcGIS caps at server maxRecordCount)
        return_geometry: Whether to include geometry in response
        delay: Seconds between requests (polite scraping)

    Returns:
        List of feature dicts, each with 'attributes' and optionally 'geometry' keys.
    """
    all_features = []
    for features in iterate_feature_pages(
        url=url,
        where=where,
        out_fields=out_fields,
        out_sr=out_sr,
        batch_size=batch_size,
        return_geometry=return_geometry,
        delay=delay,
    ):
        all_features.extend(features)
    return all_features


def _get_feature_count(url: str, where: str = "1=1") -> int:
    """Query the total feature count from an ArcGIS endpoint."""
    params = {"where": where, "returnCountOnly": "true", "f": "json"}
    resp = requests.get(f"{url}/query", params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("count", 0)


def _fetch_page(url: str, where: str, out_fields: str, out_sr: int,
                batch_size: int, offset: int, return_geometry: bool) -> list[dict]:
    """Fetch a single page — called by the thread pool workers."""
    params = {
        "where": where,
        "outFields": out_fields,
        "outSR": out_sr,
        "f": "json",
        "resultRecordCount": batch_size,
        "resultOffset": offset,
        "returnGeometry": str(return_geometry).lower(),
    }
    resp = requests.get(f"{url}/query", params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"ArcGIS API error at offset {offset}: {data['error']}")
    return data.get("features", [])


def fetch_all_features_parallel(
    url: str,
    where: str = "1=1",
    out_fields: str = "*",
    out_sr: int = 4326,
    batch_size: int = DEFAULT_BATCH_SIZE,
    return_geometry: bool = True,
    max_workers: int = 8,
) -> list[dict]:
    """Fetch all features using parallel HTTP requests.

    ~5-8x faster than sequential iterate_feature_pages for large layers.
    Fetches all pages concurrently using a thread pool, then returns
    features in offset order.

    Args:
        url: ArcGIS FeatureServer/MapServer layer URL.
        where: SQL WHERE clause.
        out_fields: Fields to return.
        out_sr: Output spatial reference.
        batch_size: Records per page.
        return_geometry: Include geometry in response.
        max_workers: Number of concurrent HTTP requests.

    Returns:
        List of all feature dicts, ordered by offset.
    """
    log = get_dagster_logger()

    # Get total count first
    total = _get_feature_count(url, where)
    log.info(f"Total features to fetch: {total:,} ({(total + batch_size - 1) // batch_size} pages)")

    if total == 0:
        return []

    offsets = list(range(0, total, batch_size))
    results_by_offset: dict[int, list[dict]] = {}
    errors = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _fetch_page, url, where, out_fields, out_sr,
                batch_size, offset, return_geometry,
            ): offset
            for offset in offsets
        }

        completed = 0
        for future in as_completed(futures):
            offset = futures[future]
            completed += 1
            try:
                features = future.result()
                results_by_offset[offset] = features
                if completed % 10 == 0 or completed == len(futures):
                    total_so_far = sum(len(v) for v in results_by_offset.values())
                    log.info(f"  Pages fetched: {completed}/{len(futures)} ({total_so_far:,} features)")
            except Exception as exc:
                log.warning(f"  Page at offset {offset} failed: {exc}")
                errors += 1

    # Reassemble in order
    all_features = []
    for offset in sorted(results_by_offset.keys()):
        all_features.extend(results_by_offset[offset])

    log.info(f"Parallel fetch complete: {len(all_features):,} features, {errors} page errors")
    return all_features
