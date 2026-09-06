from datetime import date
import pytest
from api.lib.project_status import summarize_project, exact_date


def event(key, day, decision=None, **details):
    return {
        "event_key": key,
        "event_date": day,
        "what_happened": "Plan discussed",
        "what_happens_next": "Verify revised submission",
        "sources": [
            {
                "evidence_id": f"e-{key}",
                "label": "Council",
                "details": {"decision": decision, **details},
            }
        ],
    }


def test_later_hearing_does_not_repeat_old_approval_as_current():
    result = summarize_project(
        [event("a", "2026-01-01", "approved"), event("b", "2026-02-01")]
    )
    assert result["status"] == "Later activity recorded; verify decision status"
    assert result["decisions"][0]["event_key"] == "a"
    assert "next_verification" not in result


def test_conflicts_conditions_and_ambiguous_dates_remain_explicit():
    result = summarize_project(
        [
            event(
                "a",
                "2026-01-01",
                "approved",
                conditions=["Submit drainage plan"],
                upcoming_date="next month",
            ),
            event("b", "2026-01-01", "denied"),
        ]
    )
    assert result["status"].startswith("Conflicting")
    assert result["conditions"][0]["status"].startswith("Satisfaction not established")
    assert result["milestones"][0]["date"] is None


def test_future_agenda_and_old_deadline_are_not_completed_decisions():
    result = summarize_project(
        [
            event("future", "2027-01-01", "approved"),
            event("old", "2026-01-01", upcoming_date="2026-02-01"),
        ],
        today=date(2026, 3, 1),
    )
    assert not result["decisions"]
    assert result["milestones"][0]["status"].startswith("Date passed")
    assert exact_date("2026-02-30") is None


def test_milestone_dates_require_a_full_unambiguous_date():
    assert exact_date("September 20, 2026") == "2026-09-20"
    assert exact_date("Sep 20 2026") == "2026-09-20"
    assert exact_date("September 20") is None
    assert exact_date("9/10/26") is None


def test_scheduled_and_recommended_records_never_become_completed_decisions():
    result = summarize_project(
        [
            event("agenda", "2026-01-01", "approved", record_status="scheduled"),
            event("referral", "2026-02-01", "approved", record_status="recommendation"),
        ],
        today=date(2026, 9, 4),
    )
    assert result["decisions"] == []


def test_normalized_record_dates_order_decisions_without_mutating_sources():
    records = [
        event("old", "January 2, 2026", "approved"),
        event("new", "2026-02-01", "denied"),
    ]
    result = summarize_project(records, today=date(2026, 3, 1))
    assert result["status"] == "Denial recorded"
    assert [d["record_date"] for d in result["decisions"]] == [
        "2026-02-01",
        "2026-01-02",
    ]
    assert result["history_incomplete"] is False
    assert records[0]["event_date"] == "January 2, 2026"


def test_same_day_decisions_with_different_date_spellings_conflict():
    result = summarize_project(
        [
            event("one", "January 2, 2026", "approved"),
            event("two", "2026-01-02", "denied"),
        ],
        today=date(2026, 3, 1),
    )
    assert result["status"].startswith("Conflicting")
    assert result["as_of"] == "2026-01-02"


def test_future_and_undated_conditions_do_not_imply_adoption():
    records = [
        event("future", "2027-01-01", "approved", conditions=["Build sidewalk"]),
        event("undated", None, "approved", conditions=["Revise drainage"]),
    ]
    result = summarize_project(records, today=date(2026, 3, 1))
    assert result["decisions"] == []
    assert all(
        c["status"] == "Adoption not established by this record"
        for c in result["conditions"]
    )
    assert result["history_incomplete"] is True


def test_scopes_and_authorities_do_not_conflate_independent_decisions():
    records = [
        event(
            "plan",
            "2026-01-01",
            "denied",
            record_status="decision",
            decision_scope="plan",
            decision_authority="Council",
        ),
        event(
            "bond",
            "2026-01-01",
            "approved",
            record_status="decision",
            decision_scope="bond",
            decision_authority="Council",
        ),
    ]
    result = summarize_project(records, today=date(2026, 3, 1))
    assert result["status"].startswith("Multiple scoped decisions")
    assert {d["scope"] for d in result["decisions"]} == {"plan", "bond"}
    records.append(
        event(
            "other",
            "2026-01-01",
            "approved",
            record_status="decision",
            decision_scope="plan",
            decision_authority="Council",
        )
    )
    assert summarize_project(records, today=date(2026, 3, 1))["status"].startswith(
        "Conflicting"
    )


def test_milestones_and_conditions_link_to_their_own_source_receipts():
    record = event(
        "bond",
        "2026-01-01",
        "approved",
        record_status="decision",
        decision_scope="bond",
        decision_authority="Council",
        conditions=["Submit inspection"],
        milestones=[
            {"kind": "bid_opening", "text": "June 1, 2026", "date": "2026-06-01"},
            {"kind": "completion", "text": "November 30, 2026", "date": "2026-11-30"},
        ],
    )
    for marker in ["decision", "condition:0", "milestone:0", "milestone:1"]:
        record["sources"].append(
            {"evidence_id": marker, "details": {"supports": [marker]}}
        )
    result = summarize_project([record], today=date(2026, 9, 1))
    assert result["status"] == "Bond: Approval recorded"
    assert result["decisions"][0]["evidence_id"] == "decision"
    assert result["conditions"][0]["evidence_id"] == "condition:0"
    assert [m["evidence_id"] for m in result["milestones"]] == [
        "milestone:0",
        "milestone:1",
    ]
    assert [m["kind"] for m in result["milestones"]] == ["bid_opening", "completion"]
    assert result["milestones"][0]["status"].startswith("Date passed")
    assert result["milestones"][1]["status"] == "Stated date"


def test_removed_is_not_continued_or_approved():
    record = event("removed", "2026-01-01", None, record_status="removed")
    result = summarize_project([record], today=date(2026, 3, 1))
    assert result["status"].startswith("Removed from agenda")
    assert not result["decisions"]


@pytest.mark.parametrize("withdrawal_key", ["a", "z"])
def test_same_day_withdrawal_and_decision_do_not_choose_key_order(withdrawal_key):
    records = [
        event(withdrawal_key, "2026-01-01", record_status="withdrawn"),
        event(
            "m",
            "2026-01-01",
            "approved",
            record_status="decision",
            decision_scope="plan",
        ),
    ]
    result = summarize_project(records, today=date(2026, 3, 1))
    assert result["status"] == "Multiple actions recorded — verify scope and sequence"
    assert len(result["decisions"]) == 1


def test_later_dated_withdrawal_can_supersede_prior_decision():
    result = summarize_project(
        [
            event("approval", "2026-01-01", "approved"),
            event("withdrawal", "2026-01-02", record_status="withdrawn"),
        ],
        today=date(2026, 3, 1),
    )
    assert result["status"] == "Withdrawal recorded"


def test_same_day_conflicting_decisions_are_not_hidden_by_withdrawal():
    records = [
        event("a", "2026-01-01", "approved"),
        event("b", "2026-01-01", "denied"),
        event("z", "2026-01-01", record_status="withdrawn"),
    ]
    assert summarize_project(records, today=date(2026, 3, 1))["status"].startswith(
        "Conflicting"
    )
