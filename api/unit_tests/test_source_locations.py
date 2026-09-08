from api.lib.source_locations import (
    locate_feed_sources,
    municipal_source_details,
    page_passages,
)


def test_page_passages_splits_known_pages_and_preserves_unknown_whitespace_gaps():
    text = "Alpha \nBeta gamma"
    passages = page_passages(
        [{"text": text, "start": 10, "end": 10 + len(text)}],
        [
            {"start": 10, "end": 16, "page": 5},
            {"start": 18, "end": 25, "page": 6},
        ],
    )

    assert passages == [
        {"text": "Alpha ", "page": 5},
        {"text": "\nB", "page": None},
        {"text": "eta gam", "page": 6},
        {"text": "ma", "page": None},
    ]
    assert "".join(passage["text"] for passage in passages) == text


def test_page_passages_invalid_metadata_never_invents_a_page():
    assert page_passages(
        [
            {"text": "Missing offsets", "start": None, "end": 15},
            {"text": "Wrong length", "start": 0, "end": 1},
        ],
        [{"start": 0, "end": 99, "page": 7}],
    ) == [
        {"text": "Missing offsets", "page": None},
        {"text": "Wrong length", "page": None},
    ]


def source_record():
    return {
        "document_url": "https://borough.example.test/agenda.pdf",
        "body_name": "Borough Council",
        "meeting_date": "2026-09-10",
        "card": {
            "passages": [
                {"text": "Repeated wording", "start": 0, "end": 16},
                {"text": "Repeated wording", "start": 20, "end": 36},
            ]
        },
        "payload": {
            "document_kind": "agenda",
            "pages": [
                {"start": 0, "end": 16, "page": 2},
                {"start": 20, "end": 36, "page": 3},
            ],
        },
    }


def test_municipal_source_details_requires_exact_document_and_wording():
    record = source_record()
    source = {
        "document_url": record["document_url"],
        "excerpt": "Repeated wording",
        "explanation_source_id": "P2",
    }

    details = municipal_source_details(source, record)

    assert details["body_name"] == "Borough Council"
    assert details["document_kind"] == "agenda"
    assert details["passages"] == [{"text": "Repeated wording", "page": 3}]
    assert (
        municipal_source_details(
            {**source, "document_url": "https://other.example.test/agenda.pdf"}, record
        )
        == {}
    )
    assert (
        municipal_source_details({**source, "excerpt": "Similar wording"}, record) == {}
    )


def test_municipal_source_details_uses_p_index_to_disambiguate_repeated_spans():
    source = {
        "document_url": "https://borough.example.test/agenda.pdf",
        "excerpt": "Repeated wording",
        "explanation_source_id": "P1",
    }

    details = municipal_source_details(source, source_record())

    assert details["passages"] == [{"text": "Repeated wording", "page": 2}]


def test_locate_feed_sources_batches_current_view_records_and_enriches_only_matches():
    class Cursor:
        def __init__(self):
            self.calls = []

        def execute(self, statement, params):
            self.calls.append((statement, params))

        def fetchall(self):
            return [{"event_key": "municipal:1:abc:card1", **source_record()}]

    matching_source = {
        "document_url": "https://borough.example.test/agenda.pdf",
        "excerpt": "Repeated wording",
        "explanation_source_id": "P2",
        "details": {"existing": "kept"},
    }
    rows = [
        {
            "event_key": "municipal:1:abc:card1",
            "source_kind": "municipal_evidence",
            "source_evidence": [matching_source],
        },
        {
            "event_key": "municipal:2:abc:card2",
            "source_kind": "municipal_evidence",
            "source_evidence": [matching_source.copy()],
        },
        {"event_key": "parcel-a", "source_kind": "parcel", "source_evidence": []},
    ]
    cursor = Cursor()

    locate_feed_sources(cursor, rows)

    assert cursor.calls[0][1] == (
        [1, 2],
        ["municipal:1:abc:card1", "municipal:2:abc:card2"],
    )
    assert rows[0]["source_evidence"][0]["details"] == {
        "existing": "kept",
        "body_name": "Borough Council",
        "document_kind": "agenda",
        "meeting_date": "2026-09-10",
        "passages": [],
        "translated": False,
    }
    assert rows[1]["source_evidence"][0]["details"] == {
        "existing": "kept",
        "passages": [],
        "translated": False,
    }
    assert rows[0]["source_evidence"][0]["excerpt"] is None
