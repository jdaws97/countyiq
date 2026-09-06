"""Directories share public source policy and never expose private people."""


def test_organization_directory_lists_and_searches_businesses(client):
    response = client.get("/api/directory/organizations")
    assert response.status_code == 200, response.text
    organizations = response.json()["organizations"]
    assert organizations
    assert all(
        row["entity_type"] in {"business", "government"} for row in organizations
    )
    name = organizations[0]["canonical_name"]
    result = client.get("/api/directory/organizations", params={"q": name, "limit": 1})
    assert result.status_code == 200
    assert result.json()["organizations"][0]["canonical_name"] == name
    assert (
        client.get("/api/directory/organizations", params={"q": "%"}).json()[
            "organizations"
        ]
        == []
    )


def test_project_search_uses_governed_development_events(client):
    response = client.get("/api/directory/projects", params={"q": "not-a-real-project"})
    assert response.status_code == 200, response.text
    assert response.json() == {"projects": [], "has_more": False}
