"""Unit tests for the read-only paid-backfill estimator."""

from __future__ import annotations

from datetime import date

import pytest

from countyiq.lib.backfill_estimator import (
    KNOWN_PRICE_PROFILES,
    _cost,
    approximate_tokens,
    build_name_clusters,
    estimate_backfill,
)


class FakeDatabase:
    def __init__(self):
        self.statements: list[str] = []

    def execute(self, sql: str, params=None):
        normalized = " ".join(sql.split())
        self.statements.append(sql)
        if "AS candidate_view_populated" in normalized:
            return [(1, 1, 0, 0, 0, 0, 0, True)]
        if "FROM staging.public_proceedings pp" in normalized:
            return [
                (
                    1,
                    "Spring Garden Township Board of Supervisors",
                    date(2026, 8, 1),
                    "board_of_supervisors",
                    "https://example.test/minutes.pdf",
                    "A" * 1_000,
                ),
                (
                    2,
                    "York City Council",
                    date(2026, 8, 2),
                    "city_council",
                    "https://example.test/minutes.docx",
                    "too short",
                ),
            ]
        if "c.relispopulated" in normalized:
            return [(True,)]
        return []

    def dict_cursor(self):  # pragma: no cover - no sampled downstream candidates
        raise AssertionError("no downstream context should be gathered in this fixture")


def test_approximate_tokens_uses_visible_four_character_rule():
    assert approximate_tokens("") == 0
    assert approximate_tokens("abcd") == 1
    assert approximate_tokens("abcde") == 2


def test_name_clusters_are_connected_components():
    clusters = build_name_clusters([
        ("A LLC", "A PROPERTIES"),
        ("A PROPERTIES", "A HOLDINGS"),
        ("B LLC", "B INC"),
    ])
    assert sorted(clusters) == [
        ["A HOLDINGS", "A LLC", "A PROPERTIES"],
        ["B INC", "B LLC"],
    ]


def test_cost_uses_per_million_rates():
    profile = KNOWN_PRICE_PROFILES["openai/gpt-5.6-luna"]
    # 1M prompt + 1M completion tokens at $0.20/$1.20.
    assert _cost(profile, 1, 1_000_000, 1_000_000) == 1.4


def test_report_counts_only_call_eligible_pass0_rows_and_is_select_only():
    database = FakeDatabase()
    report = estimate_backfill(database, sample_size=10)

    pass0 = report["passes"][0]
    assert pass0["key"] == "pass0"
    assert pass0["units_min"] == 1
    assert pass0["units_max"] == 1
    assert pass0["planning_calls_min"] == 1
    assert pass0["planning_calls_max"] == 1
    assert pass0["details"]["unsupported_without_text"] == 1
    assert pass0["sampled_units"] == 1
    assert report["read_only"] is True

    assert database.statements
    executable_sql = [
        "\n".join(
            line for line in statement.splitlines()
            if not line.lstrip().startswith("--")
        ).upper()
        for statement in database.statements
    ]
    assert all("SELECT " in statement or "WITH " in statement for statement in executable_sql)
    assert not any(
        word in statement
        for statement in executable_sql
        for word in ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE ")
    )


def test_disabled_runtime_gate_does_not_zero_hypothetical_backfill(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_PASS0_ENABLED", "false")

    report = estimate_backfill(FakeDatabase(), sample_size=10)

    pass0 = report["passes"][0]
    assert pass0["enabled_in_environment"] is False
    assert pass0["planning_calls_min"] == 1
    assert pass0["planning_cost_min"] > 0


def test_report_fails_closed_when_pass1_candidate_view_is_unpopulated():
    class UnpopulatedDatabase(FakeDatabase):
        def execute(self, sql: str, params=None):
            if "c.relispopulated" in " ".join(sql.split()):
                self.statements.append(sql)
                return [(False,)]
            return super().execute(sql, params)

    with pytest.raises(RuntimeError, match="deterministic_enrichment_refresh"):
        estimate_backfill(UnpopulatedDatabase(), sample_size=10)
