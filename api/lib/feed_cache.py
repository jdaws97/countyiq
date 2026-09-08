"""Bounded feed-page reuse tied to a transactional database revision."""

import json
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime
from threading import Lock


class FeedPageCache:
    """Keep independent copies so presentation cannot mutate cached evidence."""

    def __init__(self, capacity: int = 32, max_bytes: int = 16 * 1024 * 1024):
        self.capacity = capacity
        self.max_bytes = max_bytes
        self._bytes = 0
        self._pages: OrderedDict[str, tuple[tuple, datetime, object]] = OrderedDict()
        self._sizes: dict[str, int] = {}
        self._lock = Lock()

    def get(self, key: str, revision: tuple, now: datetime):
        with self._lock:
            entry = self._pages.get(key)
            if entry is None:
                return None
            stored_revision, expires_at, value = entry
            if stored_revision != revision or now >= expires_at:
                del self._pages[key]
                self._bytes -= self._sizes.pop(key)
                return None
            self._pages.move_to_end(key)
            return deepcopy(value)

    def put(self, key: str, revision: tuple, expires_at: datetime, value) -> None:
        size = len(json.dumps(value, default=str).encode("utf-8"))
        with self._lock:
            self._pages.pop(key, None)
            self._bytes -= self._sizes.pop(key, 0)
            if size > self.max_bytes:
                return
            self._pages[key] = (revision, expires_at, deepcopy(value))
            self._sizes[key] = size
            self._bytes += size
            self._pages.move_to_end(key)
            while len(self._pages) > self.capacity or self._bytes > self.max_bytes:
                removed, _ = self._pages.popitem(last=False)
                self._bytes -= self._sizes.pop(removed)


feed_pages = FeedPageCache()


def read_feed_revision(cursor) -> tuple[tuple, datetime]:
    """Read the serving revision inside the caller's consistent snapshot."""
    cursor.execute(
        "SELECT generation, revision, CURRENT_DATE AS policy_date, NOW() AS checked_at "
        "FROM meta.feed_cache_revision"
    )
    state = cursor.fetchone()
    revision = (str(state["generation"]), state["revision"], state["policy_date"])
    return revision, state["checked_at"]
