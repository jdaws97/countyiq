"""ArcGIS REST API client with automatic pagination.

Handles FeatureServer and MapServer endpoints. Paginates using
resultRecordCount + resultOffset until all records are fetched.
"""

import time

import requests
from dagster import get_dagster_logger

DEFAULT_BATCH_SIZE = 2000
REQUEST_TIMEOUT = 60


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
    log = get_dagster_logger()
    all_features = []
    offset = 0

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
        all_features.extend(features)
        log.info(f"Fetched {len(features)} features (offset={offset}, total={len(all_features)})")

        # ArcGIS sets exceededTransferLimit when there are more records
        if not data.get("exceededTransferLimit", False) or len(features) == 0:
            break

        offset += len(features)
        time.sleep(delay)

    log.info(f"Finished: {len(all_features)} total features from {url}")
    return all_features
