"""The free value gate must never hide narrative property decisions."""

from countyiq.lib.municipal_evidence import bind_review, review_prompt
from countyiq.lib.municipal_value import source_value
from countyiq.lib.pass0_source import index_source


def test_accounting_only_document_skips_without_reading_vendor_rows():
    document = index_source(
        "Township finance packet\nBills List\nName Account Amount\n"
        "Engineer Cly Road Expense 1,234.00\n"
    )
    value = source_value(document)
    assert value.skip_reason == "accounting_table_only"
    assert "Cly Road Expense" not in review_prompt([], document)


def test_short_project_decision_before_appendix_is_not_filtered_out():
    document = index_source(
        "Subdivision plan approved subject to drainage changes.\n"
        "Expenses by Vendor Detail\nDate Account Paid Balance\n"
        "2026-09-01 Sewer study 450.00 450.00\n"
    )
    value = source_value(document)
    assert value.skip_reason is None
    assert value.excluded_lines == frozenset({2, 3, 4})
    assert "Subdivision plan approved" in review_prompt([], document)
    rejected = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "Sewer study",
                    "passages": [[4, 4]],
                }
            ]
        },
        [],
        document,
    )
    assert rejected["status"] == "partial"
    assert not rejected["cards"]


def test_narrative_resumes_after_a_financial_table_without_renumbering():
    document = index_source(
        "Bills List\nName Account Amount\nVendor Supplies 12.00\n"
        "NEW BUSINESS\nMotion to approve School Road bridge contract.\n"
    )
    value = source_value(document)
    assert value.excluded_lines == frozenset({1, 2, 3})
    assert value.skip_reason is None
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "School Road bridge",
                    "passages": [[5, 5]],
                }
            ]
        },
        [],
        document,
    )
    assert result["status"] == "complete"
    assert result["cards"][0]["passages"][0]["start"] == document.units[4].start


def test_bill_approval_heading_does_not_remove_the_following_project_decision():
    document = index_source(
        "Approve the Bills List\nName Account Amount\n"
        "Motion to award water main project for $400,000.\n"
    )
    assert not source_value(document).excluded_lines


def test_cancelled_meeting_is_distinct_from_cancelled_property_permission():
    cancelled = index_source(
        "York Township\nZoning Hearing Board\nAugust 25, 2026\nCancelled\n"
    )
    permit = index_source("Zoning Hearing Board\n14 Main Street permit cancelled\n")
    assert source_value(cancelled).skip_reason == "cancelled_meeting_notice"
    assert source_value(permit).skip_reason is None
