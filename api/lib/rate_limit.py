"""In-process rate limiting for LLM-backed endpoints.

The public /api/search endpoint proxies to OpenRouter with a paid API key and
no auth in front of it, so it needs two guards:

- A per-client token bucket (burst + steady refill) so one IP can't hammer it.
- A global daily call budget so even distributed abuse can't drain the key;
  callers fall back to the free pg_trgm path when the budget is exhausted.

State is per-process (each uvicorn worker has its own buckets), so the
effective limits are `value x workers`. That's fine at this scale — the goal
is stopping runaway spend, not precise accounting.
"""

import os
import threading
import time
from datetime import datetime, timezone

from fastapi import Request


class PerClientRateLimiter:
    """Token bucket per client key. Thread-safe; prunes idle buckets."""

    def __init__(self, rate_per_minute: float, burst: int):
        self._rate = rate_per_minute / 60.0
        self._burst = float(burst)
        self._buckets: dict[str, list[float]] = {}  # key -> [tokens, last_update]
        self._lock = threading.Lock()
        self._last_prune = time.monotonic()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if now - self._last_prune > 300:
                idle = [k for k, b in self._buckets.items() if now - b[1] > 600]
                for k in idle:
                    del self._buckets[k]
                self._last_prune = now

            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = [self._burst, now]
                self._buckets[key] = bucket
            else:
                bucket[0] = min(self._burst, bucket[0] + (now - bucket[1]) * self._rate)
                bucket[1] = now

            if bucket[0] >= 1.0:
                bucket[0] -= 1.0
                return True
            return False


class DailyBudget:
    """Global counter that resets at UTC midnight. Thread-safe."""

    def __init__(self, limit: int):
        self._limit = limit
        self._count = 0
        self._day = self._today()
        self._lock = threading.Lock()

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def spend(self) -> bool:
        with self._lock:
            today = self._today()
            if today != self._day:
                self._day = today
                self._count = 0
            if self._count >= self._limit:
                return False
            self._count += 1
            return True


def client_ip(request: Request) -> str:
    """Best-effort client IP behind Cloudflare -> Caddy -> uvicorn."""
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# Shared instances for the LLM search path.
llm_search_limiter = PerClientRateLimiter(
    rate_per_minute=_env_int("COUNTYIQ_SEARCH_RATE_PER_MIN", 10),
    burst=_env_int("COUNTYIQ_SEARCH_BURST", 5),
)
llm_search_daily_budget = DailyBudget(_env_int("COUNTYIQ_SEARCH_DAILY_LLM_BUDGET", 2000))
