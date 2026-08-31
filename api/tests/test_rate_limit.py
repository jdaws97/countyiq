"""Unit tests for the in-process API rate limiters (no DB required)."""

from starlette.requests import Request

from api.lib.rate_limit import DailyBudget, PerClientRateLimiter, client_ip


def test_burst_then_throttle():
    limiter = PerClientRateLimiter(rate_per_minute=60, burst=3)
    assert limiter.allow("1.2.3.4")
    assert limiter.allow("1.2.3.4")
    assert limiter.allow("1.2.3.4")
    # Burst exhausted; refill is 1/sec so an immediate 4th call is denied.
    assert not limiter.allow("1.2.3.4")


def test_clients_are_independent():
    limiter = PerClientRateLimiter(rate_per_minute=60, burst=1)
    assert limiter.allow("1.1.1.1")
    assert not limiter.allow("1.1.1.1")
    assert limiter.allow("2.2.2.2")


def test_client_bucket_memory_is_bounded_and_evicts_least_recently_used():
    limiter = PerClientRateLimiter(rate_per_minute=60, burst=1, max_clients=2)

    assert limiter.allow("first")
    assert limiter.allow("second")
    assert not limiter.allow("first")  # touch first; second is now least recent
    assert limiter.allow("third")

    assert list(limiter._buckets) == ["first", "third"]


def test_refill_restores_tokens():
    limiter = PerClientRateLimiter(rate_per_minute=6000, burst=1)  # 100 tokens/sec
    assert limiter.allow("ip")
    assert not limiter.allow("ip")
    import time

    time.sleep(0.05)  # 100/sec refill -> ~5 tokens accrued, capped at burst=1
    assert limiter.allow("ip")


def test_daily_budget_exhausts_and_resets():
    budget = DailyBudget(limit=2)
    assert budget.spend()
    assert budget.spend()
    assert not budget.spend()
    # Simulate a UTC day rollover.
    budget._day = "1970-01-01"
    assert budget.spend()


def test_client_ip_ignores_untrusted_forwarding_headers():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/search",
            "headers": [
                (b"cf-connecting-ip", b"203.0.113.10"),
                (b"x-forwarded-for", b"198.51.100.20"),
            ],
            "client": ("192.0.2.30", 50000),
            "scheme": "https",
            "server": ("testserver", 443),
            "query_string": b"",
        }
    )

    assert client_ip(request) == "192.0.2.30"
