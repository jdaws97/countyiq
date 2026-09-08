"""Feed reuse cannot cross revisions, expiry, or mutable presentation copies."""

from datetime import UTC, datetime, timedelta

from api.lib.feed_cache import FeedPageCache


def test_revision_change_and_expiry_retract_cached_pages():
    cache = FeedPageCache()
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=1)
    cache.put("page", (1,), expires, [{"title": "Current"}])
    assert cache.get("page", (1,), now)
    assert cache.get("page", (2,), now) is None
    cache.put("page", (2,), expires, [])
    assert cache.get("page", (2,), expires) is None


def test_presentation_changes_do_not_modify_cached_evidence():
    cache = FeedPageCache()
    now = datetime.now(UTC)
    rows = [{"sources": [{"text": "Original"}]}]
    cache.put("page", (1,), now + timedelta(minutes=1), rows)
    rows[0]["sources"].clear()
    displayed = cache.get("page", (1,), now)
    displayed[0]["sources"].clear()
    assert cache.get("page", (1,), now)[0]["sources"] == [{"text": "Original"}]


def test_cache_evicts_old_pages_and_rejects_oversized_pages():
    cache = FeedPageCache(capacity=1, max_bytes=100)
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=1)
    cache.put("first", (1,), expires, ["first"])
    cache.put("second", (1,), expires, ["second"])
    assert cache.get("first", (1,), now) is None
    assert cache.get("second", (1,), now) == ["second"]
    cache.put("large", (1,), expires, ["x" * 101])
    assert cache.get("large", (1,), now) is None
