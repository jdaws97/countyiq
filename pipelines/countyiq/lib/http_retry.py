"""Shared HTTP GET with retry for source downloads.

Bulk source assets each had their own recursive retry that only caught
5xx — so a transient 404/timeout/connection-reset from a flaky county
CMS (e.g. CivicPlus DocumentCenter) killed the whole asset run. This
centralizes a small, correct retry: transient statuses + network errors,
exponential backoff with jitter, honoring Retry-After.
"""

from __future__ import annotations

import logging
import random
import time

import requests

_log = logging.getLogger("countyiq.http")

# Honest identifying UA. County CMS platforms (CivicPlus DocumentCenter)
# return 404 to the default `python-requests/x.y` UA but 200 to a normal
# browser-style UA — verified deterministic 2026-08-02 on the delinquent
# tax-claim PDF. We identify ourselves as CountyIQ with a contact URL
# rather than spoofing a specific browser: honest, and not tripping naive
# user-agent blocklists.
_DEFAULT_UA = "Mozilla/5.0 (compatible; CountyIQ/1.0; +https://countyiq.app)"

# 404 stays retryable because CivicPlus also flaps intermittently, but the
# primary defense against its 404s is the User-Agent above.
_TRANSIENT_STATUSES = {404, 408, 425, 429, 500, 502, 503, 504}


def get_with_retry(
    url: str,
    *,
    timeout: int = 60,
    retries: int = 4,
    headers: dict | None = None,
    backoff_base: float = 2.0,
    backoff_cap: float = 30.0,
) -> requests.Response:
    """GET a URL, retrying transient failures. Raises on final failure.

    Returns a response with a 2xx status. Retries transient HTTP statuses
    and network errors; a non-transient 4xx (401/403/etc.) raises
    immediately since it will not heal. Sends an honest CountyIQ
    User-Agent by default (see _DEFAULT_UA).
    """
    request_headers = {"User-Agent": _DEFAULT_UA}
    if headers:
        request_headers.update(headers)
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(
                url, timeout=timeout, headers=request_headers, allow_redirects=True
            )
            if resp.status_code in _TRANSIENT_STATUSES:
                resp_after = resp.headers.get("Retry-After")
                wait = _retry_wait(attempt, backoff_base, backoff_cap, resp_after)
                _log.warning(
                    "GET %s -> %d (transient), attempt %d/%d, retrying in %.1fs",
                    url,
                    resp.status_code,
                    attempt + 1,
                    retries,
                    wait,
                )
                last_exc = requests.exceptions.HTTPError(
                    f"{resp.status_code} for {url}"
                )
                if attempt < retries - 1:
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
            resp.raise_for_status()  # non-transient 4xx raises here immediately
            return resp
        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ) as exc:
            last_exc = exc
            wait = _retry_wait(attempt, backoff_base, backoff_cap, None)
            _log.warning(
                "GET %s network error (%s), attempt %d/%d, retrying in %.1fs",
                url,
                exc,
                attempt + 1,
                retries,
                wait,
            )
            if attempt < retries - 1:
                time.sleep(wait)
    raise (
        last_exc
        if last_exc
        else RuntimeError(f"GET {url} failed with no captured error")
    )


def _retry_wait(
    attempt: int, base: float, cap: float, retry_after: str | None
) -> float:
    if retry_after:
        try:
            return float(retry_after)  # honor server-specified minimum verbatim
        except ValueError:
            pass
    return min(cap, base**attempt) + random.uniform(0, 1)
