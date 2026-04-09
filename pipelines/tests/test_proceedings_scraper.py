"""Unit tests for public proceedings scraper helper functions.

Tests the pure helpers without requiring a database connection.
The _already_exists and _content_hash_exists functions require DB
and are integration-tested separately.
"""

import hashlib

from countyiq.assets.scrapers.public_proceedings import _safe_name


class TestSafeName:
    def test_simple_name(self):
        assert _safe_name("Carroll Twp Board of Supervisors") == "carroll_twp_board_of_supervisors"

    def test_special_characters(self):
        assert _safe_name("York City Zoning Hearing Board") == "york_city_zoning_hearing_board"

    def test_strips_leading_trailing(self):
        result = _safe_name("  Hellam Twp  ")
        assert not result.startswith("_")
        assert not result.endswith("_")


class TestContentHash:
    """Verify that our SHA-256 approach produces deterministic, distinct hashes."""

    def test_same_content_same_hash(self):
        data = b"Hello World PDF Content"
        h1 = hashlib.sha256(data).hexdigest()
        h2 = hashlib.sha256(data).hexdigest()
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = hashlib.sha256(b"January 2026 Minutes").hexdigest()
        h2 = hashlib.sha256(b"February 2026 Minutes").hexdigest()
        assert h1 != h2

    def test_hash_is_64_char_hex(self):
        h = hashlib.sha256(b"test").hexdigest()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
