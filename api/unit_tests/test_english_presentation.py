from copy import deepcopy

from api.lib.english_presentation import present_receipt, present_record
from api.lib.source_locations import locate_feed_sources


def test_translation_retains_verified_start_page_without_reusing_original_offsets():
    source = {
        "id": "P1",
        "text": "Audiencia pública propuesta: 8 de septiembre de 2026.",
    }
    explanation = {
        "presentation_language": "en",
        "source_presentations": [
            {
                "source_id": "P1",
                "language": "es",
                "english_text": "Proposed public hearing: September 8, 2026.",
            }
        ],
    }
    receipt = {
        "excerpt": source["text"],
        "details": {
            "passages": [
                {"text": "Audiencia pública", "page": 2},
                {"text": "propuesta: 8 de septiembre de 2026.", "page": 3},
            ]
        },
    }
    original = deepcopy(source)
    present_receipt(receipt, source, explanation)
    assert receipt["details"]["translated"] is True
    assert receipt["details"]["passages"] == [
        {"text": "Proposed public hearing: September 8, 2026.", "page": 2}
    ]
    assert source == original
    record = {
        "dates": [{"source_id": "P1", "quote": source["text"], "status": "proposed"}]
    }
    presented = present_record(record, [source], explanation)
    assert presented["dates"][0]["quote"] == receipt["excerpt"]
    assert presented["dates"][0]["status"] == "proposed"
    assert record["dates"][0]["quote"] == original["text"]


def test_missing_translation_cannot_fall_back_to_spanish():
    source = {"id": "P1", "text": "Audiencia pública"}
    receipt = {
        "excerpt": source["text"],
        "details": {"passages": [{"text": source["text"], "page": 1}]},
    }
    present_receipt(
        receipt, source, {"presentation_language": "en", "source_presentations": []}
    )
    assert receipt["excerpt"] is None
    assert receipt["details"]["passages"] == []


def test_feed_with_unavailable_current_record_never_serves_old_spanish_copy():
    class Cursor:
        def execute(self, *_args):
            pass

        def fetchall(self):
            return []

    rows = [
        {
            "event_key": "test",
            "source_kind": "municipal_evidence",
            "title": "Audiencia pública",
            "what_happened": "Fecha propuesta",
            "source_evidence": [
                {
                    "excerpt": "Fecha propuesta",
                    "details": {
                        "decision_scope": "Permiso",
                        "record_dates": [{"quote": "Fecha propuesta"}],
                    },
                }
            ],
        }
    ]
    locate_feed_sources(Cursor(), rows)
    assert rows[0]["title"] == "Municipal record"
    assert rows[0]["source_evidence"][0]["excerpt"] is None
    assert "record_dates" not in rows[0]["source_evidence"][0]["details"]
