"""Reusable, fail-closed robots.txt decisions for official web sources."""

from __future__ import annotations

import threading
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests


_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class RobotsDeniedError(requests.RequestException):
    """Raised before fetching a URL that the applicable robots policy blocks."""

    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(
            f"robots policy blocks {url}: {reason}",
            request=requests.Request("GET", url).prepare(),
        )


class SourceOriginDeniedError(requests.RequestException):
    """Raised before following a source request to an unreviewed origin."""

    def __init__(self, url: str):
        self.url = url
        super().__init__(
            f"source policy does not allow origin {source_origin(url)}",
            request=requests.Request("GET", url).prepare(),
        )


@dataclass(frozen=True)
class RobotsDecision:
    allowed: bool
    reason: str
    robots_url: str
    status_code: int | None = None


class RobotsPolicy:
    """Cache one robots policy per origin and expose auditable decisions.

    Missing policies (404/410) follow the ordinary allow convention. Network
    errors, server/client errors, empty responses, and explicit disallows fail
    closed. The same honest user agent is used for the policy and source fetch.
    """

    def __init__(self, user_agent: str, *, timeout: int = 10):
        self._user_agent = user_agent
        self._timeout = timeout
        self._cache: dict[
            str,
            tuple[urllib.robotparser.RobotFileParser | None, str, int | None, str],
        ] = {}
        self._lock = threading.Lock()

    def decision(self, url: str) -> RobotsDecision:
        parsed = urlparse(url)
        origin = f"{parsed.scheme or 'https'}://{parsed.netloc.lower()}"
        robots_url = f"{origin}/robots.txt"
        with self._lock:
            if origin not in self._cache:
                self._cache[origin] = self._fetch(robots_url)
            parser, reason, status_code, cached_url = self._cache[origin]
        if parser is None:
            return RobotsDecision(False, reason, cached_url, status_code)
        allowed = parser.can_fetch(self._user_agent, url)
        return RobotsDecision(
            allowed,
            "allowed" if allowed else "explicit_disallow",
            cached_url,
            status_code,
        )

    def allowed(self, url: str) -> bool:
        return self.decision(url).allowed

    def _fetch(
        self, robots_url: str
    ) -> tuple[urllib.robotparser.RobotFileParser | None, str, int | None, str]:
        try:
            response = requests.get(
                robots_url,
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            return None, f"robots_network_error:{type(exc).__name__}", None, robots_url

        if response.status_code in (404, 410):
            parser = urllib.robotparser.RobotFileParser()
            parser.parse([])
            return (
                parser,
                "robots_missing",
                response.status_code,
                getattr(response, "url", robots_url),
            )
        if response.status_code >= 400:
            return (
                None,
                f"robots_http_{response.status_code}",
                response.status_code,
                getattr(response, "url", robots_url),
            )
        if not response.text.strip():
            return (
                None,
                "robots_empty",
                response.status_code,
                getattr(response, "url", robots_url),
            )

        parser = urllib.robotparser.RobotFileParser()
        parser.parse(response.text.splitlines())
        return (
            parser,
            "robots_loaded",
            response.status_code,
            getattr(response, "url", robots_url),
        )


def get_with_robots(
    url: str,
    *,
    robots: RobotsPolicy,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    max_redirects: int = 5,
    allowed_origins: set[str] | frozenset[str] | None = None,
) -> requests.Response:
    """GET a URL while authorizing every redirect target before access.

    ``requests`` normally follows redirects before callers can inspect the new
    origin. Municipal sites frequently move between vendor-hosted domains, so
    every hop must receive its own fail-closed robots decision. Conditional
    validators are intentionally removed after the first hop because an ETag
    or Last-Modified value is scoped to the reviewed listing URL.
    """

    current_url = url
    normalized_allowed_origins = (
        {origin.lower().rstrip("/") for origin in allowed_origins}
        if allowed_origins is not None
        else None
    )
    request_headers = dict(headers or {})
    redirect_headers = {
        key: value
        for key, value in request_headers.items()
        if key.lower() == "user-agent"
    }

    for redirect_count in range(max_redirects + 1):
        if (
            normalized_allowed_origins is not None
            and source_origin(current_url) not in normalized_allowed_origins
        ):
            raise SourceOriginDeniedError(current_url)
        decision = robots.decision(current_url)
        if not decision.allowed:
            raise RobotsDeniedError(current_url, decision.reason)

        response = requests.get(
            current_url,
            headers=request_headers if redirect_count == 0 else redirect_headers,
            timeout=timeout,
            allow_redirects=False,
        )
        if response.status_code not in _REDIRECT_STATUSES:
            return response

        location = response.headers.get("Location")
        if not location:
            return response
        if redirect_count == max_redirects:
            response.close()
            raise requests.TooManyRedirects(
                f"more than {max_redirects} redirects while fetching {url}"
            )
        current_url = urljoin(current_url, location)
        response.close()

    raise AssertionError("redirect loop guard should be unreachable")


def source_origin(url: str) -> str:
    """Return the lower-case scheme and authority used by source policy."""

    parsed = urlparse(url)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}".rstrip("/")
