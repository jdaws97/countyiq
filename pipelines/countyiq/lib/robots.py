"""Reusable, fail-closed robots.txt decisions for official web sources."""

from __future__ import annotations

import ipaddress
import posixpath
import re
import socket
import threading
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlparse, urlsplit

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


class UnsafeSourceAddressError(requests.RequestException):
    """Raised before an HTTP request can reach a local or private address."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"source URL is not a public HTTP endpoint: {reason}")


def assert_source_path(url: str, allowed_url_prefixes: tuple[str, ...] = ()) -> None:
    """Restrict a shared delivery origin to its reviewed publisher directory."""
    prefixes = [
        prefix
        for prefix in allowed_url_prefixes
        if source_origin(prefix) == source_origin(url)
    ]
    if not prefixes:
        return
    path = posixpath.normpath(unquote(urlsplit(url).path))
    for prefix in prefixes:
        approved_path = posixpath.normpath(unquote(urlsplit(prefix).path)).rstrip("/")
        if path == approved_path or path.startswith(approved_path + "/"):
            return
    raise SourceOriginDeniedError(url)


@dataclass(frozen=True)
class RobotsDecision:
    allowed: bool
    reason: str
    robots_url: str
    status_code: int | None = None


@dataclass(frozen=True)
class _RobotsRule:
    allow: bool
    pattern: str
    specificity: int
    regex: re.Pattern[str]

    @classmethod
    def parse(cls, *, allow: bool, pattern: str) -> _RobotsRule | None:
        pattern = pattern.strip()
        if not pattern:
            return None
        anchored = pattern.endswith("$")
        body = pattern[:-1] if anchored else pattern
        expression = re.escape(body).replace(r"\*", ".*")
        return cls(
            allow=allow,
            pattern=pattern,
            specificity=len(body.replace("*", "")),
            regex=re.compile(f"^{expression}{'$' if anchored else ''}"),
        )


class _RobotsMatcher:
    """Match robots groups with wildcard, end-anchor, and longest-rule semantics."""

    def __init__(
        self,
        groups: list[tuple[tuple[str, ...], tuple[_RobotsRule, ...]]],
    ) -> None:
        self._groups = groups

    @classmethod
    def parse(cls, lines: list[str]) -> _RobotsMatcher:
        groups: list[tuple[tuple[str, ...], tuple[_RobotsRule, ...]]] = []
        agents: list[str] = []
        rules: list[_RobotsRule] = []
        group_has_directive = False

        def flush() -> None:
            nonlocal agents, rules, group_has_directive
            if agents:
                groups.append((tuple(agents), tuple(rules)))
            agents = []
            rules = []
            group_has_directive = False

        for raw_line in lines:
            line = raw_line.partition("#")[0].strip()
            if not line or ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.casefold()
            if field == "user-agent":
                if agents and group_has_directive:
                    flush()
                if value:
                    agents.append(value.casefold())
                continue
            if not agents:
                continue
            group_has_directive = True
            if field not in {"allow", "disallow"}:
                continue
            rule = _RobotsRule.parse(allow=field == "allow", pattern=value)
            if rule is not None:
                rules.append(rule)
        flush()
        return cls(groups)

    def can_fetch(self, product_token: str, url: str) -> bool:
        product = product_token.casefold()
        best_agent_specificity = -1
        selected_rules: list[_RobotsRule] = []
        for agents, rules in self._groups:
            scores = [
                0 if agent == "*" else len(agent)
                for agent in agents
                if agent == "*" or agent in product
            ]
            if not scores:
                continue
            specificity = max(scores)
            if specificity > best_agent_specificity:
                best_agent_specificity = specificity
                selected_rules = list(rules)
            elif specificity == best_agent_specificity:
                selected_rules.extend(rules)

        if best_agent_specificity < 0:
            return True
        parsed = urlsplit(url)
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        matching = [rule for rule in selected_rules if rule.regex.search(target)]
        if not matching:
            return True
        longest = max(rule.specificity for rule in matching)
        return any(rule.allow for rule in matching if rule.specificity == longest)


class RobotsPolicy:
    """Cache one robots policy per origin and expose auditable decisions.

    Missing policies (404/410) follow the ordinary allow convention. Network
    errors, server/client errors, empty responses, and explicit disallows fail
    closed. The outbound HTTP user agent remains honest while an explicit
    product token selects the matching robots group.
    """

    def __init__(
        self,
        user_agent: str,
        *,
        product_token: str | None = None,
        timeout: int = 10,
    ):
        self._user_agent = user_agent
        self._product_token = product_token or user_agent
        self._timeout = timeout
        self._cache: dict[
            str,
            tuple[_RobotsMatcher | None, str, int | None, str],
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
        allowed = parser.can_fetch(self._product_token, url)
        return RobotsDecision(
            allowed,
            "allowed" if allowed else "explicit_disallow",
            cached_url,
            status_code,
        )

    def allowed(self, url: str) -> bool:
        return self.decision(url).allowed

    def cache_browser_response(
        self,
        robots_url: str,
        *,
        text: str,
        status_code: int,
        resolved_url: str | None = None,
    ) -> None:
        """Cache a robots response obtained through an honest browser transport.

        Some public hosts terminate the Python/OpenSSL connection while serving
        the same URL normally to Chromium. The browser caller must enforce the
        reviewed origin boundary before passing the response here. Empty/error
        responses retain the same fail-closed semantics as the direct client.
        """

        parsed = urlparse(robots_url)
        origin = f"{parsed.scheme or 'https'}://{parsed.netloc.lower()}"
        result = self._parse_response(
            text=text,
            status_code=status_code,
            resolved_url=resolved_url or robots_url,
        )
        with self._lock:
            self._cache[origin] = result

    @staticmethod
    def _parse_response(
        *,
        text: str,
        status_code: int,
        resolved_url: str,
    ) -> tuple[_RobotsMatcher | None, str, int | None, str]:
        if status_code in (404, 410):
            parser = _RobotsMatcher.parse([])
            return parser, "robots_missing", status_code, resolved_url
        if status_code >= 400:
            return None, f"robots_http_{status_code}", status_code, resolved_url
        if not text.strip():
            return None, "robots_empty", status_code, resolved_url

        parser = _RobotsMatcher.parse(text.splitlines())
        return parser, "robots_loaded", status_code, resolved_url

    def _fetch(
        self, robots_url: str
    ) -> tuple[_RobotsMatcher | None, str, int | None, str]:
        try:
            response = get_public_with_redirects(
                requests,
                robots_url,
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            return None, f"robots_network_error:{type(exc).__name__}", None, robots_url

        return self._parse_response(
            text=response.text,
            status_code=response.status_code,
            resolved_url=getattr(response, "url", robots_url),
        )


def get_with_robots(
    url: str,
    *,
    robots: RobotsPolicy,
    requester=requests,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    stream: bool = False,
    max_redirects: int = 5,
    allowed_origins: set[str] | frozenset[str] | None = None,
    allowed_url_prefixes: tuple[str, ...] = (),
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
        assert_public_http_url(current_url)
        assert_source_path(current_url, allowed_url_prefixes)
        if (
            normalized_allowed_origins is not None
            and source_origin(current_url) not in normalized_allowed_origins
        ):
            raise SourceOriginDeniedError(current_url)
        decision = robots.decision(current_url)
        if not decision.allowed:
            raise RobotsDeniedError(current_url, decision.reason)

        response = requester.get(
            current_url,
            headers=request_headers if redirect_count == 0 else redirect_headers,
            timeout=timeout,
            allow_redirects=False,
            stream=stream,
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


def assert_public_http_url(url: str) -> None:
    """Reject non-HTTP, credential-bearing, and non-public network targets.

    Source URLs and redirects are untrusted input. Resolving the
    hostname before each hop blocks ordinary loopback, RFC1918, link-local,
    container-network, and instance-metadata SSRF targets. Host firewall rules
    remain the final defense against DNS rebinding between this check and the
    socket connection.
    """

    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeSourceAddressError("unsupported_scheme")
    if not parsed.hostname:
        raise UnsafeSourceAddressError("missing_hostname")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeSourceAddressError("embedded_credentials")

    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise UnsafeSourceAddressError("invalid_port") from exc
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except (socket.gaierror, UnicodeError, ValueError) as exc:
        raise UnsafeSourceAddressError("hostname_resolution_failed") from exc

    resolved = {entry[4][0].split("%", 1)[0] for entry in addresses if entry[4]}
    if not resolved:
        raise UnsafeSourceAddressError("hostname_resolution_failed")
    try:
        if any(not ipaddress.ip_address(address).is_global for address in resolved):
            raise UnsafeSourceAddressError("non_public_address")
    except ValueError as exc:
        raise UnsafeSourceAddressError("invalid_resolved_address") from exc


def get_public_with_redirects(
    client,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    max_redirects: int = 5,
    **request_kwargs,
) -> requests.Response:
    """GET a public URL while validating every redirect before connecting."""

    current_url = url
    request_headers = dict(headers or {})
    for redirect_count in range(max_redirects + 1):
        assert_public_http_url(current_url)
        response = client.get(
            current_url,
            headers=request_headers,
            timeout=timeout,
            allow_redirects=False,
            **request_kwargs,
        )
        if response.status_code not in _REDIRECT_STATUSES:
            return response

        location = response.headers.get("Location")
        if not location:
            return response
        if redirect_count == max_redirects:
            response.close()
            raise requests.TooManyRedirects(
                f"more than {max_redirects} redirects while fetching a source"
            )

        next_url = urljoin(getattr(response, "url", current_url), location)
        if source_origin(next_url) != source_origin(current_url):
            request_headers = {
                key: value
                for key, value in request_headers.items()
                if key.lower() not in {"authorization", "cookie", "proxy-authorization"}
            }
        current_url = next_url
        response.close()

    raise AssertionError("redirect loop guard should be unreachable")


def source_origin(url: str) -> str:
    """Return the lower-case scheme and authority used by source policy."""

    parsed = urlparse(url)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}".rstrip("/")
