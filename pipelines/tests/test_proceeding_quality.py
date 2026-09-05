"""Evidence-driven metadata and paid-extraction eligibility regressions."""
from datetime import date
from copy import deepcopy

import pytest

from countyiq.lib.county_config import CountyConfig, get_county_config
from countyiq.lib.parsers.public_proceedings import parse_meeting_date_from_filename
from countyiq.lib.proceeding_quality import review_metadata, source_fingerprint
from scripts.review_proceeding_metadata import build_plan

TODAY = date(2026, 9, 4)
ENTRIES = (
    ("Hanover Borough Council", "https://example.test/minutes", "borough_council"),
    ("Hanover Boro Planning Commission", "https://example.test/pc", "planning_commission"),
)
BODY = "Hanover Borough Council"


def row(text, *, url="https://example.test/July_2026.pdf", ident=1):
    return dict(id=ident, body_name=BODY, meeting_date="2026-07-01",
                proceeding_type="council", source_url="https://example.test/minutes",
                document_url=url, content_hash="source-bytes", raw_text=text + "\n" + "Meeting business. " * 35)


def review(source):
    return review_metadata(source, ENTRIES, ("wrong.test",), today=TODAY)


def test_header_corrects_month_only_date_and_preserves_source():
    source = row("Hanover Borough Council\nJuly 23, 2026\nRoll Call")
    before = deepcopy(source)
    result = review(source)
    assert (result["meeting_date"], result["date_basis"], result["status"]) == (
        "2026-07-23", "document_header", "ready")
    assert source == before


def test_previous_minutes_date_is_not_current_date():
    result = review(row("Hanover Borough Council\nJuly 23, 2026\nApproval of minutes June 25, 2026"))
    assert result["status"] == "ready"
    assert result["meeting_date"] == "2026-07-23"


def test_month_only_filename_does_not_manufacture_first_day():
    result = review(row("Hanover Borough Council\nMeeting minutes\nRoll call"))
    assert result["meeting_date"] is None
    assert "exact_meeting_date_unverified" in result["issues"]


def test_conflicting_document_years_are_held():
    result = review(row("7/14/2025\nHanover Borough Council\nJuly 14, 2026\nRoll call"))
    assert result["meeting_date"] is None
    assert "conflicting_header_dates" in result["issues"]


def test_header_filename_conflict_is_held():
    result = review(row("Hanover Borough Council\nJuly 23, 2026\nRoll call",
                        url="https://example.test/2026-07-30.pdf"))
    assert result["status"] == "review_required"
    assert "header_filename_date_conflict" in result["issues"]


def test_actual_board_replaces_catchall_archive_body():
    result = review(row("Hanover Planning Commission\nJuly 23, 2026\nRoll call"))
    assert result["status"] == "ready"
    assert result["body_name"] == "Hanover Boro Planning Commission"
    assert result["proceeding_type"] == "planning_commission"


@pytest.mark.parametrize("header,issue", [
    ("Guthrie Library Board of Governors\nJuly 23, 2026", "unrelated_board"),
    ("Hanover Zoning Hearing Board\nJuly 23, 2026", "primary_board_not_configured"),
    ("Hanover Borough Council\nJuly 23, 2026\nMeeting cancelled", "cancelled_meeting"),
])
def test_unfit_records_are_held(header, issue):
    assert issue in review(row(header))["issues"]


def test_mixed_packet_is_held():
    result = review(row("Hanover Borough Council\nJuly 23, 2026\nRoll call\n"
                        "AGENDA\nBusiness\nMEETING MINUTES\nJune 25, 2026"))
    assert "mixed_agenda_minutes_packet" in result["issues"]


def test_wrong_jurisdiction_cannot_become_ready_from_plausible_header():
    source = row("Hanover Borough Council\nJuly 23, 2026")
    source["source_url"] = "https://www.wrong.test/minutes"
    assert review(source)["status"] == "quarantined"


@pytest.mark.parametrize("name", [
    "Minutes_February_2026.pdf", "minutes-2026-02-30.pdf",
    "minutes-13-01-2026.pdf", "minutes-02-29-2025.pdf",
])
def test_parser_does_not_invent_invalid_or_incomplete_dates(name):
    assert parse_meeting_date_from_filename(name) is None


def test_fingerprint_detects_text_and_metadata_edits():
    source = row("Hanover Borough Council\nJuly 23, 2026")
    assert source_fingerprint(source) != source_fingerprint({**source, "raw_text": "changed"})
    assert source_fingerprint(source) != source_fingerprint({**source, "body_name": "Changed"})


def test_plan_deduplicates_only_same_verified_board_date_and_text():
    source = row("Hanover Borough Council\nJuly 23, 2026\nRoll call")
    county = CountyConfig(name="Test County", s3_prefix="test", municipality_websites=ENTRIES)
    policies = {"hanover_borough_council": dict(
        derived_product_allowed=True, allowed_origins=["https://example.test"], rights_status="conditional", review_due_on=date(2026, 11, 1))}
    plan = build_plan([source, {**source, "id": 2, "document_url": "https://example.test/alternate.pdf"}],
                      policies, county, today=TODAY)
    assert plan["statuses"] == {"ready": 1, "quarantined": 1}
    assert plan["items"][1]["review"]["duplicate_of"] == 1
    assert plan["items"][0]["action"] == "superseded"


def test_expired_policy_holds_otherwise_good_metadata():
    county = CountyConfig(name="Test County", s3_prefix="test", municipality_websites=ENTRIES)
    plan = build_plan([row("Hanover Borough Council\nJuly 23, 2026")],
        {"hanover_borough_council": dict(derived_product_allowed=True, allowed_origins=["https://example.test"], rights_status="conditional",
         review_due_on=date(2026, 1, 1))}, county, today=TODAY)
    assert "source_policy_not_released" in plan["items"][0]["review"]["issues"]


def test_pending_query_requires_metadata_release_and_past_date():
    from countyiq.assets.enrichment.proceeding_extraction import PENDING_PROCEEDINGS_QUERY
    assert "metadata_quality->>'status' = 'ready'" in PENDING_PROCEEDINGS_QUERY
    assert "pp.meeting_date <= CURRENT_DATE" in PENDING_PROCEEDINGS_QUERY


def test_replacement_sources_are_separate_from_retired_identities():
    county = get_county_config("york")
    assert len(county.rejected_proceeding_domains) == 4
    assert len(county.proceeding_source_replacements) == 8
    assert not {x[0] for x in county.proceeding_source_replacements}.intersection(
        x[0] for x in county.municipality_websites)
    assert any(name == "Penn Township Board of Commissioners"
               for name, _, _ in county.proceeding_source_replacements)


def test_incremental_duplicate_is_quarantined_against_reviewed_baseline():
    source = row("Hanover Borough Council\nJuly 23, 2026\nRoll call", ident=2)
    prior = {**source, "id": 1, "meeting_date": "2026-07-23"}
    county = CountyConfig(name="Test County", s3_prefix="test", municipality_websites=ENTRIES)
    policies = {"hanover_borough_council": dict(
        derived_product_allowed=True, allowed_origins=["https://example.test"], rights_status="conditional", review_due_on=date(2026, 11, 1))}
    plan = build_plan([source], policies, county, today=TODAY, baseline=[prior])
    assert plan["items"][0]["review"]["status"] == "quarantined"
    assert plan["items"][0]["review"]["duplicate_of"] == 1
    assert plan["duplicate_baseline"] == [{"id": 1, "fingerprint": source_fingerprint(prior)}]
    changed = build_plan([source], policies, county, today=TODAY,
                         baseline=[{**prior, "raw_text": prior["raw_text"]+" changed"}])
    assert changed != plan
    assert changed["items"][0]["review"]["status"] == "ready"


@pytest.mark.parametrize("header,issue", [
    ("Hanover Borough Council\nPublic Works, Facilities & Enhancement Committee Meeting\nJuly 23, 2026", "committee_meeting"),
    ("Minutes\nHanover Area Fire and Rescue Commission\nJuly 23, 2026\n"
     "Present: Hanover Borough Councilmen, Penn Township Commissioners", "unrelated_board"),
    ("Borough Council\nSpring Grove\nBorough Council Committee Meeting Minutes\nJuly 23, 2026", "committee_meeting"),
])
def test_council_members_or_letterhead_do_not_make_a_full_council_meeting(header, issue):
    result = review(row(header))
    assert result["status"] == "review_required"
    assert issue in result["issues"]


@pytest.mark.parametrize("url", ["https://other.test/document.pdf", "https://example.test.other.test/file.pdf", "", "/relative.pdf", "http://example.test/file.pdf"])
def test_unapproved_document_origin_cannot_receive_ready_metadata(url):
    source = row("Hanover Borough Council\nJuly 23, 2026\nRoll call", url=url)
    county = CountyConfig(name="Test County", s3_prefix="test", municipality_websites=ENTRIES)
    policies = {"hanover_borough_council": dict(derived_product_allowed=True,
        rights_status="conditional", review_due_on=date(2026,11,1), allowed_origins=["https://example.test"])}
    plan = build_plan([source], policies, county, today=TODAY)
    assert plan["items"][0]["review"]["status"] == "review_required"
    assert "source_origin_not_released" in plan["items"][0]["review"]["issues"]


def test_reviewed_document_delivery_origin_is_supported():
    source = row("Hanover Borough Council\nJuly 23, 2026\nRoll call", url="https://documents.test/file.pdf")
    county = CountyConfig(name="Test County", s3_prefix="test", municipality_websites=ENTRIES)
    policies = {"hanover_borough_council": dict(derived_product_allowed=True,
        rights_status="conditional", review_due_on=date(2026,11,1),
        allowed_origins=["https://example.test", "https://documents.test"])}
    assert build_plan([source], policies, county, today=TODAY)["items"][0]["review"]["status"] == "ready"
    source["source_url"] = "https://unreviewed.test/listing"
    assert build_plan([source], policies, county, today=TODAY)["items"][0]["review"]["status"] == "review_required"


def test_exact_future_date_is_valid_metadata_but_paid_query_waits_for_date():
    result = review(row("Hanover Borough Council\nOctober 1, 2026\nRoll call"))
    assert result["status"] == "ready"
    assert result["meeting_date"] == "2026-10-01"


def test_joint_board_workshop_cannot_be_released_as_one_board():
    source = row("Hanover Borough Council and Planning Commission\nJOINT MEETING/WORKSHOP\nJuly 23, 2026\nRoll call")
    result = review(source)
    assert result["status"] == "review_required"
    assert "joint_meeting" in result["issues"]


def test_hyphenated_document_slug_date_conflict_requires_review():
    source = row("Hanover Borough Council\nJanuary 5, 2026\nRoll call",
                 url="https://example.test/council-agenda-january-6th-2026")
    result = review(source)
    assert result["status"] == "review_required"
    assert "header_filename_date_conflict" in result["issues"]


@pytest.mark.parametrize("filename", ["council-january-6th-2026.pdf", "council_January_6_2026.pdf", "January 6, 2026 minutes.pdf"])
def test_exact_spelled_month_slug_dates_are_recognized(filename):
    assert parse_meeting_date_from_filename(filename) == "2026-01-06"


@pytest.mark.parametrize("attendance", ["Supervisor present: A. Example", "Supervisors present: A. Example", "Present: A. Example", "Attendance was as follows:"])
def test_attendance_ends_header_before_prior_meeting_references(attendance):
    source = row("Hanover Borough Council\nJuly 23, 2026\n"
                 "The meeting was called to order at 7 pm.\n" + attendance +
                 "\nThe board met in executive session on June 25, 2026.")
    result = review(source)
    assert result["status"] == "ready"
    assert result["meeting_date"] == "2026-07-23"


def test_conflicting_opening_meeting_date_is_not_hidden_by_attendance_cutoff():
    source = row("Hanover Borough Council\nJanuary 5, 2021\n"
                 "The Council met in Regular Session on Tuesday, December 5, 2021.\n"
                 "BOROUGH COUNCIL PRESENT: A. Example")
    result = review(source)
    assert result["status"] == "review_required"
    assert "conflicting_header_dates" in result["issues"]


@pytest.mark.parametrize("notice", [
    "The meeting to have been held on March 14 was cancelled because of snow.",
    "The meeting on March 14, 2017 was canceled because of snow.",
    "The March 14 meeting was cancelled due to a lack of quorum.",
    "The March 14, 2017 public meeting was cancelled due to weather.",
    "The March 14th meeting was canceled and rescheduled.",
])
def test_other_dated_meeting_cancellation_does_not_cancel_current_minutes(notice):
    source = row("Hanover Borough Council\nMarch 22, 2017\nPresent: A. Example\n"
                 "The meeting was called to order.\n" + notice)
    assert "cancelled_meeting" not in review(source)["issues"]


@pytest.mark.parametrize("notice", [
    "Meeting cancelled", "Meeting canceled", "Canceled meeting", "Cancelled meeting",
    "The March 22, 2017 public meeting was canceled.",
    "The February 30 meeting was cancelled.",
    "The March 14 minutes were approved; the meeting was cancelled.",
    "The meeting on March 22 was cancelled.",
    "The meeting scheduled for March 22, 2017 was cancelled.",
    "The minutes of March 14 were discussed; this meeting was cancelled.",
    "The meeting on February 30 was cancelled.",
])
def test_current_or_uncertain_cancellation_remains_held(notice):
    source = row("Hanover Borough Council\nMarch 22, 2017\nRoll call\n" + notice)
    assert "cancelled_meeting" in review(source)["issues"]


def test_trailing_agenda_cancellation_is_not_lost_at_header_boundary():
    source = row("Hanover Borough Council\nMarch 22, 2017\nRoll call\n"
                 "New business\nAdjournment\nMeeting cancelled at applicant request.")
    assert "cancelled_meeting" in review(source)["issues"]


@pytest.mark.parametrize("separator", ["/", " & ", " and\n"])
def test_combined_board_title_is_held_without_explicit_joint_word(separator):
    source = row("Hanover Borough Council" + separator + "Planning Commission\n"
                 "July 23, 2026\nRoll call")
    result = review(source)
    assert result["status"] == "review_required"
    assert "joint_meeting" in result["issues"]


def test_guest_board_reference_does_not_make_combined_title():
    source = row("Hanover Borough Council\nJuly 23, 2026\n"
                 "Planning Commission member A. Example attended as a guest.\nRoll call")
    assert "joint_meeting" not in review(source)["issues"]
