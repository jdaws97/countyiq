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
    assert "(ds.evidence - %(volatile)s::text[])" in database.sql
    assert (
        "IS NOT DISTINCT FROM (e.evidence_data - %(volatile)s::text[])" in database.sql
    )
    assert database.params == {
        "volatile": [
            "months_since_received",
            "months_since_sale",
            "months_since_meeting",
            "months_since_latest_acquisition",
        ]
    }


def test_pass3_retracts_briefs_outside_ranked_serving_set():
    database = _ProjectionCleanupDatabase([("P1",)])

    assert brief_generation._retract_unservable_briefs(database, rank_limit=500) == 1
    assert "DELETE FROM public.parcel_briefs" in database.sql
    assert "NOT EXISTS (" in database.sql
    assert "FROM ranked" in database.sql
    assert database.params == {"rank_limit": 500}


def test_signal_rebuild_retracts_evidence_before_commit_and_rolls_back_failure(
    monkeypatch,
):
    from types import SimpleNamespace
    import pytest
    from countyiq.assets.enrichment import development_signals
    from countyiq.lib.intelligence_common import RETRACT_STALE_EVIDENCE_QUERY

    monkeypatch.setattr(
        development_signals, "authorize_source_uses", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        development_signals, "source_use_is_authorized", lambda *a, **kw: True
    )
    monkeypatch.setattr(
        development_signals, "_SIGNALS", [("fixture", "INSERT fixture signals")]
    )
    for fail in (False, True):
        events = []

        class Connection:
            autocommit = True

            def commit(self):
                events.append("commit")

            def rollback(self):
                events.append("rollback")

        connection = Connection()

        class Cursor:
            rowcount = 2

            def __init__(self):
                self.connection = connection

            def execute(self, query, params=None):
                assert connection.autocommit is False
                if query == RETRACT_STALE_EVIDENCE_QUERY:
                    events.append("retract")
                    if fail:
                        raise RuntimeError("fixture retraction failed")
                else:
                    events.append("rebuild")

            def close(self):
                events.append("close")

        database = SimpleNamespace(cursor=Cursor)
        context = SimpleNamespace(
            run_id="review", log=SimpleNamespace(info=lambda *args: None)
        )
        run = development_signals.development_signals.node_def.compute_fn.decorated_fn
        if fail:
            with pytest.raises(RuntimeError, match="retraction failed"):
                run(context, database)
            assert "commit" not in events
            assert events[-3:] == ["retract", "rollback", "close"]
        else:
            result = run(context, database)
            assert events[-3:] == ["retract", "commit", "close"]
            assert result.metadata["evidence_retracted"].value == 2
        assert connection.autocommit is True
