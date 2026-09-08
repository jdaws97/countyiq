"""Municipality summaries share Activity's account and freshness boundaries."""

# Shared fixtures are requested by pytest by name.
# ruff: noqa: F811

import pytest

from api.tests.conftest import TEST_MUNICIPALITY
from api.tests.test_matter_accounts import add_case, publish_test_account
from api.tests.test_municipal_evidence import writer
from api.tests.test_municipal_evidence_workflow import add_source  # noqa: F401


@pytest.fixture(autouse=True)
def preserve_score_fixtures():
    """The shared source-publication helper also rebuilds unrelated radar scores."""
    with writer() as cursor:
        cursor.execute(
            "CREATE TEMP TABLE saved_momentum ON COMMIT DROP AS "
            "SELECT * FROM public.development_momentum"
        )
        try:
            yield
        finally:
            cursor.execute("DELETE FROM public.development_momentum")
            cursor.execute(
                "INSERT INTO public.development_momentum SELECT * FROM saved_momentum"
            )


def _pipeline(client) -> dict:
    response = client.get(f"/api/municipalities/{TEST_MUNICIPALITY}")
    assert response.status_code == 200, response.text
    return response.json()["development_pipeline"]


def test_summary_counts_case_once_and_withdraws_cached_stale_sources(
    client, add_source
):
    baseline = _pipeline(client)
    agenda, _ = add_case(add_source)
    keys = publish_test_account()
    current = _pipeline(client)

    assert current["total_matters"] == baseline["total_matters"] + len(keys)
    assert {item["event_key"] for item in current["recent"]}.intersection(keys) == set(
        keys
    )
    assert not any(
        item["event_key"].startswith("municipal:") for item in current["recent"]
    )
    assert _pipeline(client) == current

    with writer() as cursor:
        cursor.execute(
            "UPDATE staging.public_proceedings SET raw_text = raw_text || ' amended' "
            "WHERE id = %s",
            (agenda,),
        )
    withdrawn = _pipeline(client)
    assert withdrawn["total_matters"] == baseline["total_matters"]
    assert not {item["event_key"] for item in withdrawn["recent"]}.intersection(keys)
