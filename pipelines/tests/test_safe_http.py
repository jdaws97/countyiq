"""Dynamic source URLs must not become an SSRF path."""

import socket

import pytest

from countyiq.lib.robots import (
    UnsafeSourceAddressError,
    assert_public_http_url,
    get_public_with_redirects,
)


def _resolved(address: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:password@example.gov/data",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.8/internal",
        "http://[::1]/admin",
        "https://example.com:invalid/data",
    ],
)
def test_non_public_source_urls_are_rejected(monkeypatch, url):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: _resolved("127.0.0.1"))

    with pytest.raises(UnsafeSourceAddressError):
        assert_public_http_url(url)


def test_hostname_resolving_to_private_address_is_rejected(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: _resolved("10.1.2.3"))

    with pytest.raises(UnsafeSourceAddressError, match="non_public_address"):
        assert_public_http_url("https://public-looking.example/data")


def test_public_https_address_is_allowed(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: _resolved("93.184.216.34"))

    assert_public_http_url("https://example.com/data") is None


def test_private_redirect_is_rejected_before_second_request(monkeypatch):
    def resolve(hostname, *_args, **_kwargs):
        address = "169.254.169.254" if hostname == "169.254.169.254" else "93.184.216.34"
        return _resolved(address)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)

    class Response:
        status_code = 302
        headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        url = "https://example.com/start"

        @staticmethod
        def close():
            return None

    class Client:
        def __init__(self):
            self.calls = 0

        def get(self, *_args, **_kwargs):
            self.calls += 1
            return Response()

    client = Client()
    with pytest.raises(UnsafeSourceAddressError, match="non_public_address"):
        get_public_with_redirects(client, "https://example.com/start")

    assert client.calls == 1


def test_cross_origin_redirect_drops_credentials(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: _resolved("93.184.216.34"),
    )

    class Response:
        def __init__(self, status_code, url, location=None):
            self.status_code = status_code
            self.url = url
            self.headers = {"Location": location} if location else {}

        @staticmethod
        def close():
            return None

    class Client:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs["headers"]))
            if len(self.calls) == 1:
                return Response(302, url, "https://other.example/final")
            return Response(200, url)

    client = Client()
    response = get_public_with_redirects(
        client,
        "https://source.example/start",
        headers={
            "Authorization": "Bearer secret",
            "Cookie": "session=secret",
            "Proxy-Authorization": "Basic secret",
            "User-Agent": "CountyIQ",
        },
    )

    assert response.status_code == 200
    assert client.calls[0][1]["Authorization"] == "Bearer secret"
    assert client.calls[1][1] == {"User-Agent": "CountyIQ"}
