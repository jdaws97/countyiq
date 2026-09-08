"""Evidence selections preserve source boundaries, including empty reads."""

import pytest
from countyiq.lib.municipal_evidence import (
    bind_evidence,
    bind_review,
    evidence_windows,
    source_document,
)
from countyiq.lib.pass0_source import index_source


def test_windows_account_for_every_line_without_truncating_late_matters():
    document = index_source("Routine report\n" * 100 + "New subdivision application\n")
    windows = evidence_windows(document, primary_chars=80, context_lines=2)
    covered = [
        number for window in windows for number in range(window.first, window.last + 1)
    ]
    assert covered == list(range(1, len(document.units) + 1))
    assert "New subdivision application" in windows[-1].prompt
    assert windows[1].context_first < windows[1].first


def test_multiline_title_and_conditions_resolve_exactly():
    text = "BOARD AGENDA\nMessiah Lifeways\nLand Development Plan\nProposed approval, subject to\nengineer review and a signed agreement.\nOther project\n"
    document = index_source(text)
    window = evidence_windows(document)[0]
    result = bind_evidence(
        {"items": [{"title": 2, "passages": [[1, 5]]}]}, document, window
    )
    assert result["status"] == "complete"
    card = result["cards"][0]
    assert card["title"] == "Messiah Lifeways"
    assert card["passages"][0]["text"] == text[: text.index("Other project")]
    for span in [card["subject"], *card["passages"]]:
        assert span["text"] == text[span["start"] : span["end"]]
        assert span["source_text_sha256"] == document.sha256
    assert "approval" not in card
    assert "status" not in card


@pytest.mark.parametrize(
    "item",
    [
        {"title": 1, "passages": [[1, 9999]]},
        {"title": 999, "passages": [[1, 2]]},
        {"title": True, "passages": [[1, 2]]},
    ],
)
def test_invalid_ranges_cannot_become_complete_evidence(item):
    document = index_source("Named project\nApproved subject to conditions\n")
    result = bind_evidence({"items": [item]}, document, evidence_windows(document)[0])
    assert result["status"] != "complete"
    assert result["cards"] == []
    assert result["errors"]


def test_context_title_cannot_create_duplicate_primary_assignment():
    document = index_source("Project A\nProject B\nProject C\nProject D\n")
    window = evidence_windows(document, primary_chars=10, context_lines=1)[1]
    result = bind_evidence(
        {"items": [{"title": 1, "passages": [[1, 2]]}]}, document, window
    )
    assert result["status"] == "partial"
    assert result["cards"] == []


def test_unbound_navigation_marker_uses_selected_evidence_without_adding_other_subject():
    document = index_source("Code report: Property A\nProperty B: notice posted.\n")
    result = bind_evidence(
        {"items": [{"title": 1, "passages": [[2, 2]]}]},
        document,
        evidence_windows(document)[0],
    )
    assert result["status"] == "complete"
    assert result["warnings"]
    card = result["cards"][0]
    assert card["title"] == "Property B: notice posted."
    assert "Property A" not in str(card)


def test_empty_completed_read_is_distinct_from_broken_envelope():
    document = index_source("Meeting cancelled\n")
    window = evidence_windows(document)[0]
    assert bind_evidence({"items": []}, document, window)["status"] == "complete"
    assert bind_evidence(None, document, window)["status"] == "invalid"


def test_review_rejects_unbounded_ranges_before_scanning_accounting_lines():
    document = index_source("Named development\nPlan tabled pending review.\n")
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "Named development",
                    "passages": [[1, 10**18]],
                }
            ]
        },
        [],
        document,
    )
    assert result["status"] == "partial"
    assert not result["cards"]
    assert result["errors"]


def test_unicode_pages_preserve_original_offsets_and_no_newlines():
    pages = [{"page": 1, "text": "Café project"}, {"page": 2, "text": "条件\n"}]
    document, spans = source_document(pages)
    for page, span in zip(pages, spans, strict=True):
        assert document.text[span["start"] : span["end"]] == page["text"]


@pytest.mark.parametrize(
    "title", ["PA American Water", "water", "Penn", "invented approval"]
)
def test_nonliteral_short_label_keeps_original_source_without_rewriting(title):
    document = index_source(
        "Pennsylvania American Water\nProposed water main extension.\n"
    )
    original = bind_evidence(
        {"items": [{"title": 1, "passages": [[1, 2]]}]},
        document,
        evidence_windows(document)[0],
    )["cards"]
    # A literal lowercase word is valid; paraphrases, case changes and partial
    # words fall back to the bound discovery title.
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": 0,
                    "title": title,
                    "passages": [[1, 2]],
                }
            ]
        },
        original,
        document,
    )
    assert result["status"] == "complete"
    if title == "water":
        assert result["cards"][0]["title"] == "water"
    else:
        assert result["cards"][0]["title"] == original[0]["title"]
        assert result["cards"][0]["passages"] == original[0]["passages"]
        assert result["warnings"]


def test_review_preserves_wrapped_exact_span_and_rejects_unknown_or_duplicate_indices():
    document = index_source(
        "New\nSchool Plan\nApproval proposed, conditions pending.\n"
    )
    original = bind_evidence(
        {"items": [{"title": 1, "passages": [[1, 3]]}]},
        document,
        evidence_windows(document)[0],
    )["cards"]
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": 0,
                    "title": "New School Plan",
                    "passages": [[1, 3]],
                }
            ]
        },
        original,
        document,
    )
    span = result["cards"][0]["subject"]
    assert document.text[span["start"] : span["end"]] == "New\nSchool Plan"
    assert result["cards"][0]["passages"] == original[0]["passages"]
    for indices in ([0, 0], [1]):
        result = bind_review(
            {
                "items": [
                    {
                        "context": [],
                        "references": [],
                        "index": index,
                        "title": "School",
                        "passages": [[1, 3]],
                    }
                    for index in indices
                ]
            },
            original,
            document,
        )
        assert result["status"] == "partial"


def test_review_recovers_missing_continuation_and_subject_from_full_source():
    document = index_source(
        "Bridge project motion to approve.\n"
        "Seconded. Motion failed, 2-3.\n"
        "School zoning application received.\n"
    )
    original = bind_evidence(
        {"items": [{"title": 1, "passages": [[1, 1]]}]},
        document,
        evidence_windows(document)[0],
    )["cards"]
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": 0,
                    "title": "Bridge project",
                    "passages": [[1, 2]],
                },
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "School zoning application",
                    "passages": [[3, 3]],
                },
            ]
        },
        original,
        document,
    )
    assert result["status"] == "complete"
    assert result["cards"][0]["passages"][0]["text"].endswith("Motion failed, 2-3.\n")
    assert result["cards"][1]["passages"][0]["text"] == document.units[2].text
    invalid = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "Invented",
                    "passages": [[4, 4]],
                }
            ]
        },
        [],
        document,
    )
    assert invalid["status"] == "partial"
    assert not invalid["cards"]


def test_review_trims_neighbor_without_losing_shared_budget_heading():
    document = index_source(
        "Proposed 2027 budget\nSchool project $1M\nBridge project $500,000\n"
    )
    original = bind_evidence(
        {"items": [{"title": 3, "passages": [[1, 3]]}]},
        document,
        evidence_windows(document)[0],
    )["cards"]
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": 0,
                    "title": "Bridge project",
                    "passages": [[1, 1], [3, 3]],
                }
            ]
        },
        original,
        document,
    )
    assert result["status"] == "complete"
    texts = [span["text"] for span in result["cards"][0]["passages"]]
    assert texts == ["Proposed 2027 budget\n", "Bridge project $500,000\n"]
    original[0]["passages"][0]["source_text_sha256"] = "changed"
    changed = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": 0,
                    "title": "Bridge project",
                    "passages": [[3, 3]],
                }
            ]
        },
        original,
        document,
    )
    assert changed["status"] == "invalid"
    assert "Candidate source changed" in changed["errors"][0]


@pytest.mark.parametrize(
    ("text", "retained"),
    [
        ("c) Property Maintenance Ordinances – moving forward with enforcement", False),
        ("Zoning violations report: none", False),
        ("Property maintenance ordinance amendment proposed", True),
        ("Property maintenance enforcement at 14 Main Street", True),
        ("Property maintenance ordinances adopted", True),
        ("Zoning complaints: 3", True),
    ],
)
def test_generic_reports_cannot_hide_named_cases_or_policy_changes(text, retained):
    document = index_source(text + "\n")
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": text,
                    "passages": [[1, 1]],
                }
            ]
        },
        [],
        document,
    )
    assert result["status"] == "complete"
    assert bool(result["cards"]) is retained


def test_direct_read_binds_source_without_candidate_index_metadata():
    document = index_source("Bridge project was tabled.\n")
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": 8,
                    "title": "Bridge project",
                    "passages": [[1, 1]],
                }
            ]
        },
        [],
        document,
    )
    assert result["status"] == "complete"
    assert result["cards"][0]["passages"][0]["text"] == document.text


def test_future_budget_heading_is_recovered_without_neighboring_projects():
    document = index_source(
        "• Budget Planning for 2027\n"
        "o Pond repair $18,000\n"
        "o Westridge Drive repaving estimate $230,000\n"
        "• New Business\n"
        "o Approval of unrelated contract\n"
    )
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "Westridge Drive",
                    "passages": [[3, 3]],
                }
            ]
        },
        [],
        document,
    )
    assert result["status"] == "complete"
    assert [span["text"] for span in result["cards"][0]["passages"]] == [
        "• Budget Planning for 2027\n",
        "o Westridge Drive repaving estimate $230,000\n",
    ]
    unrelated = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "unrelated contract",
                    "passages": [[5, 5]],
                }
            ]
        },
        [],
        document,
    )
    assert len(unrelated["cards"][0]["passages"]) == 1


@pytest.mark.parametrize("budget_heading", ["2026 BUDGET", "• 2026 BUDGET"])
def test_budget_context_stops_before_an_unmarked_report(budget_heading):
    document = index_source(
        f"{budget_heading}\n"
        "Council approved the budget.\n"
        "ENGINEER'S REPORT\n"
        "South Street Restoration Project is complete.\n"
    )
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "South Street Restoration Project",
                    "passages": [[4, 4]],
                }
            ]
        },
        [],
        document,
    )
    assert result["status"] == "complete"
    assert result["cards"][0]["context_passages"] == []


def test_budget_adoption_sentence_does_not_become_an_unrelated_section_heading():
    document = index_source(
        "▪ 2024 BUDGET\n"
        "Council authorized advertisement of the\n"
        "proposed 2024 budget for public inspection and adoption in December.\n"
        "▪ 2024-2027 COMMUNITY DEVELOPMENT BLOCK GRANT PROJECTS\n"
        "Applications for planning grants are due in January.\n"
        "▪ NEW BUSINESS\n"
        "A transportation study will be presented in December.\n"
    )
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "planning grants",
                    "passages": [[4, 5]],
                },
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "transportation study",
                    "passages": [[7, 7]],
                },
            ]
        },
        [],
        document,
    )
    assert result["status"] == "complete"
    assert all(not card["context_passages"] for card in result["cards"])
    assert all(
        "adoption" not in passage["text"]
        for card in result["cards"]
        for passage in card["passages"]
    )


@pytest.mark.parametrize("bullet", ["•", "*"])
def test_inline_bullets_are_separable_without_changing_original_bytes(bullet):
    original = f"{bullet} Alpha extension denied. {bullet} Bravo extension approved.\n"
    document, pages = source_document([{"page": 1, "text": original}])
    assert document.text[: len(original)] == original
    assert pages[0]["end"] == len(original)
    assert document.units[0].text == f"{bullet} Alpha extension denied. "
    assert document.units[1].text == f"{bullet} Bravo extension approved.\n"
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "Alpha extension",
                    "passages": [[1, 1]],
                }
            ]
        },
        [],
        document,
    )
    assert result["status"] == "complete"
    passage = result["cards"][0]["passages"][0]
    assert passage["text"] == original[passage["start"] : passage["end"]]
    assert "denied" in passage["text"] and "approved" not in passage["text"]


def test_vote_closure_can_be_selected_without_the_following_unrelated_subject():
    original = "Alpha variance denied. Motion carried\nunanimously. Mr. Brown asked about Bravo.\n"
    document, _ = source_document([{"page": 1, "text": original}])
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "Alpha variance",
                    "passages": [[1, 2]],
                }
            ]
        },
        [],
        document,
    )
    passage = result["cards"][0]["passages"][0]["text"]
    assert "Motion carried\nunanimously." in passage
    assert "Bravo" not in passage


def test_adjacent_acronym_heading_identifies_a_facility_opening():
    document, _ = source_document(
        [
            {
                "page": 1,
                "text": "YMCA\nThey expect to open on August 3.\nCommittee Reports\n",
            }
        ]
    )
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "open on August 3",
                    "passages": [[2, 2]],
                }
            ]
        },
        [],
        document,
    )
    assert (
        result["cards"][0]["passages"][0]["text"]
        == "YMCA\nThey expect to open on August 3.\n"
    )


def test_wrapped_acronym_does_not_attach_to_a_new_named_subject():
    document, _ = source_document(
        [
            {
                "page": 1,
                "text": (
                    "Loius Diaz: A complaint was filed with the\n"
                    "DJ\n"
                    "Rock Realty asked what they can do with 286 N. Main.\n"
                ),
            }
        ]
    )
    result = bind_review(
        {
            "items": [
                {
                    "index": None,
                    "title": "Loius Diaz",
                    "passages": [[1, 2]],
                    "context": [],
                    "references": [],
                },
                {
                    "index": None,
                    "title": "286 N. Main",
                    "passages": [[3, 3]],
                    "context": [],
                    "references": [],
                },
            ]
        },
        [],
        document,
    )
    assert result["status"] == "complete"
    assert result["cards"][0]["subject_passages"][0]["text"].endswith("DJ\n")
    assert result["cards"][1]["context_passages"] == []


def test_uppercase_previous_vote_is_not_a_heading_for_another_property():
    document, _ = source_document(
        [
            {
                "page": 1,
                "text": "MOTION PASSED UNANIMOUSLY\nBravo requests its variance.\n",
            }
        ]
    )
    result = bind_review(
        {
            "items": [
                {
                    "context": [],
                    "references": [],
                    "index": None,
                    "title": "Bravo",
                    "passages": [[2, 2]],
                }
            ]
        },
        [],
        document,
    )
    assert result["cards"][0]["passages"][0]["text"] == "Bravo requests its variance.\n"
