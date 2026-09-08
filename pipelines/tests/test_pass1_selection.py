"""Pass 1 cluster selection includes customer-visible person identity."""

import pytest
from countyiq.lib.entity_types import classify_entity, is_organization_name
from countyiq.lib.pass1_entity_verification import (
    CANDIDATE_CLUSTERS_QUERY,
    SHARED_ADDRESS_HUB_LIMIT,
    cluster_involves_organization,
    resolve_pass1_scope,
    select_pass1_clusters,
    select_pass1_work,
    stable_cluster_key,
)

CLUSTERS = [
    ["SMITH JOHN A", "SMITH JOHN"],
    ["ACME HOLDINGS LLC", "ACME HOLDINGS L L C"],
    ["YORK TOWNSHIP", "TOWNSHIP OF YORK"],
    ["DOE JANE & DOE JOHN", "DOE FAMILY TRUST"],
]


def test_person_only_clusters_are_included_by_default(monkeypatch) -> None:
    monkeypatch.delenv("COUNTYIQ_PASS1_INCLUDE_PERSON_CLUSTERS", raising=False)
    kept, skipped = select_pass1_clusters(CLUSTERS)
    assert kept == CLUSTERS
    assert skipped == 0


def test_env_flag_can_disable_person_clusters(monkeypatch) -> None:
    monkeypatch.setenv("COUNTYIQ_PASS1_INCLUDE_PERSON_CLUSTERS", "false")
    kept, skipped = select_pass1_clusters(CLUSTERS)
    assert kept == CLUSTERS[1:]
    assert skipped == 1


def test_explicit_argument_overrides_environment(monkeypatch) -> None:
    monkeypatch.setenv("COUNTYIQ_PASS1_INCLUDE_PERSON_CLUSTERS", "true")
    kept, skipped = select_pass1_clusters(CLUSTERS, include_person_only=False)
    assert len(kept) == 3 and skipped == 1


def test_organization_detection_matches_owner_classifier() -> None:
    assert cluster_involves_organization(["SMITH JOHN", "SMITH FAMILY TRUST"])
    assert cluster_involves_organization(["211 INVESTORS", "213 INVESTORS"])
    assert cluster_involves_organization(
        ["JEFFERSON SEWER AUTH", "JEFFERSON SEWER AUTHOR"]
    )
    assert not cluster_involves_organization(["SMITH JOHN", "SMITH JON"])
    assert classify_entity("COUNTY OF YORK") == "government"
    assert is_organization_name("MAPLE ST HOLDINGS LLC")
    assert not is_organization_name("")


def test_candidate_query_excludes_registered_agent_hubs() -> None:
    assert "hub_addresses" in CANDIDATE_CLUSTERS_QUERY
    assert f"COUNT(*) >= {SHARED_ADDRESS_HUB_LIMIT}" in CANDIDATE_CLUSTERS_QUERY
    assert (
        "NOT IN (SELECT office_address FROM hub_addresses)" in CANDIDATE_CLUSTERS_QUERY
    )


def test_paid_scope_retains_whole_active_clusters_and_free_registration_facts():
    registrations = [{"entity_name": "ACME HOLDINGS LLC", "entity_number": "123"}]
    kept, free = select_pass1_work(
        CLUSTERS, registrations, {"SMITH JOHN"}, scope="active_records", allow_llm=True
    )
    assert kept == CLUSTERS[:2]
    assert kept[0] == ["SMITH JOHN A", "SMITH JOHN"]
    assert free == {stable_cluster_key(CLUSTERS[1])}


def test_disabling_paid_inference_still_keeps_only_official_registration_resolution():
    registrations = [{"entity_name": "ACME HOLDINGS LLC", "entity_number": "123"}]
    kept, free = select_pass1_work(
        CLUSTERS, registrations, {"SMITH JOHN"}, scope="all", allow_llm=False
    )
    assert kept == [CLUSTERS[1]]
    assert len(free) == 1


def test_all_cluster_scope_is_explicit_and_invalid_scope_does_not_expand_spend(
    monkeypatch,
):
    monkeypatch.delenv("COUNTYIQ_PASS1_SCOPE", raising=False)
    assert resolve_pass1_scope() == "active_records"
    monkeypatch.setenv("COUNTYIQ_PASS1_SCOPE", "all")
    assert resolve_pass1_scope() == "all"
    kept, _ = select_pass1_work(CLUSTERS, [], set(), scope="all", allow_llm=True)
    assert kept == CLUSTERS
    monkeypatch.setenv("COUNTYIQ_PASS1_SCOPE", "alll")
    with pytest.raises(ValueError, match="COUNTYIQ_PASS1_SCOPE"):
        resolve_pass1_scope()


def test_acquisitions_prioritize_organizations_and_explicit_watches_keep_people():
    from countyiq.lib.pass1_entity_verification import (
        ACQUISITION_ENTITY_NAMES_QUERY,
        ACTIVE_ENTITY_NAMES_QUERY,
        WATCHED_ENTITY_NAMES_QUERY,
        priority_entity_names,
    )

    class Database:
        def execute(self, query):
            return {
                ACTIVE_ENTITY_NAMES_QUERY: [("PLAN OWNER",)],
                ACQUISITION_ENTITY_NAMES_QUERY: [("BUILDER LLC",), ("PRIVATE PERSON",)],
                WATCHED_ENTITY_NAMES_QUERY: [("WATCHED PERSON",)],
            }[query]

    names = priority_entity_names(Database(), [])
    assert names == {"PLAN OWNER", "BUILDER LLC", "WATCHED PERSON"}
    clusters = [
        ["BUILDER LLC", "BUILDER LIMITED"],
        ["PRIVATE PERSON", "PRIVATE P"],
        ["WATCHED PERSON", "WATCHED P"],
    ]
    kept, _ = select_pass1_work(
        clusters, [], names, scope="active_records", allow_llm=True
    )
    assert kept == [clusters[0], clusters[2]]


def test_purchase_under_an_abbreviated_name_prioritizes_its_organization_cluster():
    from countyiq.lib.pass1_entity_verification import (
        ACQUISITION_ENTITY_NAMES_QUERY,
        priority_entity_names,
    )

    class Database:
        def execute(self, query):
            if query == ACQUISITION_ENTITY_NAMES_QUERY:
                return [("LANCASTER COUNTY CONSERVANCY",)]
            return []

    clusters = [["LANCASTER COUNTY CONSERVANCY", "LANCASTER CNTY CONSERVANCY INC"]]
    names = priority_entity_names(Database(), clusters)
    kept, _ = select_pass1_work(
        clusters, [], names, scope="active_records", allow_llm=True
    )
    assert kept == clusters
