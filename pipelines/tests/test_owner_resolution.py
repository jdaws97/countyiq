"""Unit tests for the pure-Python parts of owner entity resolution."""

from countyiq.assets.enrichment.owners import (
    _UnionFind,
    _shared_business_address_groups,
    classify_entity,
    classify_group,
    normalize_mail_addr,
    normalize_name,
)


class TestNormalizeName:
    def test_strips_entity_suffixes_iteratively(self):
        assert normalize_name("SMITH LLC INC") == "SMITH"

    def test_strips_person_suffixes(self):
        assert normalize_name("SMITH JOHN A JR") == "SMITH JOHN A"

    def test_collapses_whitespace_and_case(self):
        assert normalize_name("  smith   john ") == "SMITH JOHN"

    def test_removes_parentheticals(self):
        assert normalize_name("SMITH JOHN (ESTATE OF)") == "SMITH JOHN"

    def test_empty(self):
        assert normalize_name("") == ""
        assert normalize_name(None) == ""


class TestNormalizeMailAddr:
    def test_normalizes_punctuation_and_case(self):
        assert normalize_mail_addr("123 Main St., York PA") == "123 MAIN ST YORK PA"

    def test_rejects_short_fragments(self):
        assert normalize_mail_addr("YORK PA") == ""

    def test_none_and_empty(self):
        assert normalize_mail_addr(None) == ""
        assert normalize_mail_addr("") == ""


class TestClassifyEntity:
    def test_person(self):
        assert classify_entity("SMITH JOHN A") == "person"

    def test_business(self):
        assert classify_entity("MAPLE ST HOLDINGS LLC") == "business"

    def test_trust(self):
        assert classify_entity("SMITH FAMILY TRUST") == "trust"

    def test_government(self):
        assert classify_entity("COUNTY OF YORK") == "government"
        assert classify_entity("SPRINGETTSBURY TOWNSHIP") == "government"

    def test_government_beats_business_terms(self):
        # "AUTHORITY" is government even though authorities are corporate bodies
        assert classify_entity("YORK CITY SEWER AUTHORITY") == "government"


class TestClassifyGroup:
    def test_priority_vote(self):
        # A group containing a trust variant and a person variant is a trust
        assert classify_group(["SMITH JOHN", "SMITH JOHN LIVING TRUST"]) == "trust"

    def test_all_person(self):
        assert classify_group(["SMITH JOHN", "SMITH JOHN A"]) == "person"

    def test_government_wins(self):
        assert (
            classify_group(["YORK PROPERTIES LLC", "COUNTY OF YORK"]) == "government"
        )


class TestUnionFind:
    def test_union_and_find(self):
        uf = _UnionFind()
        assert uf.union("a", "b") is True
        assert uf.union("b", "c") is True
        assert uf.find("a") == uf.find("c")

    def test_redundant_union_returns_false(self):
        uf = _UnionFind()
        uf.union("a", "b")
        assert uf.union("a", "b") is False

    def test_disjoint_sets_stay_disjoint(self):
        uf = _UnionFind()
        uf.union("a", "b")
        uf.union("x", "y")
        assert uf.find("a") != uf.find("x")


def test_shared_business_address_is_ambiguity_evidence_not_a_union():
    groups = {
        "ALPHA HOLDINGS": ["ALPHA HOLDINGS LLC"],
        "BETA PROPERTIES": ["BETA PROPERTIES LLC"],
        "SMITH JOHN": ["SMITH JOHN"],
    }
    types = {
        "ALPHA HOLDINGS": "business",
        "BETA PROPERTIES": "business",
        "SMITH JOHN": "person",
    }
    addresses = {
        "ALPHA HOLDINGS LLC": "10 REGISTERED AGENT WAY YORK PA",
        "BETA PROPERTIES LLC": "10 REGISTERED AGENT WAY YORK PA",
        "SMITH JOHN": "10 REGISTERED AGENT WAY YORK PA",
    }

    ambiguous = _shared_business_address_groups(groups, types, addresses)

    assert ambiguous == {
        "10 REGISTERED AGENT WAY YORK PA": [
            "ALPHA HOLDINGS",
            "BETA PROPERTIES",
        ]
    }
    uf = _UnionFind()
    assert uf.find("ALPHA HOLDINGS") != uf.find("BETA PROPERTIES")
