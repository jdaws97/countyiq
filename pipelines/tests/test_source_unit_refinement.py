"""Joint motions can retain separate subjects and one shared outcome."""

import pytest
from countyiq.lib.municipal_evidence import bind_review
from countyiq.lib.pass0_source import index_source
from countyiq.lib.source_unit_refinement import refine_source_units


def test_joint_motion_preserves_both_cases_and_exact_shared_outcome():
    source = index_source(
        "Smucker Subdivision and Marsteller/Rhineholt Subdivision: "
        "A motion was made to table both plans pending additional information.\n"
    )
    refined = refine_source_units(
        source,
        {
            "source_text_sha256": source.sha256,
            "offsets": [
                source.text.index(" and "),
                source.text.index("Marsteller"),
                source.text.index(": "),
            ],
        },
    )
    result = bind_review(
        {
            "items": [
                {
                    "index": None,
                    "title": title,
                    "passages": [[unit, unit]],
                    "context": [[4, 4]],
                    "references": [],
                }
                for title, unit in [
                    ("Smucker Subdivision", 1),
                    ("Marsteller/Rhineholt Subdivision", 3),
                ]
            ]
        },
        [],
        refined,
    )
    assert result["status"] == "complete", result["errors"]
    assert len(result["cards"]) == 2
    assert refined.text == source.text
    assert refined.sha256 == source.sha256
    assert "".join(unit.text for unit in refined.units) == source.text
    for card in result["cards"]:
        assert "table both plans" in card["context_passages"][0]["text"]


def test_refinement_rejects_changed_source_and_changed_accounting_filter():
    source = index_source("Bills List\nVendor Account Amount\nABC 100.00\n")
    with pytest.raises(ValueError, match="source hash"):
        refine_source_units(source, {"source_text_sha256": "old", "offsets": [5]})
    with pytest.raises(ValueError, match="accounting exclusion"):
        refine_source_units(
            source, {"source_text_sha256": source.sha256, "offsets": [5]}
        )
