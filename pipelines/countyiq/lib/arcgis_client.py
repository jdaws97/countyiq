"""ArcGIS REST API client with automatic pagination.

Handles FeatureServer and MapServer endpoints. Paginates using
resultRecordCount + resultOffset until all records are fetched.

Supports sequential, bounded-parallel streaming, and buffered-parallel
fetching. The parallel fetchers use ThreadPoolExecutor for ~5-8x speedup on
large layers.
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
    extra_params: dict[str, object] | None = None,
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
        if extra_params:
            params.update(extra_params)

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
    extra_params: dict[str, object] | None = None,
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
        extra_params=extra_params,
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
                batch_size: int, offset: int, return_geometry: bool,
                retries: int = 3) -> list[dict]:
    """Fetch a single page — called by the thread pool workers.

    Retries transient failures (5xx, timeouts, connection errors) with
    exponential backoff before giving up.
    """
    params = {
        "where": where,
        "outFields": out_fields,
        "outSR": out_sr,
        "f": "json",
        "resultRecordCount": batch_size,
        "resultOffset": offset,
        "returnGeometry": str(return_geometry).lower(),
    }
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(f"{url}/query", params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"ArcGIS API error at offset {offset}: {data['error']}")
            return data.get("features", [])
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as exc:
            last_exc = exc
        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            if exc.response is not None and exc.response.status_code < 500:
                raise  # 4xx won't heal on retry
        if attempt < retries - 1:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Page at offset {offset} failed after {retries} attempts: {last_exc}")


def iterate_feature_pages_parallel(
    url: str,
    where: str = "1=1",
    out_fields: str = "*",
    out_sr: int = 4326,
    batch_size: int = DEFAULT_BATCH_SIZE,
    return_geometry: bool = True,
    max_workers: int = 4,
) -> Iterator[list[dict]]:
    """Yield pages in completion order with a bounded in-flight window.

    Only ``max_workers`` futures are submitted at once. Completed futures are
    removed before the next request is submitted so their feature payloads can
    be reclaimed as soon as the caller finishes each yielded page.

    Any page failure raises and closes the iterator. Callers that stage pages
    incrementally must keep their writes in a transaction and roll it back on
    failure so a partial fetch can never drive missing-row expiration.
    """
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    log = get_dagster_logger()
    total = _get_feature_count(url, where)
    page_total = (total + batch_size - 1) // batch_size
    log.info(f"Total features to fetch: {total:,} ({page_total} pages)")
    if total == 0:
        return

    offsets = iter(range(0, total, batch_size))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        def submit(offset: int):
            return pool.submit(
                _fetch_page, url, where, out_fields, out_sr,
                batch_size, offset, return_geometry,
            )

        pending = {}
        for offset in offsets:
            pending[submit(offset)] = offset
            if len(pending) == max_workers:
                break

        completed = 0
        fetched = 0
        while pending:
            future = next(as_completed(pending))
            offset = pending.pop(future)
            try:
                features = future.result()
            except Exception as exc:
                for other in pending:
                    other.cancel()
                raise RuntimeError(
                    f"Parallel fetch incomplete: page at offset {offset} failed. "
                    "Refusing to yield a successful partial result."
                ) from exc

            completed += 1
            fetched += len(features)
            if completed % 10 == 0 or completed == page_total:
                log.info(
                    f"  Pages consumed: {completed}/{page_total} "
                    f"({fetched:,} features)"
                )

            yield features
            del features, future

            try:
                next_offset = next(offsets)
            except StopIteration:
                continue
            pending[submit(next_offset)] = next_offset

    if fetched != total:
        raise RuntimeError(
            f"Parallel fetch returned {fetched:,} features but ArcGIS reported "
            f"{total:,}. Refusing a partial result."
        )
    log.info(f"Bounded parallel fetch complete: {fetched:,} features")
