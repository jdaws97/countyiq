"""Validate Access signature and claims, not a caller-supplied email header."""

import time
from types import SimpleNamespace
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.requests import Request
from fastapi import HTTPException
from api.lib import auth

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ISSUER = "https://countyiq-test.cloudflareaccess.com"


def token(**changes):
    claims = {
        "iss": ISSUER,
        "aud": ["test-audience"],
        "sub": "user-one",
        "email": "tester@example.test",
        "type": "app",
        "iat": int(time.time()) - 1,
        "exp": int(time.time()) + 300,
    }
    claims.update(changes)
    return jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": "test-key"})


def request(headers=None, method="GET"):
    return Request(
        {
            "type": "http",
            "method": method,
            "scheme": "http",
            "server": ("testserver", 80),
            "path": "/",
            "headers": [
                (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
            ],
        }
    )


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(auth.verification_limiter, "allow", lambda ip: True)
    monkeypatch.setenv("COUNTYIQ_AUTH_PROVIDER", "cloudflare_access")
    monkeypatch.setenv("COUNTYIQ_ACCESS_ISSUER", ISSUER)
    monkeypatch.setenv("COUNTYIQ_ACCESS_AUD", "test-audience")
    monkeypatch.setattr(
        auth,
        "signing_keys",
        lambda issuer: SimpleNamespace(
            get_signing_key_from_jwt=lambda value: SimpleNamespace(key=KEY.public_key())
        ),
    )


def test_verified_identity_ignores_untrusted_email_header(configured):
    identity = auth.require_identity(
        request(
            {
                "Cf-Access-Jwt-Assertion": token(),
                "Cf-Access-Authenticated-User-Email": "attacker@example.test",
            }
        )
    )
    assert identity.subject == "user-one"
    assert identity.email == "tester@example.test"


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "https://attacker.cloudflareaccess.com"},
        {"aud": ["wrong-app"]},
        {"exp": int(time.time()) - 100},
        {"iat": int(time.time()) + 500},
        {"sub": ""},
        {"email": None},
        {"type": "org"},
    ],
)
def test_bad_claims_fail_closed(configured, changes):
    with pytest.raises(HTTPException) as exc:
        auth.require_identity(request({"Cf-Access-Jwt-Assertion": token(**changes)}))
    assert exc.value.status_code == 401


def test_bad_signature_and_raw_headers_cannot_sign_in(configured):
    forged = jwt.encode(
        {"sub": "attacker"},
        "untrusted-key-for-negative-test-only",
        algorithm="HS256",
        headers={"kid": "test-key"},
    )
    for headers in [
        {"Cf-Access-Jwt-Assertion": forged},
        {"Cf-Access-Authenticated-User-Email": "tester@example.test"},
        {},
    ]:
        with pytest.raises(HTTPException):
            auth.require_identity(request(headers))


def test_writes_require_custom_header_and_allowed_origin(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_WORKSPACE_ORIGINS", "https://app.countyiq.net")
    for headers in [
        {},
        {"X-CountyIQ-Workspace": "1", "Origin": "https://evil.example"},
    ]:
        with pytest.raises(HTTPException):
            auth.require_workspace_write(request(headers, "POST"))
    auth.require_workspace_write(
        request(
            {"X-CountyIQ-Workspace": "1", "Origin": "https://app.countyiq.net"}, "POST"
        )
    )


def test_unknown_keys_are_throttled_before_remote_lookup(configured, monkeypatch):
    from api.lib.rate_limit import PerClientRateLimiter

    monkeypatch.setattr(
        auth, "verification_limiter", PerClientRateLimiter(rate_per_minute=0, burst=2)
    )
    lookups = []

    def unknown_key(value):
        lookups.append(value)
        raise jwt.PyJWKClientError("Unknown fixture key")

    monkeypatch.setattr(
        auth,
        "signing_keys",
        lambda issuer: SimpleNamespace(get_signing_key_from_jwt=unknown_key),
    )
    statuses = []
    for _ in range(3):
        with pytest.raises(HTTPException) as exc:
            auth.require_identity(request({"Cf-Access-Jwt-Assertion": token()}))
        statuses.append(exc.value.status_code)
    assert statuses == [401, 401, 429]
    assert len(lookups) == 2


def test_identity_is_only_verified_once_per_request(configured, monkeypatch):
    from api.lib.rate_limit import PerClientRateLimiter

    monkeypatch.setattr(
        auth, "verification_limiter", PerClientRateLimiter(rate_per_minute=0, burst=1)
    )
    req = request({"Cf-Access-Jwt-Assertion": token()})
    assert auth.require_identity(req) is auth.require_identity(req)


def test_service_token_claims_are_not_a_customer(configured):
    # Access service tokens have an empty sub and a common_name client ID.
    with pytest.raises(HTTPException) as exc:
        auth.require_identity(
            request(
                {
                    "Cf-Access-Jwt-Assertion": token(
                        sub="", common_name="fixture-service.access"
                    )
                }
            )
        )
    assert exc.value.status_code == 401


def test_login_uses_app_root(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_APP_URL", "https://app.countyiq.net")
    assert auth.login_url() == "https://app.countyiq.net/"


def test_product_api_requires_identity_when_configured(configured):
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    for path in [
        "/api/meta",
        "/api/stats",
        "/api/parcels/summary",
        "/api/feed",
        "/api/directory/organizations",
    ]:
        response = client.get(path)
        assert response.status_code == 401, (path, response.text)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/session").json()["authenticated"] is False
    response = client.get("/api/meta", headers={"Cf-Access-Jwt-Assertion": token()})
    assert response.status_code == 200


def test_disabled_auth_is_anonymous_local_exploration(monkeypatch):
    from fastapi.testclient import TestClient
    from api.main import app

    monkeypatch.setenv("COUNTYIQ_AUTH_PROVIDER", "disabled")
    client = TestClient(app)
    assert client.get("/api/meta").status_code == 200
    assert client.get("/api/session").json()["configured"] is False


def test_invalid_provider_does_not_open_product_data(monkeypatch):
    from fastapi.testclient import TestClient
    from api.main import app

    monkeypatch.setenv("COUNTYIQ_AUTH_PROVIDER", "unknown")
    assert TestClient(app).get("/api/meta").status_code == 503


def test_optional_identity_rejects_bad_credentials(configured):
    assert auth.optional_identity(request()) is None
    with pytest.raises(HTTPException) as exc:
        auth.optional_identity(request({"Cf-Access-Jwt-Assertion": "invalid"}))
    assert exc.value.status_code == 401
