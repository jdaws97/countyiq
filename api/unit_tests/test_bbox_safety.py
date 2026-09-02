"""Safety and privacy coverage for public bounding-box responses."""

from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from api.lib.query_bounds import MAX_BBOX_RESULTS, validate_bbox
from api.routes import parcels, radar


class _RowsCursor:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.sql = ""
        self.params: dict = {}

    def execute(self, sql: str, params: dict) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self) -> list[dict]:
        return self.rows


def _cursor_context(cursor: _RowsCursor):
    @contextmanager
    def _context():
        yield cursor

    return _context


@pytest.mark.parametrize(
    ("west", "south", "east", "north"),
    [
        (-76.8, 40.0, -76.9, 40.1),
        (-76.9, 40.1, -76.8, 40.0),
        (-77.0, 40.0, -76.7, 40.1),
        (-76.9, 39.9, -76.8, 40.2),
    ],
)
def test_bbox_rejects_inverted_or_excessive_envelopes(
    west: float,
    south: float,
    east: float,
    north: float,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_bbox(west, south, east, north)

    assert exc_info.value.status_code == 422


def test_parcel_bbox_fetches_one_extra_row_and_reports_truncation(monkeypatch):
    cursor = _RowsCursor(
        [
            {"geometry": None, "pidn": "1", "aprtotal": None, "price": None},
            {"geometry": None, "pidn": "2", "aprtotal": None, "price": None},
            {"geometry": None, "pidn": "3", "aprtotal": None, "price": None},
        ]
    )
    monkeypatch.setattr(parcels, "get_cursor", _cursor_context(cursor))
    monkeypatch.setattr(parcels, "require_source_use", lambda *args, **kwargs: None)
    monkeypatch.setattr(parcels, "source_use_allowed", lambda *args, **kwargs: False)

    response = parcels.parcels_bbox(
        west=-76.9,
        south=39.9,
        east=-76.8,
        north=40.0,
        layer=None,
        limit=2,
    )

    assert response["count"] == 2
    assert response["limit"] == 2
    assert response["truncated"] is True
    assert [feature["properties"]["pidn"] for feature in response["features"]] == [
        "1",
        "2",
    ]
    assert cursor.params["fetch_limit"] == 3
    assert "ORDER BY p.pidn" in cursor.sql
    assert "LIMIT %(fetch_limit)s" in cursor.sql


def test_radar_bbox_has_the_same_hard_limit_contract(monkeypatch):
    cursor = _RowsCursor(
        [
            {"pidn": "1", "score": 90},
            {"pidn": "2", "score": 80},
        ]
    )
    monkeypatch.setattr(radar, "get_cursor", _cursor_context(cursor))
    monkeypatch.setattr(radar, "_require_radar_sources", lambda _cur: None)

    response = radar.development_bbox(
        west=-76.9,
        south=39.9,
        east=-76.8,
        north=40.0,
        view="momentum",
        min_score=0,
        limit=1,
    )

    assert response == {
        "count": 1,
        "limit": 1,
        "truncated": True,
        "parcels": [{"pidn": "1", "score": 90}],
    }
    assert cursor.params["fetch_limit"] == 2
    assert "ORDER BY dm.score DESC, dm.pidn" in cursor.sql


def test_organization_exception_does_not_expose_prior_owner_or_mail_address():
    parcel = {
        "owner_full": "ACME HOLDINGS LLC",
        "own_name1": "ACME HOLDINGS LLC",
        "own_name2": "ATTN JANE DOE",
        "prev_owner": "JOHN DOE",
        "mail_addr_full": "1 PRIVATE LANE",
    }

    parcels._redact_parcel_owner_fields(
        parcel,
        show_people=False,
        show_current_owner=True,
    )

    assert parcel == {
        "owner_full": "ACME HOLDINGS LLC",
        "own_name1": None,
        "own_name2": None,
        "prev_owner": None,
        "mail_addr_full": None,
    }


def test_bbox_public_limit_is_explicit_and_finite():
    assert MAX_BBOX_RESULTS == 5_000
