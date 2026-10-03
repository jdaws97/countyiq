"""Compare public-source connectivity from the current host; no credentials or writes."""

import json
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPException
from urllib.parse import urlsplit
from urllib.request import urlopen

ENDPOINTS = {
    "county_gis": "https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Parcels/FeatureServer/0?f=json",
    "penndot": "https://gis.penndot.pa.gov/gis/rest/services/opendata/roadwaysegments/MapServer/0?f=json",
    "dep": "https://gis.dep.pa.gov/depgisprd/rest/services/emappa/eMapPA_External/FeatureServer/171?f=json",
    "county_website": "https://yorkcountypa.gov/",
    "control": "https://api.github.com/",
}


def probe(item):
    name, url = item
    started = time.monotonic()
    result = {"source": name, "hostname": urlsplit(url).hostname}
    try:
        result["addresses"] = sorted(
            {address[4][0] for address in socket.getaddrinfo(result["hostname"], 443)}
        )
        with urlopen(url, timeout=8) as response:
            result["http_status"] = response.status
            result["content_type"] = response.headers.get_content_type()
            # Reading a small body verifies a completed response without logging
            # source records or downloading county datasets.
            response.read(1024)
    except (OSError, HTTPException) as error:
        result["error"] = str(error)
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return result


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(probe, ENDPOINTS.items()))
    print(json.dumps(results, indent=2))
