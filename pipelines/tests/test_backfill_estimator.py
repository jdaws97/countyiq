"""Unit tests for the read-only paid-backfill estimator."""

from __future__ import annotations

from datetime import date
from itertools import pairwise

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
                    "zoning " + "A" * 1_000,
                    "hash-1",
                ),
                (
                    2,
                    "York City Council",
                    date(2026, 8, 2),
                    "city_council",
                    "https://example.test/minutes.docx",
                    "too short",
                    "hash-2",
                ),
                (
                    3,
                    "Dover Township Board of Supervisors",
                    date(2026, 8, 3),
                    "board_of_supervisors",
                    "https://example.test/routine.pdf",
                    "budget personnel utilities " * 50,
                    "hash-3",
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
    clusters = build_name_clusters(
        [
            ("A LLC", "A PROPERTIES"),
            ("A PROPERTIES", "A HOLDINGS"),
            ("B LLC", "B INC"),
        ]
    )
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
    assert pass0["details"]["deterministic_prefilter_skips"] == 1
    assert pass0["sampled_units"] == 1
    assert pass0["runtime_max_input_tokens_per_call"] > pass0["average_input_tokens"]
    assert pass0["retry_ceiling_cost"] > pass0["details"]["provider_retry_ceiling_cost"]
    assert report["read_only"] is True

    assert database.statements
    executable_sql = [
        "\n".join(
            line
            for line in statement.splitlines()
            if not line.lstrip().startswith("--")
        ).upper()
        for statement in database.statements
    ]
    assert all(
        "SELECT " in statement or "WITH " in statement for statement in executable_sql
    )
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


def test_records_profile_prices_evidence_reads_and_omits_inferred_passes():
    report = estimate_backfill(FakeDatabase(), sample_size=10, profile="records")

    assert report["profile"] == "records"
    pass0, pass1, pass2, pass3, pass3b = report["passes"]
    assert pass0["key"] == "pass0"
    assert pass0["planning_calls_min"] == 2
    assert pass0["planning_calls_max"] == 3
    assert pass0["retry_ceiling_calls"] == 6
    assert pass0["runtime_reservation_calls"] == 6
    assert pass0["details"]["native_text_documents"] == 2
    assert pass0["details"]["needs_ocr_documents"] == 1
    assert pass0["details"]["observed_eligible_records_per_month_last_365_days"] >= 0
    assert pass1["planning_calls_max"] >= 0
    for estimate in (pass2, pass3, pass3b):
        assert estimate["planning_calls_min"] == 0
        assert estimate["planning_calls_max"] == 0
        assert estimate["details"]["records_profile_omitted"] is True


def test_records_profile_value_gate_and_model_routing_are_priced_separately(
    monkeypatch,
):
    from countyiq.lib import backfill_estimator as estimator

    ordinary_substantive_source = "zoning application " + "x" * 300
    large_substantive_source = "zoning application " + "x" * 16_001
    financial_substantive_source = (
        "road project financing " + " ".join("$1,000" for _ in range(12)) + " x" * 100
    )
    accounting_only_source = "\n".join(
        [
            "Expenses by Vendor Detail",
            "Vendor Account Amount",
            "Acme Supplies 100-100 $1,200.00",
            "County Utility 100-200 $2,300.00",
            "Road Materials 100-300 $3,400.00",
            "Vendor detail continued " + "x" * 100,
        ]
    )

    class MixedEvidenceDatabase(FakeDatabase):
        def execute(self, sql: str, params=None):
            if "FROM staging.public_proceedings pp" in " ".join(sql.split()):
                return [
                    (
                        1,
                        "Example Township Board",
                        date(2026, 8, 1),
                        "board_of_supervisors",
                        "https://example.test/ordinary.pdf",
                        ordinary_substantive_source,
                        "ordinary-hash",
                    ),
                    (
                        2,
                        "Example Township Board",
                        date(2026, 8, 1),
                        "board_of_supervisors",
                        "https://example.test/large.pdf",
                        large_substantive_source,
                        "large-hash",
                    ),
                    (
                        3,
                        "Example Township Board",
                        date(2026, 8, 2),
                        "board_of_supervisors",
                        "https://example.test/financial.pdf",
                        financial_substantive_source,
                        "financial-hash",
                    ),
                    (
                        4,
                        "Example Township Board",
                        date(2026, 8, 2),
                        "board_of_supervisors",
                        "https://example.test/accounting.pdf",
                        accounting_only_source,
                        "accounting-hash",
                    ),
                ]
            return super().execute(sql, params)

    monkeypatch.setattr(
        estimator, "resolve_pass_model", lambda pass_number: "z-ai/glm-5.3-flash"
    )

    report = estimate_backfill(
        MixedEvidenceDatabase(), sample_size=10, profile="records"
    )
    pass0 = report["passes"][0]

    assert pass0["planning_calls_min"] == 3
    assert pass0["planning_calls_max"] == 3
    assert pass0["retry_ceiling_calls"] == 6
    assert pass0["max_output_tokens_per_call"] == 8_192
    assert pass0["details"]["model_counts"] == {
        "z-ai/glm-5.3-flash": 3,
    }
    assert pass0["details"]["output_tokens_by_model"] == {
        "z-ai/glm-5.3-flash": 1_500,
    }
    assert set(pass0["details"]["planning_cost_by_model"]) == {
        "z-ai/glm-5.3-flash",
    }
    assert pass0["details"]["value_gate_skipped_documents"] == 1
    assert pass0["details"]["value_gate_skip_reasons"] == {"accounting_table_only": 1}
    assert pass0["details"]["excluded_accounting_characters"] > 0
    assert pass0["planning_cost_min"] > 0
    assert pass0["planning_cost_max"] == pass0["planning_cost_min"]


def test_evidence_mode_never_applies_structured_keyword_skip(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_PASS0_MODE", "evidence")

    report = estimate_backfill(FakeDatabase(), sample_size=10)

    pass0 = report["passes"][0]
    assert pass0["label"] == "Pass 0 municipal evidence reading"
    assert pass0["details"]["native_text_documents"] == 2
    assert "deterministic_prefilter_skips" not in pass0["details"]


def test_records_evidence_reads_each_large_native_document_once_without_truncation():
    raw_text = "\n".join(f"Record line {number} " + "x" * 16_000 for number in range(3))

    class MultiWindowDatabase(FakeDatabase):
        def execute(self, sql: str, params=None):
            if "FROM staging.public_proceedings pp" in " ".join(sql.split()):
                return [
                    (
                        1,
                        "Example Township Board",
                        date(2026, 8, 1),
                        "board_of_supervisors",
                        "https://example.test/meeting.pdf",
                        raw_text,
                        "long-hash",
                    )
                ]
            return super().execute(sql, params)

    report = estimate_backfill(MultiWindowDatabase(), sample_size=10, profile="records")
    pass0 = report["passes"][0]

    assert pass0["details"]["complete_source_read_calls"] == 1
    assert pass0["planning_calls_min"] == 1
    assert pass0["planning_calls_max"] == 1
    assert pass0["average_input_tokens"] > 10_000


def test_backfill_profile_rejects_unknown_value():
    with pytest.raises(
        ValueError, match="profile must be intelligence, records, or explained-records"
    ):
        estimate_backfill(FakeDatabase(), profile="unsupported")


def test_evidence_ceiling_tracks_output_limit_and_attribution_correction(monkeypatch):
    class NativeDatabase(FakeDatabase):
        def execute(self, sql, params=None):
            rows = super().execute(sql, params)
            if "FROM staging.public_proceedings pp" in " ".join(sql.split()):
                return [row for row in rows if len(row[5]) >= 200]
            return rows

    monkeypatch.setenv("COUNTYIQ_PASS0_MODE", "evidence")
    monkeypatch.setenv("COUNTYIQ_PASS0_MODEL", "openai/gpt-5.6-luna")
    monkeypatch.setenv("COUNTYIQ_PASS0_MAX_TOKENS", "8192")
    ordinary = estimate_backfill(NativeDatabase(), profile="records")["passes"][0]
    monkeypatch.setenv("COUNTYIQ_PASS0_MAX_TOKENS", "128000")
    larger = estimate_backfill(NativeDatabase(), profile="records")["passes"][0]
    assert larger["max_output_tokens_per_call"] == 128000
    assert larger["max_output_tokens_per_call"] > ordinary["max_output_tokens_per_call"]
    assert larger["retry_ceiling_calls"] == 2 * larger["planning_calls_max"]
    assert larger["runtime_reservation_calls"] == larger["retry_ceiling_calls"]
    assert larger["retry_ceiling_cost"] > ordinary["retry_ceiling_cost"]


def test_explained_records_profile_does_not_treat_unmeasured_summaries_as_free():
    report = estimate_backfill(
        FakeDatabase(), sample_size=10, profile="explained-records"
    )
    _, _, pass2, pass3, pass3b = report["passes"]
    assert pass2["planning_calls_max"] == pass3b["planning_calls_max"] == 0
    assert pass3["model"] == "openai/gpt-5.6-luna"
    assert pass3["planning_cost_max"] is None
    assert report["totals"]["planning_cost_max"] is None
    assert pass3["details"]["runtime_mode_required"] == "COUNTYIQ_PASS3_MODE=records"


def test_pass3_estimate_binds_the_runtime_rank_limit(monkeypatch):
    class ParameterCheckingDatabase(FakeDatabase):
        def execute(self, sql: str, params=None):
            if "LIMIT %(rank_limit)s" in sql:
                assert params == {"rank_limit": 123}
                self.statements.append(sql)
                return []
            return super().execute(sql, params)

    monkeypatch.setenv("COUNTYIQ_PASS3_RANK_LIMIT", "123")
    estimate_backfill(ParameterCheckingDatabase(), sample_size=10)


def test_report_fails_closed_when_pass1_candidate_view_is_unpopulated():
    class UnpopulatedDatabase(FakeDatabase):
        def execute(self, sql: str, params=None):
            if "c.relispopulated" in " ".join(sql.split()):
                self.statements.append(sql)
                return [(False,)]
            return super().execute(sql, params)

    with pytest.raises(RuntimeError, match="deterministic_enrichment_refresh"):
        estimate_backfill(UnpopulatedDatabase(), sample_size=10)


def test_pass1_estimate_excludes_runtime_context_deferrals(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_PASS1_SCOPE", "all")
    from contextlib import nullcontext

    from countyiq.lib import backfill_estimator as estimator

    large = [f"LARGE {n} LLC" for n in range(41)]
    pairs = list(pairwise(large)) + [
        ("SMALL A LLC", "SMALL B LLC"),
        ("LONG A LLC", "LONG B LLC"),
    ]
    gathered = []

    class CandidateDatabase(FakeDatabase):
        def execute(self, query, params=None):
            return (
                pairs
                if query == estimator.CANDIDATE_CLUSTERS_QUERY
                else super().execute(query, params)
            )

        def dict_cursor(self):
            return nullcontext(None)

    def gather(cursor, names):
        gathered.append(names)
        return {"names": names}

    monkeypatch.setattr(estimator, "gather_cluster_records", gather)
    monkeypatch.setattr(
        estimator,
        "build_entity_cluster_prompt",
        lambda records: (
            "x" * 64_001 if records["names"][0].startswith("LONG") else "small context"
        ),
    )
    result = estimator._estimate_pass1(CandidateDatabase(), sample_size=10)

    assert all(len(names) == 2 for names in gathered)
    assert result.units_min == result.units_max == result.sampled_units == 1
    assert result.details["clusters_deferred_name_limit"] == 1
    assert result.details["sampled_clusters_deferred_character_limit"] == 1
    assert result.details["unsampled_contexts"] == 0
