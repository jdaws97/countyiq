"""Keep public query bounds explicit so invalid input never reaches PostgreSQL."""

from api.main import app


def _query_parameters(path: str) -> dict[str, dict]:
    operation = app.openapi()["paths"][path]["get"]
    return {
        parameter["name"]: parameter["schema"]
        for parameter in operation.get("parameters", [])
        if parameter["in"] == "query"
    }


def test_all_limit_parameters_require_at_least_one_result():
    unconstrained: list[str] = []
    for path, path_item in app.openapi()["paths"].items():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            for parameter in operation.get("parameters", []):
                if parameter["in"] != "query" or parameter["name"] != "limit":
                    continue
                if parameter["schema"].get("minimum") != 1:
                    unconstrained.append(path)

    assert unconstrained == []


def test_bbox_coordinates_are_bounded_to_valid_longitude_and_latitude():
    for path in ("/api/parcels/bbox", "/api/radar/development/bbox"):
        parameters = _query_parameters(path)
        assert parameters["west"]["minimum"] == -180
        assert parameters["west"]["maximum"] == 180
        assert parameters["east"]["minimum"] == -180
        assert parameters["east"]["maximum"] == 180
        assert parameters["south"]["minimum"] == -90
        assert parameters["south"]["maximum"] == 90
        assert parameters["north"]["minimum"] == -90
        assert parameters["north"]["maximum"] == 90


def test_watchlist_query_has_a_request_size_bound():
    parameters = _query_parameters("/api/parcels/summary")
    assert parameters["pidns"]["maxLength"] == 2000
