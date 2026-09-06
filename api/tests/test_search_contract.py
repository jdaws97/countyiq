"""Database-backed contracts for the deterministic parcel search path."""


def _parcel_results(response) -> list[dict]:
    assert response.status_code == 200
    return [
        result
        for result in response.json()["results"]
        if result.get("result_type") == "parcel"
    ]


def test_owner_name_in_either_order_finds_parcel_without_echoing_owner(client):
    parcels = _parcel_results(client.get("/api/search", params={"q": "Holdings Alpha"}))

    assert parcels
    assert parcels[0]["pidn"] == "0000000000001"
    assert parcels[0]["title"] == "1 Main St"
    assert parcels[0]["match_kind"] == "owner"
    assert "Alpha Holdings LLC" not in str(parcels)


def test_full_street_suffix_matches_county_abbreviation(client):
    parcels = _parcel_results(
        client.get("/api/search", params={"q": "1 Main Street, York PA 17401"})
    )

    assert parcels
    assert parcels[0]["pidn"] == "0000000000001"


def test_formatted_pidn_resolves_to_exact_parcel(client):
    parcels = _parcel_results(
        client.get("/api/search", params={"q": "0000-0000-00001"})
    )

    assert parcels[0]["pidn"] == "0000000000001"
    assert parcels[0]["score"] == 1.0
    assert parcels[0]["match_kind"] == "parcel_id"
