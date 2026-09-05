import json
from pathlib import Path
from datetime import date
from copy import deepcopy
import pytest

from countyiq.lib.proceeding_contract import contract_errors, details_for, resolve_project_keys
from countyiq.lib.intelligence_events import build_development_event
from countyiq.lib.intelligence_integrity import validate_pass0_extractions

FIXTURES = {x["source_id"]: x for x in json.loads(
    (Path(__file__).parents[1] / "eval/fixtures/municipal_pilot_regressions.json").read_text())}


def item(quote="The board approved the application.", **changes):
    fields = ["what_happened", "decision", "conditions", "event_date_text",
              "upcoming_date", "application_ids", "project_reference", "parcel_references"]
    return dict(supporting_text=quote, evidence_spans=[dict(quote=quote, fields=fields)],
                record_status="decision", what_happened="The board approved the application.",
                decision="approved", event_date=None, event_date_text=None,
                upcoming_date=None, upcoming_date_iso=None, application_ids=[],
                project_reference=None, parcel_references=[], **changes)


def test_separate_contiguous_passages_pass_but_stitched_quotes_fail():
    source = "Acme applied at 123 Main St.\nOther business happened.\nThe board approved the application."
    row = item()
    row["evidence_spans"].append(dict(quote="Acme applied at 123 Main St.", fields=["parcel_references"]))
    row["parcel_references"] = ["123 Main St."]
    assert not contract_errors(row, source)
    row["evidence_spans"][1]["quote"] = "Acme applied at 123 Main St. ... The board approved the application."
    assert any("not present" in e for e in contract_errors(row, source))


def test_exact_footer_is_not_a_filed_project():
    fixture = FIXTURES[1174]
    baseline = fixture["baseline_extractions"][2]
    quote = baseline["supporting_text"]
    row = item(quote)
    row.update(baseline, record_status="scheduled",
               evidence_spans=[dict(quote=quote,fields=["what_happened","upcoming_date","application_ids"])],
               application_ids=["CUH 2026-10"])
    assert any("boilerplate" in e for e in contract_errors(row, fixture["source_text"]))


@pytest.mark.parametrize("status", ["scheduled", "recommendation"])
def test_scheduled_and_recommended_are_not_decisions(status):
    row = item()
    row["record_status"] = status
    assert any("completed decision" in e for e in contract_errors(row, row["supporting_text"]))


def test_generic_calendar_not_a_case_deadline():
    quote = "Schedule CUH 2026-8.\nConditional Use Hearing Application & Plan Submission August 3, 2026."
    row = item(quote)
    row.update(decision=None, record_status="scheduled", what_happened="The agenda lists CUH 2026-8.",
               upcoming_date="August 3, 2026", upcoming_date_iso="2026-08-03")
    assert any("generic submission" in e for e in contract_errors(row, quote))


def test_no_invented_reference_and_date():
    row = item()
    row.update(parcel_references=["999 Imaginary Road"], event_date="2026-07-20", event_date_text="July 20")
    errors=contract_errors(row,row["supporting_text"])
    assert any("reference absent" in e for e in errors)
    assert any("complete explicit source date" in e for e in errors)


def test_historical_decision_date_and_each_span_survive_event_building():
    quote = "The board approved the application on July 20, 2026."
    extraction=item(quote)
    extraction.update(event_date="2026-07-20",event_date_text="July 20, 2026")
    extraction["evidence_spans"].append(dict(quote="The application concerns 123 Main St.",fields=["parcel_references"]))
    extraction["parcel_references"]=["123 Main St."]
    event=build_development_event(dict(id=1,proceeding_id=2,body_name="York City Planning Commission",
        meeting_date=date(2026,8,5),extraction_details=details_for(extraction),**extraction))
    assert event["event_date"]=="2026-07-20"
    assert len(event["source_evidence"])==2
    assert event["source_evidence"][0]["details"]["meeting_date"]=="2026-08-05"
    assert "decision" not in event["source_evidence"][1]["details"]


def test_scheduled_event_does_not_acquire_hearing_or_approval():
    extraction=item("The agenda lists Acme.")
    extraction.update(record_status="scheduled",decision=None,what_happened="The agenda lists Acme.",event_tags=[])
    event=build_development_event(dict(id=1,proceeding_id=2,extraction_type="development_proposal",
        meeting_date=date(2026,8,5),extraction_details=details_for(extraction),**extraction))
    assert not ({"approval","hearing"} & set(event["event_tags"]))


def project(id, body, app, name=None):
    return dict(id=id,body_name=body,meeting_date="2026-08-05",project_name="Model title changes freely",
        extraction_details=dict(contract_version=2,application_ids=[app],project_reference=name))


def test_application_identity_survives_title_and_board_changes():
    a=project(1,"West Manchester Twp Planning Commission","ZHB 26-01")
    b=project(2,"West Manchester Twp Zoning Hearing Board","ZHB 26-01")
    b["project_name"]="A different generated title"
    keys, aliases=resolve_project_keys([a,b])
    assert keys[1]==keys[2]
    later=project(3,b["body_name"],"ZHB 26-01","Sprich repair shop")
    new, additions=resolve_project_keys([later],aliases)
    assert new[3]==keys[1]


def test_source_named_plan_connects_cross_board_applications():
    a=project(1,"Conewago Twp Planning Commission","Case 05-2026","Prosper Meadows development")
    b=project(2,"Conewago Twp Zoning Hearing Board","Case 05-2026","Prosper Meadows development")
    keys,_=resolve_project_keys([a,b])
    assert keys[1]==keys[2]


def test_different_applications_at_same_parcel_do_not_merge():
    a=project(1,"York City Planning Commission","ZHB 26-01")
    b=project(2,"York City Planning Commission","ZHB 26-02")
    for row in (a,b):row.update(applicant_name="Same LLC",parcel_reference="123 Main St")
    keys,_=resolve_project_keys([a,b])
    assert keys[1]!=keys[2]


def test_conflicting_existing_aliases_require_review():
    a=project(1,"York City Planning Commission","ZHB 26-01","Willow Creek plan")
    _, aliases=resolve_project_keys([a])
    named=next(k for k in aliases if k.startswith("named|"))
    aliases[named]="project:independent"
    keys, additions=resolve_project_keys([a],aliases)
    assert keys[1] is None
    assert additions=={}


def test_baseline_failures_stay_frozen():
    fixture=FIXTURES[9599]
    errors=validate_pass0_extractions(fixture["baseline_extractions"],fixture["source_text"])
    assert sum("not present in source" in e for e in errors)==6


def test_missing_source_identity_does_not_create_a_watchable_project():
    row = project(9, "York City Planning Commission", "ZHB 26-01")
    row["extraction_details"]["application_ids"] = []
    keys, aliases = resolve_project_keys([row])
    assert keys[9] is None
    assert aliases == {}


def test_company_label_does_not_merge_distinct_bare_cases():
    a = project(1, "Conewago Twp Planning Commission", "Case 05-2026", "Prosper Development")
    b = project(2, "Conewago Twp Zoning Hearing Board", "Case 06-2026", "Prosper Development")
    for row in [a,b]:
        row["applicant_name"] = "Prosper Development"
        row["extraction_details"]["parcel_references"] = ["201 Copenhaffer Road"]
    keys, _ = resolve_project_keys([a,b])
    assert keys[1] != keys[2]


def test_same_bare_case_applicant_and_specific_location_crosses_boards():
    a = project(1, "Conewago Twp Planning Commission", "Case 05-2026")
    b = project(2, "Conewago Twp Zoning Hearing Board", "Case 05-2026")
    for row in [a,b]:
        row["applicant_name"] = "Prosper Development"
        row["extraction_details"]["parcel_references"] = ["201, 235, and 255 Copenhaffer Road"]
    keys, _ = resolve_project_keys([a,b])
    assert keys[1] == keys[2]


@pytest.mark.parametrize(("wording", "expected"), [
    ("Wednesday, August 5, 2026", "2026-08-05"),
    ("Monday June 22nd, 2026 @ 6:00PM", "2026-06-22"),
    ("July 28, 2026, Tuesday", "2026-07-28"),
    ("Deadline is August 24, 2026.", "2026-08-24"),
    ("Deadline for action by Borough Council is 03/02/2026", "2026-03-02"),
    ("the May 12, 2026 Planning Commission meeting", "2026-05-12"),
    ("1-27-2026", "2026-01-27"),
    ("3/11/26 meeting", None),
    ("July 9 and July 16, 2026", None),
    ("July 9, 2026 and July 16, 2026", None),
    ("July 15th, with a completion date of October 15th 2026", None),
    ("Monday, August 5, 2026", None),
    ("Case 05-01-2026", None),
    ("February 30, 2026", None),
    ("August 20", None),
])
def test_source_date_wrappers_without_inventing_years_or_selecting_one_milestone(wording, expected):
    from countyiq.lib.proceeding_contract import exact_date
    assert exact_date(wording) == expected
