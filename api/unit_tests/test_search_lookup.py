"""Focused tests for deterministic parcel lookup normalization and ranking."""

from pathlib import Path

from api.routes.search import (
    SCHOOL_DISTRICTS,
    _deduplicate_and_rank,
    _lookup_variants,
    _pidn_candidate,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_york_school_district_codes_match_the_county_codebook():
    expected = {
        "002": "Central York",
        "004": "Dallastown",
        "006": "Dover",
        "008": "Eastern York",
        "010": "Hanover",
        "012": "Northeastern",
        "014": "Northern York",
        "016": "Red Lion",
        "018": "South Eastern",
        "020": "South Western",
        "022": "Southern York",
        "024": "Spring Grove",
        "026": "West York",
        "028": "York City",
        "030": "York Suburban",
        "17F": "West Shore",
        "17G": "West Shore",
        "17L": "West Shore",
        "17N": "West Shore",
    }
    assert SCHOOL_DISTRICTS == expected

    # The browser currently formats the raw county code itself. Keep that
    # duplicated UI map locked to the API map until labels move into a shared
    # response contract.
    frontend_labels = (REPO_ROOT / "frontend/src/lib/propertyLabels.ts").read_text()
    for code, label in expected.items():
        assert f"'{code}': '{label}'" in frontend_labels


def test_person_name_lookup_searches_first_last_and_county_last_first_orders():
    variants = [value.casefold() for value in _lookup_variants("Avery Coleman")]

    assert "avery coleman" in variants
    assert "coleman avery" in variants


def test_company_name_is_not_reversed_around_its_legal_suffix():
    variants = [value.casefold() for value in _lookup_variants("Acme Holdings LLC")]

    assert "acme holdings llc" in variants
    assert "llc acme holdings" not in variants


def test_pasted_address_adds_county_style_suffix_and_drops_location_tail():
    variants = [
        value.casefold() for value in _lookup_variants("1 Main Street, York PA 17401")
    ]

    assert "1 main street" in variants
    assert "1 main st" in variants


def test_pidn_normalization_preserves_canonical_letters_and_removes_separators():
    assert _pidn_candidate("39000-QH-002000") == "39000QH002000"
    assert _pidn_candidate("1 Main St") is None
    assert _pidn_candidate("Avery Coleman") is None


def test_ranking_deduplicates_parcel_hits_and_keeps_the_strongest_match():
    results = _deduplicate_and_rank(
        [
            {
                "result_type": "parcel",
                "title": "1 Main St",
                "pidn": "0000000000001",
                "score": 0.72,
                "match_kind": "owner",
            },
            {
                "result_type": "parcel",
                "title": "1 Main St",
                "pidn": "0000000000001",
                "score": 1.0,
                "match_kind": "address",
            },
            {
                "result_type": "license",
                "title": "Main Street Cafe",
                "score": 0.6,
                "match_kind": "license",
            },
        ],
        limit=20,
    )

    assert len(results) == 2
    assert results[0]["pidn"] == "0000000000001"
    assert results[0]["match_kind"] == "address"
