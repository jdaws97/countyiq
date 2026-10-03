from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from countyiq.lib.plan_review_snapshots import (
    compare_snapshots,
    make_snapshot,
    select_latest_document,
)

FIXTURE = Path(__file__).parent / "fixtures/yccd/plan-review-status-2026-08-31.pdf"
LISTING = (
    "https://www.yorkccd.org/erosion-and-sediment-control/pending-plan-review-list"
)
DOCUMENT = "https://www.yorkccd.org/wp-content/uploads/2026/08/Plan-Review-Status-8-31-2026.pdf"


def test_selects_newest_dated_pdf_and_rejects_publisher_or_date_ambiguity():
    older = DOCUMENT.replace("8-31-2026", "8-24-2026")
    html = f'<a href="{DOCUMENT}">latest</a><a href="{older}">older</a>'
    assert select_latest_document(html, LISTING) == (DOCUMENT, "2026-08-31")
    with pytest.raises(ValueError, match="publisher"):
        select_latest_document(
            f'<a href="{DOCUMENT.replace("www.yorkccd.org", "example.com")}">PDF</a>',
            LISTING,
        )
    with pytest.raises(ValueError, match="Multiple"):
        select_latest_document(
            html + f'<a href="{DOCUMENT.replace("/2026/08/", "/2026/09/")}">other</a>',
            LISTING,
        )


def test_snapshot_keeps_source_identity_without_inventing_project_links():
    snapshot = make_snapshot(
        FIXTURE.read_bytes(), document_url=DOCUMENT, expected_date="2026-08-31"
    )
    assert len(snapshot["rows"]) == 35
    assert len({row["receipt_key"] for row in snapshot["rows"]}) == 35
    assert all(row["project_match"] is None for row in snapshot["rows"])
    assert snapshot["rows"][3]["plan_name"].endswith("30 Industrial Road")
    assert snapshot["rows"][3]["permit_number"] == "PAC670868"
    with pytest.raises(ValueError, match="header date"):
        make_snapshot(
            FIXTURE.read_bytes(), document_url=DOCUMENT, expected_date="2026-08-24"
        )


def test_removed_review_is_outcome_unknown_and_later_unchanged_rows_are_not_changes():
    before = make_snapshot(
        FIXTURE.read_bytes(), document_url=DOCUMENT, expected_date="2026-08-31"
    )
    after = deepcopy(before)
    after["document_date"] = "2026-09-08"
    removed = after["rows"].pop(3)
    after["rows"][0]["administrative_date"] = "2026-09-08"
    for row in after["rows"]:
        row["page"] = 9
        row["receipt_key"] = "new-snapshot:" + row["receipt_key"]
    result = compare_snapshots(before, after)
    assert result["added"] == []
    assert result["removed_outcome_unknown"] == [removed]
    assert len(result["changed"]) == 1
    assert all(row["status"] == "in_review" for row in after["rows"])
    with pytest.raises(ValueError, match="later dated"):
        compare_snapshots(before, before)
    after["rows"].append(deepcopy(after["rows"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        compare_snapshots(before, after)


def test_pilot_is_manual_and_outside_every_scheduled_job():
    from countyiq.definitions import defs
    from countyiq.jobs import plan_review_pilot

    graph = defs.resolve_asset_graph()
    assert {
        key.to_user_string() for key in plan_review_pilot.selection.resolve(graph)
    } == {"plan_review_snapshot"}
    scheduled = {schedule.job_name for schedule in defs.schedules}
    for job in defs.jobs:
        if job.name in scheduled:
            assert "plan_review_snapshot" not in {
                key.to_user_string() for key in job.selection.resolve(graph)
            }


def test_source_policy_or_archive_failure_cannot_report_a_successful_collection(
    monkeypatch,
):
    from countyiq.assets.bulk import plan_reviews

    collect = Mock()
    monkeypatch.setattr(plan_reviews, "collect_snapshot", collect)
    authorize = Mock(side_effect=RuntimeError("source is paused"))
    monkeypatch.setattr(plan_reviews, "authorize_source", authorize)
    invoke = plan_reviews.plan_review_snapshot.op.compute_fn.decorated_fn
    context = SimpleNamespace(run_id="pilot-test")
    archive = SimpleNamespace(strict=True, archive=Mock())
    with pytest.raises(RuntimeError, match="paused"):
        invoke(context, Mock(), archive)
    collect.assert_not_called()
    archive.archive.assert_not_called()

    authorize.side_effect = None
    authorize.return_value = SimpleNamespace(
        source_key="yccd_plan_reviews", raw_retention_allowed=False
    )
    with pytest.raises(RuntimeError, match="raw retention"):
        invoke(context, Mock(), archive)
    collect.assert_not_called()

    authorize.return_value.raw_retention_allowed = True
    collect.return_value = (
        FIXTURE.read_bytes(),
        make_snapshot(
            FIXTURE.read_bytes(), document_url=DOCUMENT, expected_date="2026-08-31"
        ),
    )
    archive.archive.side_effect = RuntimeError("archive unavailable")
    with pytest.raises(RuntimeError, match="archive unavailable"):
        invoke(context, Mock(), archive)
