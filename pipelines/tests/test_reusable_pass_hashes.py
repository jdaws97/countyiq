"""Reusable pass hashes require current accepted serving projections."""

import pytest

from countyiq.lib.intelligence_common import fetch_reusable_pass_hashes


class FakeDatabase:
    def __init__(self, rows):
        self.rows = rows
        self.query = ""
        self.params = None

    def execute(self, query, params=None):
        self.query = " ".join(query.split())
        self.params = params
        return self.rows


def test_pass1_hashes_require_entity_projection_or_completed_empty_partition():
    database = FakeDatabase([{"pidn": "cluster", "input_hash": "hash"}])

    hashes = fetch_reusable_pass_hashes(database, pass_number=1)

    assert hashes == {"cluster": "hash"}
    assert "disposition = 'accepted'" in database.query
    assert "FROM public.entity_graph" in database.query
    assert "completed.status = 'complete'" in database.query
    assert database.params == {
        "pass_number": 1,
        "output_kind": "entity_verification",
    }


def test_pass2_hashes_require_live_evidence_projection():
    database = FakeDatabase([("parcel", "hash")])

    hashes = fetch_reusable_pass_hashes(database, pass_number=2)

    assert hashes == {"parcel": "hash"}
    assert "FROM public.evidence" in database.query
    assert "completed.status" not in database.query
    assert database.params == {
        "pass_number": 2,
        "output_kind": "signal_validation",
    }


def test_reusable_hashes_reject_undefined_pass_mapping():
    with pytest.raises(ValueError, match="only for Passes 1 and 2"):
        fetch_reusable_pass_hashes(FakeDatabase([]), pass_number=3)
