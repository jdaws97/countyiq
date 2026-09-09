"""Reject unsupported dates and stage changes before explanations can be stored."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from countyiq.lib.record_explanations import (
    explanation_prompt,
    prepare_explanation,
    validate_explanation,
)


@pytest.fixture
def source():
    return {
        "kind": "municipal",
        "subject_key": "municipal:123:selection",
        "meeting_date": "2026-08-11",
        "sources": [
            {
                "id": "P1",
                "label": "Council · 2026-08-11",
                "text": "Request a hearing. Recommended date September 8, 2026, 6:00 pm.",
            }
        ],
    }


@pytest.fixture
def explanation():
    return {
        "presentation_language": "en",
        "source_presentations": [
            {"source_id": "P1", "language": "en", "english_text": None}
        ],
        "headline": "Agenda proposes a hearing",
        "summary": "The agenda requests a hearing for September 8, 2026. [Evidence:source:P1]",
        "next_step": None,
        "citations": ["P1"],
        "record": {
            "event_type": "hearing",
            "event_tags": ["hearing"],
            "record_status": "proposed",
            "matter_category": "development",
            "decision_scope": None,
            "dates": [
                {
                    "date": "2026-09-08",
                    "time": "6:00 pm",
                    "label": "Recommended hearing date",
                    "status": "proposed",
                    "quote": "Recommended date September 8, 2026, 6:00 pm.",
                    "source_id": "P1",
                }
            ],
        },
    }


def test_preserves_proposed_date_and_does_not_promote_it_to_scheduled(
    source, explanation
):
    assert validate_explanation(explanation, source) == explanation
    explanation["record"]["dates"][0]["status"] = "scheduled"
    with pytest.raises(ValueError, match="must stay proposed"):
        validate_explanation(explanation, source)


def test_spanish_hearing_retains_original_quote_and_proposed_date(source, explanation):
    original = "Audiencia pública. Fecha propuesta: 8 de septiembre de 2026, 6:00 pm."
    source["sources"][0]["text"] = original
    explanation["source_presentations"][0].update(
        language="es",
        english_text="Public hearing. Proposed date: September 8, 2026, 6:00 pm.",
    )
    explanation["record"]["dates"][0]["quote"] = original
    assert (
        validate_explanation(explanation, source)["record"]["dates"][0]["quote"]
        == original
    )
    explanation["record"]["dates"][0]["status"] = "scheduled"
    with pytest.raises(ValueError, match="must stay proposed"):
        validate_explanation(explanation, source)


@pytest.mark.parametrize("month", ["Sept", "Sept.", "Sep", "September"])
def test_september_spelling_preserves_exact_day_and_rejects_a_changed_day(
    source, explanation, month
):
    quote = f"A hearing will be held on {month} 8th, 2026."
    source["sources"][0]["text"] = quote
    item = explanation["record"]["dates"][0]
    item.update(quote=quote, time=None, status="scheduled")
    validate_explanation(explanation, source)
    item["date"] = "2026-09-09"
    with pytest.raises(ValueError, match="Exact date is not stated"):
        validate_explanation(explanation, source)


def test_scheduled_hearing_on_proposed_amendment_keeps_its_date_status(
    source, explanation
):
    quote = (
        "A public hearing on a proposed amendment to the zoning code "
        "will be held on September 8, 2026, at 6:00 pm."
    )
    source["sources"][0]["text"] = quote
    explanation["record"]["dates"][0].update(quote=quote, status="scheduled")
    validate_explanation(explanation, source)


def test_hearing_subject_exception_preserves_a_separately_proposed_date(
    source, explanation
):
    quote = (
        "A public hearing on a proposed amendment to the zoning code. "
        "The proposed date is September 8, 2026, at 6:00 pm."
    )
    source["sources"][0]["text"] = quote
    item = explanation["record"]["dates"][0]
    item.update(quote=quote, status="scheduled")
    with pytest.raises(ValueError, match="must stay proposed"):
        validate_explanation(explanation, source)
    item["status"] = "proposed"
    validate_explanation(explanation, source)


def test_explicit_twelve_hour_time_can_use_equivalent_twenty_four_hour_format(
    source, explanation
):
    explanation["record"]["dates"][0]["time"] = "18:00"
    validate_explanation(explanation, source)
    explanation["record"]["dates"][0]["time"] = "06:00"
    with pytest.raises(ValueError, match="Date time is not stated"):
        validate_explanation(explanation, source)
    explanation["record"]["dates"][0]["time"] = "18:00 UTC"
    with pytest.raises(ValueError, match="Date time is not stated"):
        validate_explanation(explanation, source)


def test_spanish_ambiguous_numeric_date_is_not_interpreted_as_us_date(
    source, explanation
):
    source["sources"][0]["text"] = "Audiencia pública propuesta: 9/8/2026."
    explanation["source_presentations"][0].update(
        language="es", english_text="Proposed public hearing: 9/8/2026."
    )
    explanation["record"]["dates"][0].update(
        quote=source["sources"][0]["text"], time=None
    )
    with pytest.raises(ValueError, match="Exact date is not stated"):
        validate_explanation(explanation, source)


@pytest.mark.parametrize(
    "presentations", [[], [{"source_id": "P1", "language": "es", "english_text": None}]]
)
def test_missing_language_review_or_translation_cannot_be_accepted(
    source, explanation, presentations
):
    explanation["source_presentations"] = presentations
    with pytest.raises(ValueError):
        validate_explanation(explanation, source)


def test_an_ordinary_meeting_cannot_create_a_hearing_filter_match(source, explanation):
    source["sources"][0]["text"] = "Consider final approval of the plan."
    explanation["record"]["dates"] = []
    with pytest.raises(ValueError, match="explicitly named hearing"):
        validate_explanation(explanation, source)


@pytest.mark.parametrize(
    "field,value",
    [
        ("date", "2026-09-09"),
        ("date", "2027-09-08"),
        ("date", "20260908"),
        ("quote", "Council · 2026-08-11"),
        ("source_id", "P99"),
        ("time", "7:00 pm"),
    ],
)
def test_rejects_unstated_date_time_and_metadata_quotes(
    source, explanation, field, value
):
    explanation["record"]["dates"][0][field] = value
    with pytest.raises(ValueError):
        validate_explanation(explanation, source)


def test_numeric_two_digit_year_cannot_be_reinterpreted_as_meeting_year(
    source, explanation
):
    source["sources"][0]["text"] = "Hearing 9/8/25"
    item = explanation["record"]["dates"][0]
    item.update(quote="Hearing 9/8/25", time=None)
    with pytest.raises(ValueError):
        validate_explanation(explanation, source)


@pytest.mark.parametrize("written_date", ["9/8.", "9/8/26.", "9.8.2026.Next item."])
def test_numeric_date_at_sentence_end_keeps_its_exact_source_quote(
    source, explanation, written_date
):
    quote = f"Proposed hearing {written_date}"
    source["sources"][0]["text"] = quote
    explanation["record"]["dates"][0].update(quote=quote, time=None)

    result = validate_explanation(explanation, source)

    assert result["record"]["dates"][0]["date"] == "2026-09-08"
    assert result["record"]["dates"][0]["quote"] == quote


@pytest.mark.parametrize("quote_entire_source", [False, True])
def test_explicit_named_date_can_be_quoted_from_joined_pdf_text(
    source, explanation, quote_entire_source
):
    source["sources"][0]["text"] = (
        "Proposed hearing. ItwillbepresentedattheSeptember8,2026,Councilmeeting."
    )
    item = explanation["record"]["dates"][0]
    quote = source["sources"][0]["text"] if quote_entire_source else "September8,2026"
    item.update(quote=quote, time=None)
    assert validate_explanation(explanation, source)["record"]["dates"][0] == item

    item["date"] = "2025-09-08"
    with pytest.raises(ValueError, match="Date changes its source year"):
        validate_explanation(explanation, source)

    item["date"] = "2026-09-09"
    with pytest.raises(ValueError, match="Exact date is not stated"):
        validate_explanation(explanation, source)


@pytest.mark.parametrize("written_date", ["9/8/25.", "9/8.25.", "9/80.", "19/8."])
def test_sentence_punctuation_does_not_allow_partial_or_changed_numeric_dates(
    source, explanation, written_date
):
    quote = f"Proposed hearing {written_date}"
    source["sources"][0]["text"] = quote
    explanation["record"]["dates"][0].update(quote=quote, time=None)

    with pytest.raises(ValueError, match="Exact date is not stated"):
        validate_explanation(explanation, source)


def test_partial_period_stays_literal_without_inventing_an_exact_day(
    source, explanation
):
    source["sources"][0]["text"] = "Expected completion November to March"
    explanation["record"].update(event_type="update", event_tags=["update"])
    item = explanation["record"]["dates"][0]
    item.update(
        date=None,
        time=None,
        label="Expected completion: November to March",
        quote=source["sources"][0]["text"],
        status="expected",
    )
    validate_explanation(explanation, source)
    item["date"] = "2026-11-01"
    with pytest.raises(ValueError):
        validate_explanation(explanation, source)


def test_repeated_invalid_content_stops_after_two_calls(source, explanation):
    from countyiq.lib.record_explanations import generate_explanation

    explanation["record"]["dates"][0]["status"] = "scheduled"
    calls = []

    def invoke(_config, prompt, **kwargs):
        calls.append(prompt)
        return SimpleNamespace(success=True, parsed=explanation)

    with pytest.raises(ValueError, match="must stay proposed"):
        generate_explanation(source, None, invoke)
    assert len(calls) == 2


@pytest.mark.parametrize("event_type", ["approval", "denial", "scoped_decision"])
def test_proposed_action_cannot_be_stored_as_a_completed_decision(
    source, explanation, event_type
):
    explanation["record"].update(
        event_type=event_type, event_tags=[event_type], decision_scope="Waiver"
    )
    with pytest.raises(ValueError, match="unconfirmed"):
        validate_explanation(explanation, source)


def test_unknown_citations_and_uncited_next_step_are_rejected(source, explanation):
    missing_source = deepcopy(explanation)
    missing_source["summary"] = "Unsupported parcel claim. [Evidence:source:P2]"
    with pytest.raises(ValueError):
        validate_explanation(missing_source, source)
    explanation["next_step"] = "Check the hearing notice."
    with pytest.raises(ValueError):
        validate_explanation(explanation, source)


def test_preparation_only_normalizes_known_citations_and_withholds_uncited_optional_copy(
    source, explanation
):
    explanation["summary"] = "The agenda requests a hearing. [Evidence:P1]"
    explanation["next_step"] = "Check the hearing notice."
    prepared, notes = prepare_explanation(explanation, source)
    assert prepared["summary"].endswith("[Evidence:source:P1]")
    assert prepared["next_step"] is None
    assert len(notes) == 2
    validate_explanation(prepared, source)
    explanation["summary"] = "Unknown evidence. [Evidence:P99]"
    prepared, _ = prepare_explanation(explanation, source)
    with pytest.raises(ValueError):
        validate_explanation(prepared, source)


def test_property_summary_has_no_opportunity_rank_or_second_pass_requirement(
    source, explanation
):
    source["kind"] = "property"
    explanation["record"] = None
    assert validate_explanation(explanation, source)["record"] is None


@pytest.mark.parametrize(
    "marker",
    ["[Evidence:P1; M1]", "[Evidence:P1, M1]", "[Evidence:source:P1;source:M1]"],
)
def test_grouped_known_citations_normalize_without_changing_sources(
    source, explanation, marker
):
    source["sources"].append({"id": "M1", "text": "Related plan."})
    explanation["source_presentations"].append(
        {"source_id": "M1", "language": "en", "english_text": None}
    )
    original_source = deepcopy(source)
    explanation["summary"] = f"The agenda requests a hearing. {marker}"
    original = deepcopy(explanation)
    prepared, notes = prepare_explanation(explanation, source)
    assert (
        prepared["summary"]
        == "The agenda requests a hearing. [Evidence:source:P1] [Evidence:source:M1]"
    )
    assert prepared["citations"] == ["M1", "P1"]
    assert notes
    validate_explanation(prepared, source)
    assert source == original_source and explanation == original


def test_group_with_unknown_citation_is_not_partially_repaired(source, explanation):
    explanation["summary"] = "The agenda requests a hearing. [Evidence:P1;UNKNOWN]"
    prepared, _ = prepare_explanation(explanation, source)
    assert prepared["summary"] == explanation["summary"]
    with pytest.raises(ValueError):
        validate_explanation(prepared, source)


def test_date_quote_accepts_typography_but_rejects_changed_words(source, explanation):
    source["sources"][0]["text"] = (
        "Council’s hearing: Recommended date September 8, 2026, 6:00 pm."
    )
    item = explanation["record"]["dates"][0]
    item["quote"] = "Council's hearing: Recommended date September 8, 2026, 6:00 pm."
    original_source = deepcopy(source)
    validate_explanation(explanation, source)
    assert source == original_source
    assert item["quote"].startswith("Council's")
    item["quote"] = item["quote"].replace("Recommended", "Confirmed")
    with pytest.raises(ValueError, match="absent from its source"):
        validate_explanation(explanation, source)


def test_duplicate_or_unbounded_source_context_cannot_be_dispatched(source):
    source["sources"].append(deepcopy(source["sources"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        explanation_prompt(source)
    source["sources"].pop()
    source["sources"][0]["text"] = "x" * 36_000
    with pytest.raises(ValueError, match="bound"):
        explanation_prompt(source)


def test_disabled_mode_does_not_read_database_or_invoke_a_model(monkeypatch):
    from countyiq.assets.enrichment.record_explanations import run_explanations

    monkeypatch.delenv("COUNTYIQ_PASS3_MODE", raising=False)
    result = run_explanations(SimpleNamespace(log=None), None, "municipal")
    assert result.metadata["status"] == "skipped"


def test_only_rejected_complete_content_receives_one_bounded_correction(
    source, explanation
):
    from countyiq.lib.record_explanations import generate_explanation

    invalid = deepcopy(explanation)
    invalid["record"]["dates"][0]["date"] = "2026-09-09"
    calls = []

    def invoke(_config, prompt, **kwargs):
        calls.append((prompt, kwargs))
        return SimpleNamespace(
            success=True, parsed=invalid if len(calls) == 1 else explanation
        )

    result, attempts = generate_explanation(source, None, invoke)
    assert result == explanation and attempts == 2
    assert "failed validation" in calls[1][0]
    assert all(kwargs["retries"] == 0 for _, kwargs in calls)
    assert all(kwargs["archive_key"] for _, kwargs in calls)
    assert calls[0][1]["archive_key"] != calls[1][1]["archive_key"]
    calls.clear()

    def failed(_config, prompt, **kwargs):
        calls.append((prompt, kwargs))
        return SimpleNamespace(success=False, error="Transport failed")

    with pytest.raises(ValueError, match="Transport failed"):
        generate_explanation(source, None, failed)
    assert len(calls) == 1
