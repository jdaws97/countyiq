"""Verified external identity; CountyIQ account IDs never depend on a vendor.

Alpha uses Cloudflare Access. No raw email header, unsigned token, local bypass,
or service token is accepted as a customer identity.
"""

from dataclasses import dataclass
from functools import lru_cache
import os
import re
from urllib.parse import urlsplit
import jwt
from fastapi import HTTPException, Request
from api.lib.rate_limit import PerClientRateLimiter, client_ip

# Unknown key IDs make PyJWKClient refresh its remote key set. Bound that work
# before key lookup, including for the public session endpoint. Per worker.
verification_limiter = PerClientRateLimiter(rate_per_minute=60, burst=20)


@dataclass(frozen=True)
class Identity:
    provider: str
    issuer: str
    subject: str
    email: str


def auth_configuration():
    provider = os.environ.get("COUNTYIQ_AUTH_PROVIDER", "disabled").strip()
    issuer = os.environ.get("COUNTYIQ_ACCESS_ISSUER", "").strip().rstrip("/")
    audience = os.environ.get("COUNTYIQ_ACCESS_AUD", "").strip()
    if provider == "disabled":
        return None
    if (
        provider != "cloudflare_access"
        or not re.fullmatch(r"https://[a-z0-9-]+\.cloudflareaccess\.com", issuer)
        or not audience
    ):
        raise HTTPException(503, "Account sign-in is not configured")
    return issuer, audience


@lru_cache(maxsize=4)
def signing_keys(issuer: str):
    return jwt.PyJWKClient(
        issuer + "/cdn-cgi/access/certs", cache_jwk_set=True, lifespan=300, timeout=5
    )


def require_identity(request: Request) -> Identity:
    cached = getattr(request.state, "countyiq_identity", None)
    if cached:
        return cached
    config = auth_configuration()
    if config is None:
        raise HTTPException(401, "Sign in to access your workspace")
    token = request.headers.get("cf-access-jwt-assertion", "")
    if not token or len(token) > 16384:
        raise HTTPException(401, "A verified sign-in is required")
    issuer, audience = config
    try:
        header = jwt.get_unverified_header(token)
        if (
            header.get("alg") != "RS256"
            or not isinstance(header.get("kid"), str)
            or len(header["kid"]) > 256
        ):
            raise jwt.InvalidTokenError()
        if not verification_limiter.allow(client_ip(request)):
            raise HTTPException(
                429, "Too many sign-in verification requests; try again shortly"
            )
        key = signing_keys(issuer).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={"require": ["iss", "aud", "sub", "exp", "iat"]},
            leeway=15,
        )
        if (
            payload.get("type") != "app"
            or not isinstance(payload.get("email"), str)
            or not payload["email"].strip()
        ):
            raise jwt.InvalidTokenError("Human application identity required")
        if (
            not isinstance(payload["sub"], str)
            or not 1 <= len(payload["sub"]) <= 256
            or len(payload["email"]) > 320
        ):
            raise jwt.InvalidTokenError()
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(
            503, "Sign-in verification is temporarily unavailable"
        ) from exc
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(401, "Sign-in is invalid or expired") from exc
    identity = Identity(
        "cloudflare_access", issuer, payload["sub"], payload["email"].strip()
    )
    request.state.countyiq_identity = identity
    return identity


def require_workspace_write(request: Request):
    # Cross-site forms cannot set this header. Origin is an additional check
    # for deployments using Access's browser cookie to inject the JWT.
    if request.headers.get("x-countyiq-workspace") != "1":
        raise HTTPException(403, "Same-origin workspace request required")
    origin = request.headers.get("origin")
    if origin:
        allowed = {
            value.strip().rstrip("/")
            for value in os.environ.get("COUNTYIQ_WORKSPACE_ORIGINS", "").split(",")
            if value.strip()
        }
        if not allowed:
            allowed = {str(request.base_url).rstrip("/")}
        if origin.rstrip("/") not in allowed:
            raise HTTPException(403, "Workspace origin is not allowed")


def login_url():
    # Host is operator configuration, never a user-provided redirect.
    configured = os.environ.get("COUNTYIQ_APP_URL", "").strip().rstrip("/")
    if (
        configured
        and urlsplit(configured).scheme == "https"
        and urlsplit(configured).netloc
        and not urlsplit(configured).username
    ):
        return configured + "/"
    return "/app"


def optional_identity(request: Request) -> Identity | None:
    """Provider-specific credential discovery stays behind this boundary."""
    if auth_configuration() is None or not request.headers.get(
        "cf-access-jwt-assertion"
    ):
        return None
    return require_identity(request)


def logout_url() -> str:
    return "/cdn-cgi/access/logout"


def require_product_access(request: Request):
    """Local exploration is anonymous; configured providers protect product data."""
    if request.url.path in {"/api/health", "/api/ready", "/api/session"}:
        return
    if auth_configuration() is not None:
        require_identity(request)
