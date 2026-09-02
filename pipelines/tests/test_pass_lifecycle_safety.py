"""Regression coverage for capped-pass fairness and serving projections."""

from datetime import UTC, datetime

from countyiq.assets.enrichment import (
    brief_generation,
    county_narratives,
    signal_validation_batched,
)
from countyiq.lib.intelligence_common import (
    fetch_prior_pass_attempts,
    pass_attempt_priority,
)


class _AttemptDatabase:
    def execute(self, sql, params):
        assert "last_run_at" in sql
        assert params == {"pass_number": 3}
        return [
            {"pidn": "recent", "last_run_at": datetime(2026, 8, 3, tzinfo=UTC)},
            ("old", datetime(2026, 8, 1, tzinfo=UTC)),
            ("never-timestamped", None),
        ]


def test_capped_passes_prioritize_never_attempted_then_oldest_attempt():
    attempts = fetch_prior_pass_attempts(_AttemptDatabase(), pass_number=3)
    subjects = ["recent", "new", "old", "never-timestamped"]

    ordered = sorted(
        subjects,
        key=lambda subject: pass_attempt_priority(subject, attempts),
    )

    assert ordered == ["never-timestamped", "new", "old", "recent"]


class _NarrativeDatabase:
    def __init__(self):
        self.sql = ""

    def execute(self, sql, _params):
        self.sql = sql
        return [("same-hash",)]


def test_pass4_hash_skip_requires_a_live_serving_projection():
    database = _NarrativeDatabase()

    assert county_narratives._get_prior_hash(database, "narrative:key") == "same-hash"
    assert "JOIN public.county_narratives" in database.sql
    assert "expires_at" in database.sql


class _ProjectionCleanupDatabase:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = None

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params
        return self.rows


def test_pass2_retracts_missing_or_changed_signal_evidence():
    database = _ProjectionCleanupDatabase([("P1", "vacancy")])

    assert signal_validation_batched._retract_stale_evidence(database) == 1
    assert "DELETE FROM public.evidence" in database.sql
    assert "ds.evidence IS NOT DISTINCT FROM e.evidence_data" in database.sql


def test_pass3_retracts_briefs_outside_ranked_serving_set():
    database = _ProjectionCleanupDatabase([("P1",)])

    assert brief_generation._retract_unservable_briefs(
        database, rank_limit=500
    ) == 1
    assert "DELETE FROM public.parcel_briefs" in database.sql
    assert "NOT EXISTS (" in database.sql
    assert "FROM ranked" in database.sql
    assert database.params == {"rank_limit": 500}
