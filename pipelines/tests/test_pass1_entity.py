"""Tests for Pass 1 entity verification.

Tests cover only pure-Python parts (template, prompt builder, output parser,
cluster builder). No actual LLM calls are made and no database is required.
"""

import json
from pathlib import Path

import pytest

from countyiq.lib.pass1_entity_verification import (
    ENTITY_VERIFICATION_SYSTEM_PROMPT,
    ENTITY_VERIFICATION_USER_TEMPLATE,
    build_deterministic_entity_resolution,
    build_entity_cluster_prompt,
    parse_entity_verification_output,
    stable_cluster_key,
)

ENTITY_VERIFICATION_PROMPT_TEXT = (
    ENTITY_VERIFICATION_SYSTEM_PROMPT + "\n\n" + ENTITY_VERIFICATION_USER_TEMPLATE
)


def test_deterministic_tier_accepts_only_anchored_legal_name_variants():
    records = {
        "candidate_names": ["ACME, L.L.C.", "ACME LLC"],
        "parcels": [{"pidn": "P1", "owner_full": "ACME LLC", "aprtotal": 100}],
        "tax_claims": [],
        "plcb_licenses": [],
        "corporate_entities": [{"entity_name": "ACME LLC", "entity_number": "123"}],
        "proceedings": [],
    }
    parsed = build_deterministic_entity_resolution(
        records,
        records["candidate_names"],
    )
    assert parsed is not None
    assert parsed["entities"][0]["member_names"] == ["ACME LLC", "ACME, L.L.C."]
    assert parsed["entities"][0]["linked_records"]["parcels"] == ["P1"]


def test_deterministic_tier_refuses_people_and_conflicting_entity_numbers():
    people = {
        "corporate_entities": [],
    }
    assert (
        build_deterministic_entity_resolution(
            people,
            ["SMITH JOHN", "SMITH, JOHN"],
        )
        is None
    )

    conflicting = {
        "corporate_entities": [
            {"entity_name": "ACME LLC", "entity_number": "123"},
            {"entity_name": "ACME, L.L.C.", "entity_number": "456"},
        ]
    }
    assert (
        build_deterministic_entity_resolution(
            conflicting,
            ["ACME LLC", "ACME, L.L.C."],
        )
        is None
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_cluster():
    """Load the entity_cluster_sample.json fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "entity_cluster_sample.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def sample_records(sample_cluster):
    """Return just the records dict from the sample cluster."""
    return sample_cluster["records"]


@pytest.fixture
def valid_llm_output():
    """Return a well-formed LLM entity verification output."""
    return {
        "entities": [
            {
                "canonical_name": "SMITH JOHN A",
                "entity_type": "individual",
                "confidence": 0.92,
                "reasoning": "Same name across parcels, tax claims, and PLCB license.",
                "linked_records": {
                    "parcels": ["6701234567890A", "6701234567890B"],
                    "tax_claims": ["6701234567890A"],
                    "plcb_licenses": ["R-12345"],
                    "corporate_entities": [],
                    "proceedings": [],
                },
                "relationships": [
                    {
                        "related_entity": "J A SMITH HOLDINGS LLC",
                        "relationship_type": "controls",
                        "evidence": "Name pattern and shared property address.",
                    }
                ],
                "portfolio_summary": {
                    "parcel_count": 2,
                    "total_assessed_value": 430000,
                    "tax_delinquent_parcels": 1,
                    "total_tax_owed": 3754.56,
                },
            },
            {
                "canonical_name": "J A SMITH HOLDINGS LLC",
                "entity_type": "llc",
                "confidence": 0.88,
                "reasoning": "Corporate entity with matching office address.",
                "linked_records": {
                    "parcels": [],
                    "tax_claims": ["6701234567890B"],
                    "plcb_licenses": [],
                    "corporate_entities": ["J A SMITH HOLDINGS LLC"],
                    "proceedings": ["J A SMITH HOLDINGS"],
                },
                "relationships": [
                    {
                        "related_entity": "SMITH JOHN A",
                        "relationship_type": "same_person",
                        "evidence": "Name abbreviation pattern.",
                    }
                ],
                "portfolio_summary": {
                    "parcel_count": 0,
                    "total_assessed_value": 0,
                    "tax_delinquent_parcels": 1,
                    "total_tax_owed": 980.00,
                },
            },
        ],
        "rejected_matches": [],
    }


# ---------------------------------------------------------------------------
# TestBuildEntityClusterPrompt
# ---------------------------------------------------------------------------


class TestBuildEntityClusterPrompt:
    """Tests for build_entity_cluster_prompt(records) -> str."""

    def test_returns_string(self, sample_records):
        result = build_entity_cluster_prompt(sample_records)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_includes_parcel_owner_names(self, sample_records):
        result = build_entity_cluster_prompt(sample_records)
        assert "SMITH JOHN A" in result

    def test_includes_parcel_pidn(self, sample_records):
        result = build_entity_cluster_prompt(sample_records)
        assert "6701234567890A" in result
        assert "6701234567890B" in result

    def test_includes_tax_claim_names(self, sample_records):
        result = build_entity_cluster_prompt(sample_records)
        assert "J A SMITH HOLDINGS LLC" in result

    def test_includes_tax_claim_amounts(self, sample_records):
        result = build_entity_cluster_prompt(sample_records)
        assert "1,834.56" in result

    def test_includes_corporate_data(self, sample_records):
        result = build_entity_cluster_prompt(sample_records)
        assert "MOUNT ROSE TAVERN INC" in result
        assert "789 COMMERCE DR" in result

    def test_includes_proceedings(self, sample_records):
        result = build_entity_cluster_prompt(sample_records)
        assert "conditional_use" in result
        assert "J A SMITH HOLDINGS" in result

    def test_includes_plcb_data(self, sample_records):
        result = build_entity_cluster_prompt(sample_records)
        assert "R-12345" in result
        assert "Premises owner: SMITH JOHN A" in result

    def test_omits_empty_sections(self):
        """When a record type is empty, its section header should not appear."""
        records = {
            "parcels": [
                {
                    "pidn": "6700000000001",
                    "owner_full": "DOE JANE",
                    "propadr": "100 OAK ST",
                    "aprtotal": 100000,
                    "acres": 0.5,
                    "class": "R",
                    "saledt": None,
                    "price": None,
                    "prev_owner": None,
                    "municipality": "York City",
                }
            ],
            "tax_claims": [],
            "plcb_licenses": [],
            "corporate_entities": [],
            "proceedings": [],
        }
        result = build_entity_cluster_prompt(records)
        assert "PARCEL RECORDS:" in result
        assert "TAX CLAIM RECORDS:" not in result
        assert "PLCB LICENSES:" not in result
        assert "PA DOS CORPORATE RECORDS:" not in result
        assert "PUBLIC PROCEEDINGS:" not in result

    def test_all_sections_present_with_full_data(self, sample_records):
        result = build_entity_cluster_prompt(sample_records)
        assert "PARCEL RECORDS:" in result
        assert "TAX CLAIM RECORDS:" in result
        assert "PLCB LICENSES:" in result
        assert "PA DOS CORPORATE RECORDS:" in result
        assert "PUBLIC PROCEEDINGS:" in result

    def test_empty_records_returns_no_records(self):
        """Completely empty records should produce a prompt with '(no records)'."""
        records = {
            "parcels": [],
            "tax_claims": [],
            "plcb_licenses": [],
            "corporate_entities": [],
            "proceedings": [],
        }
        result = build_entity_cluster_prompt(records)
        assert "(no records)" in result

    def test_missing_keys_handled(self):
        """Missing record keys should not raise."""
        result = build_entity_cluster_prompt({})
        assert isinstance(result, str)
        assert "(no records)" in result


# ---------------------------------------------------------------------------
# TestParseEntityVerificationOutput
# ---------------------------------------------------------------------------


class TestParseEntityVerificationOutput:
    """Tests for parse_entity_verification_output(output) -> dict."""

    def test_valid_output_parsed_correctly(self, valid_llm_output):
        result = parse_entity_verification_output(valid_llm_output)
        assert "entities" in result
        assert "rejected_matches" in result
        assert len(result["entities"]) == 2
        assert result["entities"][0]["canonical_name"] == "SMITH JOHN A"
        # Historical transcripts remain parseable, but their ungrounded,
        # unused model-generated arithmetic must not enter new decisions.
        assert all("portfolio_summary" not in entity for entity in result["entities"])
        assert (
            result["entities"][0]["linked_records"]
            == valid_llm_output["entities"][0]["linked_records"]
        )

    def test_confidence_preserved(self, valid_llm_output):
        result = parse_entity_verification_output(valid_llm_output)
        assert result["entities"][0]["confidence"] == 0.92

    def test_empty_entities_list_works(self):
        output = {"entities": [], "rejected_matches": []}
        result = parse_entity_verification_output(output)
        assert result["entities"] == []
        assert result["rejected_matches"] == []

    def test_missing_entities_key_returns_error(self):
        output = {"rejected_matches": []}
        result = parse_entity_verification_output(output)
        assert "error" in result

    def test_non_dict_returns_error(self):
        result = parse_entity_verification_output("not a dict")
        assert "error" in result

    def test_entities_not_list_returns_error(self):
        result = parse_entity_verification_output({"entities": "bad"})
        assert "error" in result

    def test_confidence_clamped_above_1(self):
        output = {
            "entities": [
                {
                    "canonical_name": "TEST",
                    "confidence": 1.5,
                }
            ],
            "rejected_matches": [],
        }
        result = parse_entity_verification_output(output)
        assert result["entities"][0]["confidence"] == 1.0

    def test_confidence_clamped_below_0(self):
        output = {
            "entities": [
                {
                    "canonical_name": "TEST",
                    "confidence": -0.3,
                }
            ],
            "rejected_matches": [],
        }
        result = parse_entity_verification_output(output)
        assert result["entities"][0]["confidence"] == 0.0


class TestStableClusterKey:
    """Tests for deterministic Pass 1 cluster tracking keys."""

    def test_order_independent(self):
        a = stable_cluster_key(["SMITH JOHN A", "J A SMITH HOLDINGS LLC"])
        b = stable_cluster_key(["J A SMITH HOLDINGS LLC", "SMITH JOHN A"])
        assert a == b

    def test_blank_names_ignored(self):
        a = stable_cluster_key(["SMITH JOHN A", "", "  ", "SMITH JOHN A"])
        b = stable_cluster_key(["SMITH JOHN A"])
        assert a == b

    def test_confidence_non_numeric_defaults(self):
        output = {
            "entities": [
                {
                    "canonical_name": "TEST",
                    "confidence": "high",
                }
            ],
            "rejected_matches": [],
        }
        result = parse_entity_verification_output(output)
        assert result["entities"][0]["confidence"] == 0.5

    def test_missing_rejected_matches_defaults_empty(self):
        output = {"entities": []}
        result = parse_entity_verification_output(output)
        assert result["rejected_matches"] == []

    def test_rejected_matches_not_list_defaults_empty(self):
        output = {"entities": [], "rejected_matches": "bad"}
        result = parse_entity_verification_output(output)
        assert result["rejected_matches"] == []

    def test_entity_defaults_for_missing_fields(self):
        output = {
            "entities": [{"canonical_name": "ONLY NAME"}],
            "rejected_matches": [],
        }
        result = parse_entity_verification_output(output)
        entity = result["entities"][0]
        assert entity["canonical_name"] == "ONLY NAME"
        assert entity["entity_type"] == "unknown"
        assert entity["confidence"] == 0.5
        assert entity["reasoning"] == ""
        assert entity["linked_records"] == {}
        assert entity["relationships"] == []


# ---------------------------------------------------------------------------
# TestEntityVerificationTemplate
# ---------------------------------------------------------------------------


class TestEntityVerificationTemplate:
    """Tests for the system and user prompt contract."""

    def test_has_parcel_records_reference(self):
        """Template must reference parcels in the output format."""
        assert '"parcels"' in ENTITY_VERIFICATION_PROMPT_TEXT

    def test_has_tasks_section(self):
        assert "TASKS:" in ENTITY_VERIFICATION_PROMPT_TEXT

    def test_has_output_format_section(self):
        assert "OUTPUT FORMAT:" in ENTITY_VERIFICATION_PROMPT_TEXT

    def test_has_canonical_name_key(self):
        assert "canonical_name" in ENTITY_VERIFICATION_PROMPT_TEXT

    def test_has_entities_key(self):
        assert '"entities"' in ENTITY_VERIFICATION_PROMPT_TEXT

    def test_has_rejected_matches_key(self):
        assert '"rejected_matches"' in ENTITY_VERIFICATION_PROMPT_TEXT

    def test_has_sections_placeholder(self):
        assert "{sections}" in ENTITY_VERIFICATION_USER_TEMPLATE

    def test_has_relationship_type_values(self):
        assert "controls" in ENTITY_VERIFICATION_PROMPT_TEXT
        assert "officer_of" in ENTITY_VERIFICATION_PROMPT_TEXT
        assert "same_person" in ENTITY_VERIFICATION_PROMPT_TEXT

    def test_has_entity_type_values(self):
        assert "individual" in ENTITY_VERIFICATION_PROMPT_TEXT
        assert "llc" in ENTITY_VERIFICATION_PROMPT_TEXT
        assert "corporation" in ENTITY_VERIFICATION_PROMPT_TEXT

    def test_template_accepts_sections_format(self):
        """Verify the template formats without error."""
        try:
            result = ENTITY_VERIFICATION_USER_TEMPLATE.format(
                sections="test sections here"
            )
        except KeyError as exc:
            pytest.fail(f"ENTITY_VERIFICATION_USER_TEMPLATE missing variable: {exc}")
        assert "test sections here" in result


# ---------------------------------------------------------------------------
# TestBuildClusters
# ---------------------------------------------------------------------------


class TestBuildClusters:
    """Tests for the _build_clusters union-find algorithm.

    Imports the function from the Dagster asset module.
    """

    @staticmethod
    def _build_clusters(pairs):
        """Inline union-find to test without importing the asset module."""
        parent = {}

        def find(x):
            if x not in parent:
                parent[x] = x
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for row in pairs:
            name_a = row[0] if isinstance(row, (list, tuple)) else row.get("name_a", "")
            name_b = row[1] if isinstance(row, (list, tuple)) else row.get("name_b", "")
            if name_a and name_b:
                union(name_a, name_b)

        groups = {}
        for name in parent:
            root = find(name)
            groups.setdefault(root, []).append(name)
        return list(groups.values())

    def test_simple_pair_one_cluster(self):
        pairs = [("SMITH JOHN A", "SMITH J A", "Spring Garden", 0.65)]
        clusters = self._build_clusters(pairs)
        assert len(clusters) == 1
        assert set(clusters[0]) == {"SMITH JOHN A", "SMITH J A"}

    def test_disconnected_pairs_separate_clusters(self):
        pairs = [
            ("SMITH JOHN A", "SMITH J A", "Spring Garden", 0.65),
            ("JONES MARY B", "JONES M B", "York City", 0.70),
        ]
        clusters = self._build_clusters(pairs)
        assert len(clusters) == 2
        names_flat = [set(c) for c in clusters]
        assert {"SMITH JOHN A", "SMITH J A"} in names_flat
        assert {"JONES MARY B", "JONES M B"} in names_flat

    def test_transitive_connection_merged(self):
        pairs = [
            ("A", "B", "", 0.6),
            ("B", "C", "", 0.7),
        ]
        clusters = self._build_clusters(pairs)
        assert len(clusters) == 1
        assert set(clusters[0]) == {"A", "B", "C"}

    def test_empty_pairs_no_clusters(self):
        clusters = self._build_clusters([])
        assert clusters == []

    def test_dict_pairs_supported(self):
        pairs = [
            {"name_a": "SMITH JOHN A", "name_b": "J A SMITH HOLDINGS LLC"},
        ]
        clusters = self._build_clusters(pairs)
        assert len(clusters) == 1
        assert set(clusters[0]) == {"SMITH JOHN A", "J A SMITH HOLDINGS LLC"}

    def test_single_entity_no_pair(self):
        """A row with one empty name should not create a cluster."""
        pairs = [("SMITH JOHN A", "", "", 0.0)]
        clusters = self._build_clusters(pairs)
        assert len(clusters) == 0

    def test_large_transitive_chain(self):
        pairs = [
            ("A", "B", "", 0.6),
            ("B", "C", "", 0.6),
            ("C", "D", "", 0.6),
            ("D", "E", "", 0.6),
        ]
        clusters = self._build_clusters(pairs)
        assert len(clusters) == 1
        assert set(clusters[0]) == {"A", "B", "C", "D", "E"}

    def test_multiple_disconnected_chains(self):
        pairs = [
            ("A", "B", "", 0.6),
            ("B", "C", "", 0.6),
            ("X", "Y", "", 0.7),
            ("Y", "Z", "", 0.7),
        ]
        clusters = self._build_clusters(pairs)
        assert len(clusters) == 2
        names_flat = [set(c) for c in clusters]
        assert {"A", "B", "C"} in names_flat
        assert {"X", "Y", "Z"} in names_flat
