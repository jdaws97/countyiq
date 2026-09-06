"""Persisted events immediately follow current municipal policy."""

import psycopg2
import pytest
from api.tests.conftest import DB_ENV, TEST_PIDN


@pytest.mark.parametrize(
    "state",
    [
        "paused",
        "expired",
        "denied",
        "retired",
        "missing",
        "unreviewed",
        "review_required",
        "quarantined",
    ],
)
def test_persisted_project_is_hidden_without_rebuilding(client, state):
    url = "/api/feed"
    params = {"category": "development", "since_days": 90}
    baseline = client.get(url, params=params)
    assert baseline.status_code == 200, baseline.text
    assert any(
        e["event_key"] == "development:test-project" for e in baseline.json()["events"]
    )
    parcel = client.get(f"/api/parcels/{TEST_PIDN}")
    assert parcel.status_code == 200, parcel.text
    assert any(
        row["body_name"] == "Hanover Borough Council"
        for row in parcel.json()["linked_proceedings"]
    )
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT rights_status,derived_product_allowed,review_due_on FROM meta.municipality_source_rights WHERE source_key='hanover_borough_council'"
            )
            previous = cursor.fetchone()
            cursor.execute(
                "SELECT id,body_name,valid_to,metadata_quality FROM staging.public_proceedings WHERE body_name='Hanover Borough Council' ORDER BY id LIMIT 1"
            )
            proceeding = cursor.fetchone()
            if state in {"unreviewed", "review_required", "quarantined"}:
                from psycopg2.extras import Json

                cursor.execute(
                    "UPDATE staging.public_proceedings SET metadata_quality=%s WHERE id=%s",
                    (Json({"status": state}), proceeding[0]),
                )
            elif state == "retired":
                cursor.execute(
                    "UPDATE staging.public_proceedings SET valid_to=NOW() WHERE id=%s",
                    (proceeding[0],),
                )
            elif state == "missing":
                cursor.execute(
                    "UPDATE staging.public_proceedings SET body_name='Unreviewed fixture body' WHERE id=%s",
                    (proceeding[0],),
                )
            elif state == "paused":
                cursor.execute(
                    "UPDATE meta.municipality_source_rights SET rights_status='paused' WHERE source_key='hanover_borough_council'"
                )
            elif state == "expired":
                cursor.execute(
                    "UPDATE meta.municipality_source_rights SET review_due_on=CURRENT_DATE-1 WHERE source_key='hanover_borough_council'"
                )
            else:
                cursor.execute(
                    "UPDATE meta.municipality_source_rights SET derived_product_allowed=FALSE WHERE source_key='hanover_borough_council'"
                )
    try:
        response = client.get(url, params=params)
        assert response.status_code == 200, response.text
        assert not any(
            e["event_key"] == "development:test-project"
            for e in response.json()["events"]
        )
        assert (
            client.get("/api/cases/projects/project:test-main-street").json()["events"]
            == []
        )
        assert (
            client.get("/api/directory/projects", params={"q": "Main Street"}).json()[
                "projects"
            ]
            == []
        )
        parcel = client.get(f"/api/parcels/{TEST_PIDN}")
        assert parcel.status_code == 200, parcel.text
        assert all(
            row["proceeding_id"] != proceeding[0]
            for row in parcel.json()["linked_proceedings"]
        )
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE meta.municipality_source_rights SET rights_status=%s,derived_product_allowed=%s,review_due_on=%s WHERE source_key='hanover_borough_council'",
                    previous,
                )
                from psycopg2.extras import Json

                cursor.execute(
                    "UPDATE staging.public_proceedings SET body_name=%s,valid_to=%s,metadata_quality=%s WHERE id=%s",
                    (proceeding[1], proceeding[2], Json(proceeding[3]), proceeding[0]),
                )
    baseline = client.get(url, params=params)
    assert baseline.status_code == 200, baseline.text
    assert any(
        e["event_key"] == "development:test-project" for e in baseline.json()["events"]
    )
    parcel = client.get(f"/api/parcels/{TEST_PIDN}")
    assert parcel.status_code == 200, parcel.text
    assert any(
        row["body_name"] == "Hanover Borough Council"
        for row in parcel.json()["linked_proceedings"]
    )


@pytest.mark.parametrize(
    "category,paused_source",
    [
        ("parcel", "public_proceedings"),
        ("development", "tax_claims"),
        ("development", "sheriff_sales"),
    ],
)
def test_feed_category_is_not_disabled_by_an_unrelated_source(
    client, category, paused_source
):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT rights_status FROM meta.source_rights WHERE source_key=%s",
                (paused_source,),
            )
            previous = cursor.fetchone()[0]
            cursor.execute(
                "UPDATE meta.source_rights SET rights_status='paused' WHERE source_key=%s",
                (paused_source,),
            )
    try:
        response = client.get("/api/feed", params={"category": category})
        assert response.status_code == 200, response.text
        assert response.json()["events"]
        assert all(event["category"] == category for event in response.json()["events"])
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE meta.source_rights SET rights_status=%s WHERE source_key=%s",
                    (previous, paused_source),
                )


@pytest.mark.parametrize(
    "category,paused_source",
    [
        ("parcel", "tax_claims"),
        ("development", "public_proceedings"),
    ],
)
def test_feed_still_refuses_a_required_paused_source(client, category, paused_source):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT rights_status FROM meta.source_rights WHERE source_key=%s",
                (paused_source,),
            )
            previous = cursor.fetchone()[0]
            cursor.execute(
                "UPDATE meta.source_rights SET rights_status='paused' WHERE source_key=%s",
                (paused_source,),
            )
    try:
        assert client.get("/api/feed", params={"category": category}).status_code == 503
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE meta.source_rights SET rights_status=%s WHERE source_key=%s",
                    (previous, paused_source),
                )


@pytest.mark.parametrize("state", ["paused", "expired", "denied"])
def test_property_proceedings_follow_global_source_policy(client, state):
    url = f"/api/parcels/{TEST_PIDN}"
    assert client.get(url).json()["linked_proceedings"]
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT rights_status,derived_product_allowed,review_due_on FROM meta.source_rights WHERE source_key='public_proceedings'"
            )
            previous = cursor.fetchone()
            cursor.execute(
                """
                UPDATE meta.source_rights SET rights_status=%s,derived_product_allowed=%s,
                    review_due_on=CURRENT_DATE+%s WHERE source_key='public_proceedings'
            """,
                (
                    "paused" if state == "paused" else "conditional",
                    state != "denied",
                    -1 if state == "expired" else 30,
                ),
            )
    try:
        response = client.get(url)
        # The existing endpoint contract gates the full report on global sources.
        assert response.status_code == 503, response.text
        assert "linked_proceedings" not in response.json()
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE meta.source_rights SET rights_status=%s,derived_product_allowed=%s,review_due_on=%s WHERE source_key='public_proceedings'",
                    previous,
                )
    assert client.get(url).json()["linked_proceedings"]
