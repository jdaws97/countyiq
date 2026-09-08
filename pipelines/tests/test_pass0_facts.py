from copy import deepcopy

import pytest
from countyiq.lib.pass0_facts import document_kind, structural_review
from countyiq.lib.pass0_source import index_source


def consent_fixture():
    source = (
        "Pine Borough Council minutes, September 1, 2026.\n"
        "Council moved to approve consent items 5.01 through 5.03, except 5.02.\n"
        "5.01 Wawa: preliminary/final land development plan at 10 Main Street.\n"
        "5.02 Eagle Rock: proposed bond reduction, removed for separate discussion.\n"
        "5.03 Mustang Pointe: settlement agreement.\n"
        "Consent motion carried 6-0.\n"
    )
    item = {
        "title": "Wawa land development plan",
        "type": "subdivision_review",
        "status": "decision",
        "summary": {
            "excerpts": [
                {
                    "start": "Council moved to approve consent items",
                    "end": "plan at 10 Main Street.",
                    "lines": [2, 3],
                },
                {
                    "start": "Consent motion carried 6-0.",
                    "end": "Consent motion carried 6-0.",
                    "lines": [6, 6],
                },
            ],
        },
        "identifiers": [
            {
                "kind": "address",
                "text": "10 Main Street",
                "lines": [[3, 3]],
            }
        ],
        "participants": [],
        "locations": [],
        "decisions": [
            {
                "subject": {"text": "Wawa preliminary/final plan", "lines": [[3, 3]]},
                "outcome": "approved",
                "scope": "plan",
                "form": "consent",
                "timing": "current",
                "timing_evidence": [[1, 3], [6, 6]],
                "date": None,
                "authority": [[1, 1]],
                "motion": [[2, 2]],
                "result": [[6, 6]],
                "applies_to": [[2, 3]],
            }
        ],
        "relevance": {
            "scope": "plan_review",
            "lines": [[3, 3]],
        },
        "conditions": [],
        "milestones": [],
        "event_date": None,
        "current_zoning": None,
        "proposed_zoning": None,
        "conflicts": [],
    }
    return source, {"matters": [item]}


def test_separated_consent_evidence_preserves_each_original_range():
    source, payload = consent_fixture()
    review = structural_review(payload, index_source(source))

    assert not review["envelope_errors"]
    assert not review["rejected"]
    matter = review["matters"][0]
    for receipt in matter["evidence"]:
        assert receipt["quote"] == source[receipt["start"] : receipt["end"]]
    # Source membership is deliberately not claimed to establish consent scope.
    assert matter["semantic_review_complete"] is False


def test_summary_endpoint_correction_preserves_original_citation_audit():
    source, payload = consent_fixture()
    source += "Engineer report:\nHarbor Park needs repairs in spring.\n"
    item = payload["matters"][0]
    item.update(
        title="Harbor Park",
        status="update",
        decisions=[],
        identifiers=[],
        summary={
            "excerpts": [{"start": "Harbor Park", "end": "in spring.", "lines": [7, 8]}]
        },
        relevance={"scope": "project_milestone", "lines": [[7, 8]]},
    )
    original = deepcopy(payload)

    review = structural_review(
        payload, index_source(source), continuation_ranges=[[7, 8]]
    )

    assert not review["rejected"]
    retained = review["matters"][0]
    assert retained["summary"]["excerpts"][0]["lines"] == [8, 8]
    assert retained["summary"]["text"] == "Harbor Park needs repairs in spring."
    assert retained["field_repairs"] == [
        {
            "field": "summary.excerpts.0",
            "reason": "Unique literal endpoint anchors within cited range",
            "original_lines": [[7, 8]],
            "repaired_lines": [[8, 8]],
        }
    ]
    receipt = next(
        item for item in retained["evidence"] if item["field"] == "summary.excerpts.0"
    )
    assert source[receipt["start"] : receipt["end"]] == receipt["quote"]
    assert payload == original
    assert retained["semantic_review_complete"] is False


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("AGENDA\nCouncil meeting\nCall to order\n", "agenda"),
        ("PLANNING COMMISSION AGENDA\nMay 1, 2026\n", "agenda"),
        ("Council minutes\nCall to order\nCONSENT AGENDA\n", "record"),
        ("Council meeting\nApproval of agenda\n", "unknown"),
        ("AGENDA\nMEETING MINUTES\n", "mixed"),
        (
            "MEETING AGENDA\nRecorded for preparing the minutes.\nCall to order\n",
            "agenda",
        ),
        ("SUPERVISORS AGENDA\nAction on Minutes\nPublic Comments\n", "agenda"),
        ("PLANNING COMMISSION\nAGENDA FOR JULY 9, 2026\nCall to Order\n", "agenda"),
        (
            (
                "PLANNING COMMISSION\nAGENDA\nCall to order\n"
                "A member moved to table the subdivision. The motion carried.\n"
            ),
            "mixed",
        ),
        (
            "AGENDA\nCall to order\nAttached prior minutes: the motion was\ncarried.\n",
            "mixed",
        ),
    ],
)
def test_document_kind_uses_explicit_titles_before_meeting_business(text, kind):
    assert document_kind(index_source(text)) == kind


def test_agenda_preserves_source_wording_and_history_without_asserting_a_vote():
    text = (
        "AGENDA\nPine Borough Council, September 1, 2026\n"
        "Table the 10 Main Street plan until county comments arrive.\n"
        "Council approved the earlier concept on August 1.\n"
    )
    _, payload = consent_fixture()
    matter = payload["matters"][0]
    matter.update(
        title="Council tabled the plan",
        status="scheduled",
        summary={
            "excerpts": [
                {
                    "start": "Table the 10 Main Street plan",
                    "end": "the earlier concept on August 1.",
                    "lines": [3, 4],
                }
            ]
        },
        identifiers=[],
        decisions=[],
        relevance={"scope": "plan_review", "lines": [[3, 4]]},
    )
    original = deepcopy(payload)
    review = structural_review(payload, index_source(text))

    assert not review["rejected"]
    result = review["matters"][0]
    assert result["status"] == "scheduled"
    assert result["decisions"] == []
    assert result["summary"]["text"] == (
        "Agenda item: Table the 10 Main Street plan until county comments arrive. "
        "Council approved the earlier concept on August 1."
    )
    assert result["summary_origin"] == "source_excerpt"
    assert "Council tabled" not in result["title"]
    assert payload == original

    _, decision_payload = consent_fixture()
    matter["decisions"] = decision_payload["matters"][0]["decisions"]
    assert structural_review(payload, index_source(text))["rejected"]
    matter["decisions"] = []
    matter["summary"]["text"] = "Council tabled the plan."
    assert structural_review(payload, index_source(text))["rejected"]


def test_bad_optional_identifier_is_withheld_without_losing_supported_matter():
    source, payload = consent_fixture()
    payload["matters"][0]["identifiers"][0]["text"] = "100 Main Street"
    original = deepcopy(payload)

    review = structural_review(payload, index_source(source))

    matter = review["matters"][0]
    assert matter["identifiers"] == []
    assert matter["field_rejections"][0]["field"] == "identifiers.0"
    assert payload == original


@pytest.mark.parametrize(
    ("source_address", "retained"),
    [("110 Main Street", False), ("10 Main Street; 10 Main Street", True)],
)
def test_address_membership_requires_complete_words_without_unique_occurrence(
    source_address, retained
):
    source, payload = consent_fixture()
    source += f"Address: {source_address}.\n"
    payload["matters"][0]["identifiers"] = [
        {"kind": "address", "text": "10 Main Street", "lines": [[7, 7]]}
    ]

    review = structural_review(
        payload, index_source(source), continuation_ranges=[[7, 7]]
    )

    assert not review["rejected"]
    matter = review["matters"][0]
    assert bool(matter["identifiers"]) is retained
    assert bool(matter["field_rejections"]) is not retained
    assert not matter["field_repairs"]


@pytest.mark.parametrize("cited_line", [7, 8])
def test_literal_continuation_preserves_address_and_original_citation_audit(cited_line):
    source, payload = consent_fixture()
    source += "Case at 697 Julie Court,\nMechanicsburg, PA 17055.\n"
    matter = payload["matters"][0]
    matter.update(
        title="697 Julie Court",
        status="update",
        decisions=[],
        summary={
            "excerpts": [{"start": "Case at", "end": "PA 17055.", "lines": [7, 8]}]
        },
        identifiers=[
            {
                "kind": "address",
                "text": "697 Julie Court, Mechanicsburg, PA 17055",
                "lines": [[cited_line, cited_line]],
            }
        ],
    )
    original = deepcopy(payload)

    review = structural_review(
        payload, index_source(source), continuation_ranges=[[7, 8]]
    )

    retained = review["matters"][0]
    assert retained["identifiers"][0]["lines"] == [[7, 8]]
    assert retained["field_rejections"] == []
    assert retained["field_repairs"] == [
        {
            "field": "identifiers.0",
            "reason": "Literal continuation within supplied matter evidence",
            "original_lines": [[cited_line, cited_line]],
            "repaired_lines": [[7, 8]],
        }
    ]
    receipt = next(
        row for row in retained["evidence"] if row["field"] == "identifiers.0"
    )
    assert receipt["quote"] == "697 Julie Court,\nMechanicsburg, PA 17055"
    assert source[receipt["start"] : receipt["end"]] == receipt["quote"]
    assert payload == original
    assert retained["semantic_review_complete"] is False


@pytest.mark.parametrize(
    ("source_tail", "claimed", "cited", "supplied"),
    [
        (
            "697 Julie Court, Mechanicsburg, PA 17055.\nUnrelated case.\n",
            "697 Julie Court, Mechanicsburg, PA 17055",
            [[8, 8]],
            [[7, 8]],
        ),
        (
            "Case at 697 Julie Court\n,\nMechanicsburg, PA 17055.\n",
            "697 Julie Court , Mechanicsburg, PA 17055",
            [[8, 8]],
            [[7, 9]],
        ),
        (
            "Case at 697 Julie Court,\nMechanicsburg, PA 17055.\n",
            "697 Julie Court, Mechanicsburg, PA 17055",
            [[8, 8]],
            [[8, 8]],
        ),
        (
            "Case at 697 Julie Court,\nMechanicsburg, PA 17055.\n",
            "697 Julie Court, Mechanicsburg, PA 17055",
            [[7, 7]],
            [[7, 7]],
        ),
        (
            "Unrelated case.\n697 Julie Court, Mechanicsburg, PA 17055.\n",
            "697 Julie Court, Mechanicsburg, PA 17055",
            [[7, 7]],
            [[7, 8]],
        ),
        (
            "Case at 697 Julie Court,\nUnprovided material.\nMechanicsburg, PA 17055.\n",
            "697 Julie Court, Mechanicsburg, PA 17055",
            [[7, 7]],
            [[7, 7], [9, 9]],
        ),
        (
            "Case at 697 Julie Court,\nMechanicsburg, PA 17055.\n",
            "967 Julie Court, Mechanicsburg, PA 17055",
            [[7, 7]],
            [[7, 8]],
        ),
        (
            "Case at 697 Julie Court,\nMechanicsburg, PA 17055.\n697 Julie Court, Mechanicsburg, PA 17055.\n",
            "697 Julie Court, Mechanicsburg, PA 17055",
            [[7, 7]],
            [[7, 9]],
        ),
        (
            "Payment to Kinsley\n1\nConstruction.\n",
            "Kinsley Construction",
            [[7, 7]],
            [[7, 9]],
        ),
    ],
)
def test_continuation_does_not_shift_skip_rewrite_or_choose_ambiguous_identity(
    source_tail, claimed, cited, supplied
):
    source, payload = consent_fixture()
    source += source_tail
    payload["matters"][0]["identifiers"] = [
        {"kind": "project", "text": claimed, "lines": cited}
    ]

    review = structural_review(
        payload, index_source(source), continuation_ranges=supplied
    )

    retained = review["matters"][0]
    assert retained["identifiers"] == []
    assert retained["field_repairs"] == []
    assert retained["field_rejections"][0]["field"] == "identifiers.0"


def test_participant_role_requires_literal_evidence_but_keeps_unclassified_name():
    source, payload = consent_fixture()
    source += "Acme Construction was awarded the paving contract for Oak Street.\n"
    matter = payload["matters"][0]
    matter["participants"] = [
        {
            "name": {"text": "Acme Construction", "lines": [[7, 7]]},
            "role": "applicant",
            "role_evidence": {"text": "applied for approval", "lines": [[7, 7]]},
        }
    ]
    matter["locations"] = [{"kind": "street", "text": "Oak Street", "lines": [[7, 7]]}]
    original = deepcopy(payload)

    review = structural_review(payload, index_source(source))

    assert not review["rejected"]
    result = review["matters"][0]
    assert result["participants"][0]["name"]["text"] == "Acme Construction"
    assert result["participants"][0]["role"] == "unknown"
    assert result["participants"][0]["role_evidence"] is None
    assert result["locations"][0]["text"] == "Oak Street"
    assert result["field_rejections"][0]["field"] == "participants.0.role"
    assert payload == original

    participant = matter["participants"][0]
    participant["role"] = "contractor"
    participant["role_evidence"]["text"] = "was awarded the paving contract"
    result = structural_review(payload, index_source(source))["matters"][0]
    assert result["participants"][0]["role"] == "contractor"
    assert result["field_rejections"] == []


def test_update_can_record_explicit_non_action_without_becoming_approval():
    source, payload = consent_fixture()
    source += "Council discussed a proposed plan amendment. No action taken.\n"
    matter = payload["matters"][0]
    matter["status"] = "update"
    matter["summary"] = {
        "excerpts": [
            {
                "start": "Council discussed a proposed plan amendment. No action taken.",
                "end": "Council discussed a proposed plan amendment. No action taken.",
                "lines": [7, 7],
            }
        ]
    }
    decision = matter["decisions"][0]
    decision["outcome"] = "no_action"
    for field in ("motion", "result", "applies_to"):
        decision[field] = [[7, 7]]
    decision["subject"] = {"text": "Proposed plan amendment", "lines": [[7, 7]]}

    review = structural_review(payload, index_source(source))

    assert not review["rejected"]
    assert review["matters"][0]["status"] == "update"
    assert review["matters"][0]["decisions"][0]["outcome"] == "no_action"


def test_update_preserves_prior_approval_with_its_own_date():
    source, payload = consent_fixture()
    source += "The Commission approved the Wawa plan on August 4, 2026.\n"
    matter = payload["matters"][0]
    matter["status"] = "update"
    matter["summary"] = {
        "excerpts": [
            {
                "start": "The Commission approved the Wawa plan on August 4, 2026.",
                "end": "The Commission approved the Wawa plan on August 4, 2026.",
                "lines": [7, 7],
            }
        ],
    }
    matter["event_date"] = {"text": "September 1, 2026", "lines": [[1, 1]]}
    decision = matter["decisions"][0]
    decision.update(
        timing="prior",
        timing_evidence=[[7, 7]],
        date={"text": "August 4, 2026", "lines": [[7, 7]]},
        form="direct_statement",
        authority=[[7, 7]],
        motion=[[7, 7]],
        result=[[7, 7]],
        applies_to=[[7, 7]],
    )

    review = structural_review(payload, index_source(source))

    assert not review["rejected"]
    retained = review["matters"][0]
    assert retained["status"] == "update"
    assert retained["event_date_iso"] == "2026-09-01"
    assert retained["decisions"][0]["date_iso"] == "2026-08-04"
    assert retained["semantic_review_complete"] is False
    assert any(
        row["field"] == "decisions.0.timing_evidence" for row in retained["evidence"]
    )


def test_prior_action_alone_cannot_make_current_status_a_decision():
    source, payload = consent_fixture()
    payload["matters"][0]["decisions"][0]["timing"] = "prior"

    review = structural_review(payload, index_source(source))

    assert not review["matters"]
    assert "current recorded action" in review["rejected"][0]["errors"][0]


def test_update_still_cannot_assert_current_approval():
    source, payload = consent_fixture()
    payload["matters"][0]["status"] = "update"

    review = structural_review(payload, index_source(source))

    assert not review["matters"]
    assert "current approval" in review["rejected"][0]["errors"][0]


@pytest.mark.parametrize("outcome", ["recommended_approval", "recommended_denial"])
def test_carried_recommendation_does_not_become_approval_of_the_relief(outcome):
    source, payload = consent_fixture()
    source += "The Commission recommended the waiver to Council. Motion carried.\n"
    matter = payload["matters"][0]
    matter["status"] = "recommendation"
    decision = matter["decisions"][0]
    decision.update(outcome=outcome, scope="waiver", form="recorded_motion")
    for field in ("motion", "result", "applies_to", "timing_evidence"):
        decision[field] = [[7, 7]]

    review = structural_review(payload, index_source(source))

    assert not review["rejected"]
    retained = review["matters"][0]
    assert retained["status"] == "recommendation"
    assert retained["decisions"][0]["outcome"] == outcome
    assert retained["semantic_review_complete"] is False

    matter["status"] = "decision"
    assert structural_review(payload, index_source(source))["rejected"]
    matter["status"] = "update"
    assert structural_review(payload, index_source(source))["rejected"]
    decision["timing"] = "prior"
    assert not structural_review(payload, index_source(source))["rejected"]


def test_unsupported_decision_date_is_reported_without_losing_the_action():
    source, payload = consent_fixture()
    payload["matters"][0]["decisions"][0]["date"] = {
        "text": "September 2, 2026",
        "lines": [[1, 1]],
    }

    review = structural_review(payload, index_source(source))

    assert not review["rejected"]
    retained = review["matters"][0]
    assert retained["decisions"][0]["date"] is None
    assert retained["decisions"][0]["date_iso"] is None
    assert retained["field_rejections"][0]["field"] == "decisions.0.date"


def test_minutes_description_is_source_rendered_without_certifying_classification():
    source, payload = consent_fixture()
    source += "The owner reports 3/6 units are complete losses after the fire.\n"
    matter = payload["matters"][0]
    matter.update(
        title="Three units completed",
        type="property_matter",
        status="update",
        summary={
            "excerpts": [
                {
                    "start": "The owner reports 3/6 units are complete losses after the fire.",
                    "end": "The owner reports 3/6 units are complete losses after the fire.",
                    "lines": [7, 7],
                }
            ]
        },
        identifiers=[],
        decisions=[],
    )
    original = deepcopy(payload)

    review = structural_review(payload, index_source(source))

    assert not review["rejected"]
    retained = review["matters"][0]
    assert retained["summary"]["text"] == (
        "The owner reports 3/6 units are complete losses after the fire."
    )
    assert retained["summary_origin"] == "source_excerpt"
    assert "completed" not in retained["title"]
    assert retained["semantic_review_complete"] is False
    assert payload == original
    matter["summary"]["text"] = "Three units were completed."
    assert structural_review(payload, index_source(source))["rejected"]


def test_reported_prior_decision_can_preserve_an_unknown_deciding_body():
    source, payload = consent_fixture()
    source += "The grant application was not approved.\n"
    matter = payload["matters"][0]
    matter.update(
        status="update",
        summary={
            "excerpts": [
                {
                    "start": "The grant application was not approved.",
                    "end": "The grant application was not approved.",
                    "lines": [7, 7],
                }
            ]
        },
    )
    decision = matter["decisions"][0]
    decision.update(
        timing="prior",
        outcome="denied",
        scope="grant_application",
        authority=None,
        form="direct_statement",
    )
    for field in ("motion", "result", "applies_to", "timing_evidence"):
        decision[field] = [[7, 7]]

    review = structural_review(payload, index_source(source))

    assert not review["rejected"]
    retained = review["matters"][0]
    assert retained["decisions"][0]["authority"] is None
    assert retained["decisions"][0]["authority_text"] is None
    assert not any(
        row["field"] == "decisions.0.authority" for row in retained["evidence"]
    )


def test_application_award_and_reconsideration_survive_as_distinct_actions():
    source, payload = consent_fixture()
    actions = [
        ("Council approved the Harbor Park grant application.", "grant_application"),
        ("Council allocated $10,000 to Harbor Park.", "funding_award"),
        ("Council agreed to reconsider the Harbor Park plan.", "reconsideration"),
    ]
    first_line = len(source.splitlines()) + 1
    source += "\n".join(text for text, _ in actions) + "\n"
    matter = payload["matters"][0]
    decision_template = deepcopy(matter["decisions"][0])
    matter.update(
        title="Harbor Park",
        identifiers=[],
        relevance={
            "scope": "project_milestone",
            "lines": [[first_line, first_line + 2]],
        },
        summary={
            "excerpts": [
                {"start": text, "end": text, "lines": [number, number]}
                for number, (text, _) in enumerate(actions, start=first_line)
            ]
        },
        decisions=[],
    )
    for number, (text, scope) in enumerate(actions, start=first_line):
        decision = deepcopy(decision_template)
        decision.update(
            subject={"text": text, "lines": [[number, number]]},
            scope=scope,
            form="direct_statement",
        )
        for field in ("motion", "result", "applies_to", "timing_evidence"):
            decision[field] = [[number, number]]
        matter["decisions"].append(decision)
    original = deepcopy(payload)

    review = structural_review(payload, index_source(source))

    assert not review["rejected"]
    retained = review["matters"][0]
    assert [decision["scope"] for decision in retained["decisions"]] == [
        scope for _, scope in actions
    ]
    assert retained["semantic_review_complete"] is False
    assert payload == original
    for receipt in retained["evidence"]:
        assert receipt["quote"] == source[receipt["start"] : receipt["end"]]

    matter["decisions"][1]["scope"] = "funding"
    assert structural_review(payload, index_source(source))["rejected"]


def test_summary_anchors_keep_shared_line_actions_separate_and_source_bound():
    source, payload = consent_fixture()
    source += "WWI – request for update, no reply. Dough Boy – deposit was made.\n"
    first = payload["matters"][0]
    first.update(
        title="WWI",
        status="update",
        decisions=[],
        identifiers=[],
        summary={
            "excerpts": [
                {"start": "WWI – request", "end": "no reply.", "lines": [7, 7]}
            ]
        },
    )
    second = deepcopy(first)
    second.update(
        title="Dough Boy",
        summary={
            "excerpts": [
                {"start": "Dough Boy", "end": "deposit was made.", "lines": [7, 7]}
            ]
        },
    )
    payload["matters"].append(second)
    original = deepcopy(payload)

    review = structural_review(payload, index_source(source))

    assert not review["rejected"]
    matters = review["matters"]
    assert matters[0]["summary"]["text"] == "WWI – request for update, no reply."
    assert matters[1]["summary"]["text"] == "Dough Boy – deposit was made."
    receipts = [
        next(row for row in matter["evidence"] if row["field"] == "summary.excerpts.0")
        for matter in matters
    ]
    assert receipts[0]["end"] < receipts[1]["start"]
    for receipt in receipts:
        assert receipt["quote"] == source[receipt["start"] : receipt["end"]]
    assert payload == original

    first["summary"]["excerpts"][0]["start"] = "WWI – deposit was made."
    review = structural_review(payload, index_source(source))
    assert [row["index"] for row in review["rejected"]] == [0]
    assert len(review["matters"]) == 1


def test_summary_cannot_reorder_or_repeat_source_excerpts():
    source, payload = consent_fixture()
    excerpts = payload["matters"][0]["summary"]["excerpts"]
    excerpts.reverse()
    assert structural_review(payload, index_source(source))["rejected"]
    excerpts[:] = [excerpts[0], deepcopy(excerpts[0])]
    assert structural_review(payload, index_source(source))["rejected"]


def test_deciding_body_is_recovered_from_split_header_without_generated_name():
    source, payload = consent_fixture()
    source += "FRANKLIN TOWNSHIP YORK COUNTY PA\nBOARD OF SUPERVISORS\n"
    payload["matters"][0]["decisions"][0]["authority"] = [[7, 8]]

    review = structural_review(payload, index_source(source))

    assert not review["rejected"]
    decision = review["matters"][0]["decisions"][0]
    assert decision["authority_text"] == (
        "FRANKLIN TOWNSHIP YORK COUNTY PA BOARD OF SUPERVISORS"
    )


def test_wrong_source_line_and_scheduled_decision_fail_per_item():
    source, payload = consent_fixture()
    wrong_line = deepcopy(payload["matters"][0])
    wrong_line["summary"]["excerpts"][0]["lines"] = [999, 999]
    scheduled = deepcopy(payload["matters"][0])
    scheduled["status"] = "scheduled"
    payload["matters"].extend([wrong_line, scheduled])

    review = structural_review(payload, index_source(source))

    assert len(review["matters"]) == 1
    assert [item["index"] for item in review["rejected"]] == [1, 2]


def test_coarse_milestone_keeps_wording_without_inventing_iso_date():
    source, payload = consent_fixture()
    source += "Construction is expected to finish at the beginning of 2028.\n"
    payload["matters"][0]["milestones"] = [
        {
            "kind": "completion",
            "date": {
                "text": "the beginning of 2028",
                "lines": [[7, 7]],
            },
        }
    ]

    review = structural_review(payload, index_source(source))

    assert review["matters"][0]["milestones"][0]["iso_date"] is None


def test_old_model_hash_or_narrative_fields_do_not_enter_new_contract():
    source, payload = consent_fixture()
    payload["source_sha256"] = index_source(source).sha256
    assert structural_review(payload, index_source(source))["envelope_errors"]
    del payload["source_sha256"]
    payload["matters"][0]["why_it_matters"] = "Investment opportunity."
    assert structural_review(payload, index_source(source))["rejected"]


def test_undated_actions_do_not_become_milestones_or_discard_the_matter():
    source, payload = consent_fixture()
    source += "Project completed; it will be reviewed again next Thursday.\n"
    payload["matters"][0]["milestones"] = [
        {"kind": "completion", "date": {"text": "completed", "lines": [[7, 7]]}},
        {"kind": "other", "date": {"text": "again", "lines": [[7, 7]]}},
        {"kind": "other", "date": {"text": "next Thursday", "lines": [[7, 7]]}},
    ]

    review = structural_review(payload, index_source(source))

    assert not review["rejected"]
    matter = review["matters"][0]
    assert [item["date"]["text"] for item in matter["milestones"]] == ["next Thursday"]
    assert len(matter["field_rejections"]) == 2
    assert len(payload["matters"][0]["milestones"]) == 3
