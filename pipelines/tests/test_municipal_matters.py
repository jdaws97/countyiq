"""Contract tests for partitioned municipal matter accounts."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from countyiq.lib.municipal_matters import (
    generate_matters,
    matter_prompt,
    resolve_matter_keys,
    restore_record_keys,
    validate_matters,
)


def _source(*records):
    """Build a small candidate bundle with one textual source per record."""
    return {
        "subject_key": "municipal:750-e-philadelphia",
        "records": [
            {
                "key": key,
                "meeting_date": date,
                "source_ids": [source_id],
            }
            for key, date, source_id, _text in records
        ],
        "sources": [
            {
                "id": source_id,
                "record_key": key,
                "meeting_date": date,
                "text": text,
            }
            for key, date, source_id, text in records
        ],
    }


def _account(keys, *, outcome="not_established", record_status="proposed"):
    source_ids = [f"P{key[1:]}" for key in keys]
    citations = " ".join(f"[Evidence:source:{source_id}]" for source_id in source_ids)
    account = {
        "presentation_language": "en",
        "source_presentations": [
            {"source_id": source_id, "language": "en", "english_text": None}
            for source_id in source_ids
        ],
        "headline": "Store seeks zoning relief",
        "summary": f"The supplied record documents the request. {citations}",
        "next_step": None,
        "citations": source_ids.copy(),
        "record": {
            "event_type": "application",
            "event_tags": ["application"],
            "record_status": record_status,
            "matter_category": "development",
            "decision_scope": None,
            "dates": [],
        },
        "request": f"The applicant seeks use and parking relief. {citations}",
        "why_it_matters": f"The request could change the site's permitted use. {citations}",
        "readiness": "ready",
        "outcome": outcome,
        "outcome_summary": (
            f"The competent body recorded the stated disposition. {citations}"
            if outcome != "not_established"
            else None
        ),
        "connection": citations if len(keys) > 1 else None,
        "conditions": [],
        "history": [
            {
                "record_key": key,
                "summary": f"This record documents its own action. [Evidence:source:P{key[1:]}]",
                "record_status": record_status,
            }
            for key in keys
        ],
    }
    if outcome == "conditional":
        account["conditions"] = [f"Landscaping is required. {citations}"]
    return account


def _matter(keys, **account_options):
    return {"record_keys": keys, "account": _account(keys, **account_options)}


def test_model_references_round_trip_to_exact_stored_identities():
    first = "municipal:4692:" + "a5255e2281e6d383770fe742b67929e42" * 2
    second = "municipal:10689:" + "3774cca10305b4de4c23c65cded8a7fbb" * 2
    source = _source(
        (first, "2026-03-01", "P1", "Agenda: rezoning request.\nOriginal • text."),
        (second, "2026-03-15", "P2", "Minutes: discussion of the same rezoning."),
    )
    original = deepcopy(source)

    def invoke(_config, prompt):
        supplied = json.loads(prompt.split("\n", 1)[1])
        assert [record["key"] for record in supplied["records"]] == ["R1", "R2"]
        assert [item["text"] for item in supplied["sources"]] == [
            item["text"] for item in source["sources"]
        ]
        return SimpleNamespace(
            success=True, parsed={"matters": [_matter(["R1", "R2"])]}
        )

    value, attempts = generate_matters(source, None, invoke)
    assert attempts == 1
    assert value["matters"][0]["record_keys"] == [first, second]
    assert [
        entry["record_key"] for entry in value["matters"][0]["account"]["history"]
    ] == [first, second]
    assert source == original
    assert validate_matters(value, source) == value


@pytest.mark.parametrize("unknown", ["R0", "R3", "R01", "municipal:other-bundle"])
def test_record_reference_expansion_never_guesses_an_unknown_identity(unknown):
    source = _source(("persisted-key", "2026-03-01", "P1", "Agenda: a request."))
    value = {"matters": [_matter(["R1"])]}
    value["matters"][0]["account"]["history"][0]["record_key"] = unknown
    with pytest.raises(ValueError, match="Unknown record reference"):
        restore_record_keys(value, source)


def test_reference_expansion_preserves_the_complete_partition_gate():
    source = _source(
        ("first-key", "2026-03-01", "P1", "First request."),
        ("second-key", "2026-03-01", "P2", "Second request."),
    )
    value = restore_record_keys({"matters": [_matter(["R1"])]}, source)
    with pytest.raises(ValueError, match="Every source record"):
        validate_matters(value, source)
    source["records"][1]["key"] = "first-key"
    with pytest.raises(ValueError, match="duplicate record keys"):
        matter_prompt(source)


def test_later_competent_body_minutes_establishes_outcome_for_agenda_request():
    source = _source(
        (
            "R1",
            "2026-03-01",
            "P1",
            "Agenda: appliance store requests use and parking variances at 750 E. Philadelphia St.",
        ),
        (
            "R2",
            "2026-03-15",
            "P2",
            "Zoning Hearing Board minutes: the Board approved the same use and parking variances.",
        ),
    )
    value = {
        "matters": [_matter(["R1", "R2"], outcome="approved", record_status="decision")]
    }

    assert validate_matters(value, source) == value


def test_same_parcel_requests_can_remain_separate_matters():
    source = _source(
        (
            "R1",
            "2026-03-01",
            "P1",
            "Agenda: rezoning request for 750 E. Philadelphia St.",
        ),
        (
            "R2",
            "2026-06-01",
            "P2",
            "Agenda: subdivision request for 750 E. Philadelphia St.",
        ),
    )
    value = {"matters": [_matter(["R1"]), _matter(["R2"])]}

    validated = validate_matters(value, source)

    assert [matter["record_keys"] for matter in validated["matters"]] == [
        ["R1"],
        ["R2"],
    ]


@pytest.mark.parametrize(
    "matters",
    [
        [_matter(["R1"])],
        [_matter(["R1"]), _matter(["R1"]), _matter(["R2"])],
    ],
)
def test_rejects_missing_or_duplicate_record_ownership(matters):
    source = _source(
        ("R1", "2026-03-01", "P1", "Agenda: rezoning request."),
        ("R2", "2026-06-01", "P2", "Agenda: subdivision request."),
    )

    with pytest.raises(ValueError, match="exactly one matter"):
        validate_matters({"matters": matters}, source)


def test_rejects_history_that_borrows_another_record_citation():
    source = _source(
        ("R1", "2026-03-01", "P1", "Agenda: rezoning request."),
        ("R2", "2026-06-01", "P2", "Agenda: subdivision request."),
    )
    value = {"matters": [_matter(["R1"]), _matter(["R2"])]}
    value["matters"][0]["account"]["history"][0]["summary"] = (
        "This record documents its own action. [Evidence:source:P2]"
    )

    with pytest.raises(ValueError, match="cross-matter citations"):
        validate_matters(value, source)


def test_grouped_account_requires_connection_evidence_from_every_member():
    source = _source(
        ("R1", "2026-03-01", "P1", "Agenda: variance request."),
        ("R2", "2026-03-15", "P2", "Minutes: variance approved."),
    )
    value = {"matters": [_matter(["R1", "R2"])]}
    value["matters"][0]["account"]["connection"] = (
        "Same application. [Evidence:source:P1]"
    )
    value["matters"][0]["account"]["citations"].remove("P2")

    with pytest.raises(ValueError, match="every linked record"):
        validate_matters(value, source)


@pytest.mark.parametrize("record_status", ["proposed", "recommendation"])
def test_agenda_or_recommendation_cannot_establish_approved_outcome(record_status):
    source = _source(("R1", "2026-03-01", "P1", "Agenda recommends approval."))
    value = {
        "matters": [_matter(["R1"], outcome="approved", record_status=record_status)]
    }

    with pytest.raises(ValueError, match="agenda or recommendation"):
        validate_matters(value, source)


def test_update_can_report_the_prior_approval_at_370_poplar():
    source = _source(
        (
            "R1",
            "2026-04-10",
            "P1",
            "Council update: the Board previously approved the 370 Poplar Street plan.",
        )
    )
    value = {"matters": [_matter(["R1"], outcome="approved", record_status="update")]}
    record = value["matters"][0]["account"]["record"]
    record["event_type"] = "update"
    record["event_tags"] = ["update"]

    assert validate_matters(value, source) == value


def test_follow_up_date_uses_its_cited_source_meeting_year_across_records():
    source = _source(
        ("R1", "2025-03-01", "P1", "Hearing September 8."),
        ("R2", "2026-04-01", "P2", "Later agenda reports the same request."),
    )
    value = {"matters": [_matter(["R1", "R2"])]}
    value["matters"][0]["account"]["record"]["dates"] = [
        {
            "date": "2025-09-08",
            "time": None,
            "label": "Hearing date",
            "status": "scheduled",
            "quote": "Hearing September 8.",
            "source_id": "P1",
        }
    ]

    assert validate_matters(value, source) == value


def test_conditional_outcome_requires_cited_conditions():
    source = _source(
        ("R1", "2026-03-15", "P1", "Minutes: approval with landscaping condition.")
    )
    value = {
        "matters": [_matter(["R1"], outcome="conditional", record_status="decision")]
    }
    value["matters"][0]["account"]["conditions"] = []

    with pytest.raises(ValueError, match="retain its conditions"):
        validate_matters(value, source)


def test_older_arriving_record_keeps_the_followed_matter_identity():
    matters = [_matter(["R1", "R2"])]

    resolved = resolve_matter_keys(matters, {"R2": "matter:followed-variance"})

    assert resolved[0]["key"] == "matter:followed-variance"


@pytest.mark.parametrize(
    "matters,known,match",
    [
        (
            [_matter(["R1", "R2"])],
            {"R1": "matter:rezoning", "R2": "matter:subdivision"},
            "would merge",
        ),
        (
            [_matter(["R1"]), _matter(["R2"])],
            {"R1": "matter:variance", "R2": "matter:variance"},
            "would split",
        ),
    ],
)
def test_rejects_merging_or_splitting_followed_identities(matters, known, match):
    with pytest.raises(ValueError, match=match):
        resolve_matter_keys(deepcopy(matters), known)
