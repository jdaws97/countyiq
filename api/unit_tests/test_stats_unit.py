"""Unit coverage for homepage statistics assembled from database aggregates."""

from contextlib import contextmanager
from datetime import date

from api.routes import stats


def test_stats_exposes_the_latest_tax_claim_report_date(monkeypatch):
    rows = iter(
        [
            {
                "municipality_count": 72,
                "delinquent_parcels": 10,
                "total_delinquent": 1000,
                "flood_zone_count": 5,
                "liquor_license_count": 4,
                "address_point_count": 3,
                "structure_count": 2,
                "parcel_count": 1,
                "total_assessed": 5000,
            },
            {
                "county_tax_owed": 400,
                "school_tax_owed": 300,
                "municipal_tax_owed": 200,
                "oldest_delinquent_year": 2022,
                "districts_affected": 6,
                "tax_claim_report_date": date(2026, 4, 19),
            },
        ]
    )

    class FakeCursor:
        def execute(self, _query):
            return None

        def fetchone(self):
            return next(rows)

    @contextmanager
    def fake_cursor():
        yield FakeCursor()

    monkeypatch.setattr(stats, "get_cursor", fake_cursor)
    monkeypatch.setattr(stats, "require_source_use", lambda *_args, **_kwargs: None)

    response = stats.get_stats()

    assert response["tax_claim_report_date"] == date(2026, 4, 19)
