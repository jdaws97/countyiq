from collections.abc import Iterator

import psycopg2
import pytest
from fastapi import HTTPException

from api.lib.development_radar import (
    SIGNAL_CAVEATS,
    SIGNAL_INTERPRETATIONS,
    SIGNAL_TITLES,
    build_signal_presentation,
    format_signal_label,
    sanitize_signals_for_public,
)
from api.routes.radar import _plan_status_clause, _validate_acre_range
from api.tests.conftest import (
    DB_ENV,
    OTHER_PIDN,
    SECOND_PIDN,
    TEST_MUNICIPALITY,
    TEST_PIDN,
)

EXPECTED_SIGNAL_KEYS = {
    "municipal_record",
    "active_subdivision",
    "nearby_subdivision",
    "economic_development_park",
    "municipal_action",
    "zoning_mismatch",
    "ownership_change",
    "vacancy",
    "tax_distress",
    "assemblage",
    "entity_assemblage",
    "penndot_project",
    "development_overlay",
    "local_traffic_activity",
    "growth_area",
    "soil_constraint",
    "zoning_constraint",
    "environmental_diligence",
    "flood_zone",
    "conservation_easement",
    "ag_security",
}


def test_every_signal_has_a_title_interpretation_and_caveat():
    assert set(SIGNAL_TITLES) == EXPECTED_SIGNAL_KEYS
    assert set(SIGNAL_INTERPRETATIONS) == EXPECTED_SIGNAL_KEYS
    assert set(SIGNAL_CAVEATS) == EXPECTED_SIGNAL_KEYS


def test_soil_label_names_the_actual_slope_trigger_not_drainage():
    signal = {
        "weight": -0.08,
        "site_screening_points": -15,
        "evidence": {
            "soil_units": [
                {
                    "map_unit_symbol": "PcF",
                    "map_unit_name": "PENN CHANNERY LOAM, 25 TO 50 PERCENT SLOPES, VERY STONY",
                    "coverage_pct": 67.9,
                    "drainage": "Well drained",
                    "septic_rating": "Very limited",
                    "slope_low": 25,
                    "slope_high": 50,
                    "representative_slope": 37,
                    "hydrologic_group": "B",
                }
            ]
        },
    }

    label = format_signal_label("soil_constraint", signal)
    presentation = build_signal_presentation("soil_constraint", signal)

    assert "37% representative slope" in label
    assert "Well drained" not in label
    assert presentation["score_impacts"]["site_screening"] == -15
    assert any(fact["label"] == "Mapped drainage" for fact in presentation["facts"])


def test_ag_security_is_context_and_explicitly_not_a_prohibition():
    signal = {
        "affects_eligibility": False,
        "momentum_points": 0,
        "opportunity_points": 0,
        "site_screening_points": 0,
        "evidence": {"resolution": "2020-04", "development_prohibition": False},
    }

    presentation = build_signal_presentation("ag_security", signal)

    assert presentation["affects_eligibility"] is False
    assert "not a development prohibition" in presentation["summary"]
    assert set(presentation["score_impacts"].values()) == {0}


def test_tax_claim_amounts_are_suppressed_even_when_people_display_is_allowed():
    signals = {
        "tax_distress": {
            "weight": 0.1,
            "evidence": {
                "has_current_delinquency": True,
                "total_owed": 1234.56,
                "years_delinquent": 3,
                "oldest_year": 2023,
                "source_url": "https://example.test/tax.pdf",
            },
        }
    }

    public = sanitize_signals_for_public(signals)
    evidence = public["tax_distress"]["evidence"]

    assert evidence["has_current_delinquency"] is True
    assert "total_owed" not in evidence
    assert "years_delinquent" not in evidence
    assert "oldest_year" not in evidence


def test_labels_do_not_overclaim_investor_or_assemblage_intent():
    ownership = {
        "evidence": {
            "buyer_name_looks_organizational": True,
            "saledt": "01-JAN-2026",
            "price": 250000,
        }
    }
    contiguous = {"evidence": {"contiguous_same_owner_parcels": 3}}

    assert "organization-name buyer" in format_signal_label(
        "ownership_change", ownership
    )
    assert "Investor" not in format_signal_label("ownership_change", ownership)
    assert "Same recorded owner holds" in format_signal_label(
        "entity_assemblage", contiguous
    )
    assert "assembling" not in format_signal_label("entity_assemblage", contiguous)


def test_plan_status_defaults_to_no_linked_plan_only_for_opportunity():
    assert _plan_status_clause(plan_status=None, view="opportunity") == (
        " AND dm.has_active_plan = FALSE"
    )
    assert _plan_status_clause(plan_status=None, view="momentum") == ""
    assert _plan_status_clause(plan_status="active", view="readiness") == (
        " AND dm.has_active_plan = TRUE"
    )


def test_acre_range_rejects_an_inverted_screen():
    try:
        _validate_acre_range(25, 5)
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("Expected inverted acre range to be rejected")


@pytest.fixture
def radar_parity_rows() -> Iterator[None]:
    """Create matching, active-plan, and ineligible rows inside one map viewport."""
    original_rows: list[tuple] = []
    try:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT p.pidn, p.municipality, p."class", p.acres,
                           dm.has_active_plan, dm.eligible
                    FROM staging.parcels p
                    JOIN public.development_momentum dm ON dm.pidn = p.pidn
                    WHERE p.pidn = ANY(%s)
                    ORDER BY p.pidn
                    """,
                ([TEST_PIDN, SECOND_PIDN, OTHER_PIDN],),
            )
            original_rows = cur.fetchall()
            cur.execute(
                """
                    UPDATE staging.parcels
                    SET municipality = %s, "class" = 'C', acres = 1.5
                    WHERE pidn = ANY(%s)
                    """,
                (TEST_MUNICIPALITY, [TEST_PIDN, SECOND_PIDN, OTHER_PIDN]),
            )
            cur.execute(
                """
                    UPDATE public.development_momentum
                    SET has_active_plan = CASE
                            WHEN pidn = %s THEN FALSE
                            WHEN pidn = %s THEN TRUE
                            ELSE FALSE
                        END,
                        eligible = CASE WHEN pidn = %s THEN FALSE ELSE TRUE END
                    WHERE pidn = ANY(%s)
                    """,
                (
                    TEST_PIDN,
                    SECOND_PIDN,
                    OTHER_PIDN,
                    [TEST_PIDN, SECOND_PIDN, OTHER_PIDN],
                ),
            )
        yield
    finally:
        if original_rows:
            with (
                psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn,
                conn.cursor() as cur,
            ):
                for (
                    pidn,
                    municipality,
                    parcel_class,
                    acres,
                    has_active_plan,
                    eligible,
                ) in original_rows:
                    cur.execute(
                        """
                            UPDATE staging.parcels
                            SET municipality = %s, "class" = %s, acres = %s
                            WHERE pidn = %s
                            """,
                        (municipality, parcel_class, acres, pidn),
                    )
                    cur.execute(
                        """
                            UPDATE public.development_momentum
                            SET has_active_plan = %s, eligible = %s
                            WHERE pidn = %s
                            """,
                        (has_active_plan, eligible, pidn),
                    )


@pytest.mark.parametrize(
    ("list_path", "view", "plan_status", "expected_pidns"),
    [
        ("/api/radar/opportunity", "opportunity", "none", {TEST_PIDN}),
        ("/api/radar/development", "momentum", "any", {TEST_PIDN, SECOND_PIDN}),
        ("/api/radar/site-readiness", "readiness", "active", {SECOND_PIDN}),
    ],
)
def test_radar_bbox_matches_regular_list_filters(
    client,
    radar_parity_rows,
    list_path: str,
    view: str,
    plan_status: str,
    expected_pidns: set[str],
):
    criteria = {
        "min_score": 0,
        "municipality": TEST_MUNICIPALITY,
        "min_acres": 1,
        "max_acres": 2,
        "class": "C",
        "plan_status": plan_status,
    }
    list_response = client.get(list_path, params=criteria)
    bbox_response = client.get(
        "/api/radar/development/bbox",
        params={
            **criteria,
            "view": view,
            "west": -76.81,
            "south": 39.89,
            "east": -76.77,
            "north": 39.93,
        },
    )

    assert list_response.status_code == 200
    assert bbox_response.status_code == 200
    list_pidns = {row["pidn"] for row in list_response.json()["parcels"]}
    bbox_pidns = {row["pidn"] for row in bbox_response.json()["parcels"]}
    assert list_pidns == expected_pidns
    assert bbox_pidns == expected_pidns
