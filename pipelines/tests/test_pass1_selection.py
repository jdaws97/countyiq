"""Pass 1 sends only clusters that can reach a customer surface."""

from countyiq.lib.entity_types import classify_entity, is_organization_name
from countyiq.lib.pass1_entity_verification import (
    CANDIDATE_CLUSTERS_QUERY,
    SHARED_ADDRESS_HUB_LIMIT,
    cluster_involves_organization,
    select_pass1_clusters,
)

CLUSTERS = [
    ["SMITH JOHN A", "SMITH JOHN"],
    ["ACME HOLDINGS LLC", "ACME HOLDINGS L L C"],
    ["YORK TOWNSHIP", "TOWNSHIP OF YORK"],
    ["DOE JANE & DOE JOHN", "DOE FAMILY TRUST"],
]


def test_person_only_clusters_are_skipped_by_default(monkeypatch) -> None:
    monkeypatch.delenv("COUNTYIQ_PASS1_INCLUDE_PERSON_CLUSTERS", raising=False)
    kept, skipped = select_pass1_clusters(CLUSTERS)
    assert kept == CLUSTERS[1:]
    assert skipped == 1


def test_env_flag_restores_person_clusters(monkeypatch) -> None:
    monkeypatch.setenv("COUNTYIQ_PASS1_INCLUDE_PERSON_CLUSTERS", "true")
    kept, skipped = select_pass1_clusters(CLUSTERS)
    assert kept == CLUSTERS
    assert skipped == 0


def test_explicit_argument_overrides_environment(monkeypatch) -> None:
    monkeypatch.setenv("COUNTYIQ_PASS1_INCLUDE_PERSON_CLUSTERS", "true")
    kept, skipped = select_pass1_clusters(CLUSTERS, include_person_only=False)
    assert len(kept) == 3 and skipped == 1


def test_organization_detection_matches_owner_classifier() -> None:
    assert cluster_involves_organization(["SMITH JOHN", "SMITH FAMILY TRUST"])
    assert not cluster_involves_organization(["SMITH JOHN", "SMITH JON"])
    assert classify_entity("COUNTY OF YORK") == "government"
    assert is_organization_name("MAPLE ST HOLDINGS LLC")
    assert not is_organization_name("")


def test_candidate_query_excludes_registered_agent_hubs() -> None:
    assert "hub_addresses" in CANDIDATE_CLUSTERS_QUERY
    assert f"COUNT(*) >= {SHARED_ADDRESS_HUB_LIMIT}" in CANDIDATE_CLUSTERS_QUERY
    assert "NOT IN (SELECT office_address FROM hub_addresses)" in CANDIDATE_CLUSTERS_QUERY
